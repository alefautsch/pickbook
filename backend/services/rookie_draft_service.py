"""Live rookie draft board — computes from Sleeper + dynasty_draft recommender (§7 Phase 7)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.api.settings import _read_settings
from backend.db.models import League, Roster, RosterPlayer
from backend.schemas.rookie_draft import (
    RookieBoardRow,
    RookieDraftNextPickInfo,
    RookieDraftOnClock,
    RookieDraftTimelineRow,
    RookieDraftView,
    StarterNeeds,
    ValuePivotPlayer,
    ValuePivotSummary,
)
from backend.services.league_context import build_league_scoring_context
from backend.services.league_engine import LeagueScoringState
from backend.services.metrics_service import _collect_rostered_player_ids
from backend.services.pick_service import collect_league_traded_picks, pick_slot_by_roster
from backend.services.read_service import (
    SnapshotDynasty,
    apply_snapshot_dynasty,
    headshot_url,
    ovr_tier,
    snapshot_dynasty_by_id,
)
from dynasty_draft.config import load_config
from dynasty_draft.draft_context import build_draft_timeline
from dynasty_draft.draft_pick_ownership import (
    PickOwnerIndex,
    build_pick_no_owner_index,
    build_pick_owner_index,
    merge_pick_slot_order,
)
from dynasty_draft.dynasty_daddy import DynastyDaddyStore
from dynasty_draft.external_adp import AdpStore
from dynasty_draft.pick_projector import (
    _available_pool,
    _initial_roster_counts,
    _simulate_pick,
    _target_needs,
)
from dynasty_draft.recommender import DraftState
from dynasty_draft.sleeper_client import SleeperClient
from dynasty_draft.strategy import DraftStrategy
from dynasty_draft.war_data import POSITIONS, PlayerValue, WarData

ROOKIE_PLAYER_TYPE = 1
DEFAULT_POLL_SECONDS = 30


class RookieDraftState(LeagueScoringState):
    """Rookie draft mechanics on top of league sync scoring (§5.7)."""

    def __init__(
        self,
        *,
        draft: dict[str, Any],
        picks: list[dict[str, Any]],
        league_users: list[dict[str, Any]] | None = None,
        strategy: DraftStrategy,
        pick_owner_index: PickOwnerIndex | None = None,
        pick_no_owner_index: dict[int, int] | None = None,
        roster_owner_ids: dict[int, str] | None = None,
        league_row: League,
        roster_player_ids: set[str],
        user_id: str,
        settings: dict[str, Any],
        war: WarData,
        sleeper_players: dict[str, dict[str, Any]],
        client: SleeperClient,
    ) -> None:
        super().__init__(
            league_row=league_row,
            roster_player_ids=roster_player_ids,
            user_id=user_id,
            settings=settings,
            war=war,
            sleeper_players=sleeper_players,
            client=client,
        )
        self.draft = draft
        self.picks = picks
        self.league_users = league_users or []
        self.strategy = strategy
        self.pick_owner_index = pick_owner_index or {}
        self.pick_no_owner_index = pick_no_owner_index or {}
        self.roster_owner_ids = roster_owner_ids or {}
        self.__post_init__()


def resolve_rookie_draft_id(
    client: SleeperClient,
    league_id: str,
    *,
    override: str | None = None,
) -> str | None:
    if override:
        return override.strip() or None
    drafts = client.get_league_drafts(league_id)
    rookies = [
        d
        for d in drafts
        if int((d.get("settings") or {}).get("player_type", 0) or 0) == ROOKIE_PLAYER_TYPE
    ]
    if not rookies:
        return None
    active = [d for d in rookies if d.get("status") in {"pre_draft", "drafting"}]
    pool = active or rookies
    pool.sort(key=lambda d: d.get("last_picked") or 0, reverse=True)
    draft_id = pool[0].get("draft_id")
    return str(draft_id) if draft_id else None


def _load_strategy(settings: dict[str, Any]) -> DraftStrategy:
    config = load_config()
    raw = dict(config.get("strategy") or {})
    raw["draft_phase"] = "rookies"
    raw["teams"] = raw.get("teams", settings.get("teams", 10))
    return DraftStrategy.from_config({"strategy": raw})


def _overlay_snapshot_rows(
    rows: list[dict[str, Any]],
    snapshot_by_id: dict[str, SnapshotDynasty],
) -> None:
    for row in rows:
        apply_snapshot_dynasty(row, snapshot_by_id)


def build_rookie_draft_state(
    *,
    draft: dict[str, Any],
    picks: list[dict[str, Any]],
    league_row: League,
    league_users: list[dict[str, Any]],
    roster_player_ids: set[str],
    user_id: str,
    settings: dict[str, Any],
    client: SleeperClient,
    pick_owner_index: PickOwnerIndex | None = None,
    pick_no_owner_index: dict[int, int] | None = None,
    roster_owner_ids: dict[int, str] | None = None,
) -> RookieDraftState:
    war_path = Path(str(settings.get("war_csv", "war.csv")))
    if not war_path.exists():
        raise FileNotFoundError(f"Missing WAR file: {war_path}")

    players = client.get_players()
    war = WarData(war_path)
    scoring = build_league_scoring_context(league_row)
    dd_config = settings.get("dynasty_daddy") or {}
    if bool(dd_config.get("enabled", True)):
        try:
            dd_store = DynastyDaddyStore.load(
                league_row=league_row,
                superflex=scoring.superflex,
                config=dd_config,
                force_refresh=bool(settings.get("_force_metric_refresh")),
            )
            war = dd_store.overlay_war_data(war)
        except Exception:
            pass

    strategy = _load_strategy(settings)

    state = RookieDraftState(
        draft=draft,
        picks=picks,
        league_users=league_users,
        strategy=strategy,
        pick_owner_index=pick_owner_index,
        pick_no_owner_index=pick_no_owner_index,
        roster_owner_ids=roster_owner_ids,
        league_row=league_row,
        roster_player_ids=roster_player_ids,
        user_id=user_id,
        settings=settings,
        war=war,
        sleeper_players=players,
        client=client,
    )

    config = load_config()
    try:
        state.adp_store = AdpStore.load(config, superflex=state.is_superflex())
    except Exception:
        state.adp_store = None

    return state


def _roster_position_counts(
    db: Session,
    roster_db_id: int,
    sleeper_players: dict[str, dict[str, Any]],
) -> dict[str, int]:
    counts = {pos: 0 for pos in POSITIONS}
    counts["FLEX"] = 0
    roster_players = db.scalars(
        select(RosterPlayer).where(RosterPlayer.roster_id == roster_db_id)
    ).all()
    for rp in roster_players:
        pos = (rp.position or "").upper() or (
            (sleeper_players.get(rp.sleeper_player_id) or {}).get("position") or ""
        ).upper()
        if pos in counts:
            counts[pos] += 1
    return counts


def _draft_pick_counts(state: DraftState, roster_id: int) -> dict[str, int]:
    counts = {pos: 0 for pos in POSITIONS}
    counts["FLEX"] = 0
    for pick in state.picks:
        if int(pick.get("roster_id", -1)) != roster_id:
            continue
        meta = pick.get("metadata") or {}
        pos = (meta.get("position") or "").upper()
        if pos in counts:
            counts[pos] += 1
    return counts


def starter_needs_for_roster(
    state: DraftState,
    db: Session,
    league_row: League,
    roster_db_id: int,
    sleeper_roster_id: int,
) -> StarterNeeds:
    """Existing league roster + rookie picks made so far → open starter slots."""
    base = _roster_position_counts(db, roster_db_id, state.sleeper_players)
    draft_counts = _draft_pick_counts(state, sleeper_roster_id)
    counts = {pos: base.get(pos, 0) + draft_counts.get(pos, 0) for pos in POSITIONS}
    counts["FLEX"] = base.get("FLEX", 0) + draft_counts.get("FLEX", 0)

    roster_positions = state.roster_positions or league_row.roster_positions_json or []
    needs: dict[str, int] = {}
    qb_slots = sum(1 for p in roster_positions if p == "QB")
    superflex_slots = sum(1 for p in roster_positions if p == "SUPER_FLEX")
    needs["QB"] = max(0, qb_slots + superflex_slots - counts.get("QB", 0))
    for pos in ("RB", "WR", "TE"):
        roster_need = sum(1 for p in roster_positions if p == pos)
        needs[pos] = max(0, roster_need - counts.get(pos, 0))
    flex_slots = sum(1 for p in roster_positions if p == "FLEX")
    skill = counts["RB"] + counts["WR"] + counts["TE"]
    base_skill = sum(1 for p in roster_positions if p in {"RB", "WR", "TE"})
    needs["FLEX"] = max(0, flex_slots - max(0, skill - base_skill))
    return StarterNeeds(**needs)


def _pivot_player(row: dict[str, Any]) -> ValuePivotPlayer:
    ovr = row.get("dynasty_rating")
    return ValuePivotPlayer(
        name=str(row["name"]),
        position=row.get("pos"),
        ovr=int(ovr) if ovr is not None else None,
        adp_pick=row.get("adp_pick"),
        adp_delta=row.get("adp_delta"),
        bpa_rank=row.get("bpa_rank"),
        need_rank=row.get("need_rank"),
        reason=row.get("reason"),
    )


def _board_row_from_bpa(row: dict[str, Any], rank: int) -> RookieBoardRow:
    ovr = row.get("dynasty_rating")
    hppg = row.get("healthy_ppg")
    return RookieBoardRow(
        bpa_rank=rank,
        player_id=str(row["player_id"]),
        player_name=row.get("name"),
        position=row.get("pos"),
        nfl_team=row.get("team"),
        age=row.get("age"),
        ovr=int(ovr) if ovr is not None else None,
        tier=ovr_tier(int(ovr) if ovr is not None else None),
        dynasty_rookie=bool(row.get("dynasty_rookie")),
        trade_value=row.get("trade_value"),
        projected_ppg=hppg if row.get("hppg_expected") else row.get("healthy_ppg"),
        hppg=hppg,
        worp_ppg=row.get("worp_ppg"),
        hppg_expected=bool(row.get("hppg_expected")),
        flex_rating=row.get("flex_rating"),
        adp_pick=row.get("adp_pick"),
        adp_delta=row.get("adp_delta"),
        adp_class=row.get("adp_class"),
        bpa_score=row.get("bpa_score"),
        vor=row.get("vor"),
        headshot_url=headshot_url(str(row["player_id"])),
    )


def project_remaining_picks(
    state: DraftState,
    *,
    snapshot_by_id: dict[str, SnapshotDynasty] | None = None,
) -> dict[int, dict[str, Any]]:
    """Simulate unpicked slots using real Sleeper team order (ADP + positional needs)."""
    start = len(state.picks) + 1
    total = state._teams() * state._rounds()
    if start > total:
        return {}

    pool = _available_pool(state)
    if not pool:
        return {}

    roster_counts = _initial_roster_counts(state)
    targets = _target_needs(state)
    max_tv = pool[0][1].trade_value
    projections: dict[int, dict[str, Any]] = {}
    score_pool: list[tuple[str, PlayerValue]] = []

    for pick_no in range(start, total + 1):
        row, pool = _simulate_pick(
            state,
            pick_no,
            pool,
            roster_counts,
            targets,
            max_tv,
            source="projected",
        )
        if not row:
            break
        player_id = row.get("player_id")
        if player_id:
            war_player = state._match_war(str(player_id))
            if war_player:
                score_pool.append((str(player_id), war_player))
        projections[pick_no] = row

    if score_pool:
        dynasty_by_id = state.dynasty_scores(score_pool)
        for pick_no, row in projections.items():
            player_id = row.get("player_id")
            if not player_id:
                continue
            dynasty = dynasty_by_id.get(str(player_id)) or {}
            row["dynasty_rating"] = dynasty.get("dynasty_rating")
            row["dynasty_rookie"] = dynasty.get("dynasty_rookie")
            if snapshot_by_id:
                apply_snapshot_dynasty(row, snapshot_by_id)

    return projections


def _timeline_rows(
    state: DraftState,
    *,
    snapshot_by_id: dict[str, SnapshotDynasty] | None = None,
) -> list[RookieDraftTimelineRow]:
    raw = build_draft_timeline(state, past=None, upcoming=None)
    if snapshot_by_id:
        for row in raw:
            if row.get("player_id"):
                apply_snapshot_dynasty(row, snapshot_by_id)

    projections = project_remaining_picks(state, snapshot_by_id=snapshot_by_id)
    rows: list[RookieDraftTimelineRow] = []
    for row in raw:
        pick_no = int(row["pick_no"])
        status = str(row.get("status") or "done")
        projection = projections.get(pick_no)

        if status != "done" and projection:
            ovr = projection.get("dynasty_rating")
            rows.append(
                RookieDraftTimelineRow(
                    pick_no=pick_no,
                    round=row.get("round"),
                    team_name=projection.get("team") or row.get("team"),
                    player_id=str(projection["player_id"]) if projection.get("player_id") else None,
                    player_name=projection.get("name") or None,
                    position=projection.get("pos") or None,
                    ovr=int(ovr) if ovr is not None else None,
                    dynasty_rookie=bool(projection.get("dynasty_rookie")),
                    status="projected",
                    is_me=bool(projection.get("is_me")),
                )
            )
            continue

        ovr = row.get("dynasty_rating")
        rows.append(
            RookieDraftTimelineRow(
                pick_no=pick_no,
                round=row.get("round"),
                team_name=row.get("team"),
                player_id=str(row["player_id"]) if row.get("player_id") else None,
                player_name=row.get("name") or None,
                position=row.get("pos") or None,
                ovr=int(ovr) if ovr is not None else None,
                dynasty_rookie=bool(row.get("dynasty_rookie")),
                status=status,
                is_me=bool(row.get("is_me")),
            )
        )
    return rows


def load_rookie_draft_state_for_league(
    db: Session,
    league_id: str,
    *,
    draft_id: str | None = None,
    client: SleeperClient | None = None,
) -> tuple[RookieDraftState, League] | None:
    """Load rookie draft state without requiring the app user's Sleeper account."""
    league_row = db.get(League, league_id)
    if league_row is None:
        return None

    settings = _read_settings(db)
    client = client or SleeperClient()
    resolved_draft_id = resolve_rookie_draft_id(client, league_id, override=draft_id)
    if not resolved_draft_id:
        return None

    draft = client.get_draft(resolved_draft_id)
    picks = client.get_draft_picks(resolved_draft_id)
    league_users = client.get_league_users(league_id)
    season = str(draft.get("season") or league_row.season)
    pick_slots, _ = pick_slot_by_roster(client, league_id, season=season)
    draft = merge_pick_slot_order(draft, pick_slots)
    traded_picks = collect_league_traded_picks(client, league_id)
    pick_owner_index = build_pick_owner_index(traded_picks)
    teams = int((draft.get("settings") or {}).get("teams", league_row.total_rosters or 10))
    rounds = int((draft.get("settings") or {}).get("rounds", 20))
    pick_no_owner_index = build_pick_no_owner_index(
        season=season,
        teams=teams,
        rounds=rounds,
        pick_slots=pick_slots,
        traded_picks=traded_picks,
        draft_type=str(draft.get("type") or "snake"),
        slot_to_roster=draft.get("slot_to_roster_id"),
    )
    rosters = client.get_rosters(league_id)
    roster_owner_ids = {
        int(row["roster_id"]): str(row["owner_id"])
        for row in rosters
        if row.get("roster_id") is not None and row.get("owner_id") is not None
    }
    user_id = ""
    username = (settings.get("sleeper_username") or "").strip()
    if username:
        try:
            user_id = str(client.get_user(username)["user_id"])
        except Exception:
            user_id = ""

    roster_player_ids = _collect_rostered_player_ids(db, league_id)

    state = build_rookie_draft_state(
        draft=draft,
        picks=picks,
        league_row=league_row,
        league_users=league_users,
        roster_player_ids=roster_player_ids,
        user_id=user_id,
        settings=settings,
        client=client,
        pick_owner_index=pick_owner_index,
        pick_no_owner_index=pick_no_owner_index,
        roster_owner_ids=roster_owner_ids,
    )
    return state, league_row


def get_rookie_draft_view(
    db: Session,
    league_id: str,
    *,
    draft_id: str | None = None,
    roster_id: str | None = None,
    client: SleeperClient | None = None,
) -> RookieDraftView | None:
    settings = _read_settings(db)
    username = (settings.get("sleeper_username") or "").strip()
    if not username:
        raise ValueError("sleeper_username not configured in settings")

    loaded = load_rookie_draft_state_for_league(
        db, league_id, draft_id=draft_id, client=client
    )
    if loaded is None:
        return None
    state, league_row = loaded
    snapshot_by_id = snapshot_dynasty_by_id(db, league_id)

    rosters = db.scalars(select(Roster).where(Roster.league_id == league_id)).all()
    roster_by_sleeper = {r.sleeper_roster_id: r for r in rosters}
    my_roster = next((r for r in rosters if r.is_me), None)
    my_sleeper_roster_id = int(my_roster.sleeper_roster_id) if my_roster else None

    target_roster = None
    if roster_id:
        target_roster = roster_by_sleeper.get(roster_id)
    if target_roster is None:
        target_roster = my_roster

    next_info = state.next_pick_info()
    timeline = _timeline_rows(state, snapshot_by_id=snapshot_by_id)
    clock_row = next((row for row in timeline if row.status == "on_clock"), None)

    on_clock_roster_id: str | None = None
    pick_no = next_info.get("pick_no")
    if pick_no is not None:
        owner = state.owner_roster_for_pick(int(pick_no))
        if owner is not None:
            on_clock_roster_id = str(owner)

    on_clock = RookieDraftOnClock(
        roster_id=on_clock_roster_id,
        team_name=clock_row.team_name if clock_row else None,
        draft_slot=next_info.get("slot"),
        is_me=bool(
            my_sleeper_roster_id is not None
            and on_clock_roster_id is not None
            and int(on_clock_roster_id) == my_sleeper_roster_id
        ),
    )

    starter_needs = StarterNeeds()
    drafting_team_name: str | None = None
    drafting_roster_id: str | None = None
    if target_roster:
        drafting_roster_id = target_roster.sleeper_roster_id
        drafting_team_name = target_roster.team_name or target_roster.owner_name
        starter_needs = starter_needs_for_roster(
            state,
            db,
            league_row,
            target_roster.id,
            int(target_roster.sleeper_roster_id),
        )

    bpa_all = state.bpa_recommendations(limit=500)
    _overlay_snapshot_rows(bpa_all, snapshot_by_id)
    bpa_rows = [_board_row_from_bpa(row, idx + 1) for idx, row in enumerate(bpa_all)]
    bpa_top = bpa_rows[:15]

    need_all = state.recommend(limit=500)
    _overlay_snapshot_rows(need_all, snapshot_by_id)
    need_top = [
        _board_row_from_bpa(row, idx + 1).model_copy(update={"need_rank": idx + 1})
        for idx, row in enumerate(need_all[:15])
    ]

    pivot_raw = state.value_pivot_summary(limit=6)
    for key in ("take_bpa_over_need", "wait_for_later"):
        _overlay_snapshot_rows(list(pivot_raw.get(key) or []), snapshot_by_id)
    value_pivot = ValuePivotSummary(
        take_bpa_over_need=[_pivot_player(row) for row in pivot_raw.get("take_bpa_over_need") or []],
        wait_for_later=[_pivot_player(row) for row in pivot_raw.get("wait_for_later") or []],
    )
    by_ovr = sorted(bpa_rows, key=lambda row: (row.ovr is None, -(row.ovr or 0)))
    board = [
        row.model_copy(update={"ovr_rank": idx + 1}) for idx, row in enumerate(by_ovr)
    ]

    teams = state._teams()
    rounds = state._rounds()
    total_picks = teams * rounds
    picks_made = len(state.picks)
    draft = state.draft
    resolved_draft_id = str(draft.get("draft_id") or "")

    config = load_config()
    poll_seconds = max(
        DEFAULT_POLL_SECONDS,
        int(config.get("poll_seconds", DEFAULT_POLL_SECONDS)),
    )

    strategy_notes = list(
        state.strategy.strategy_notes(state.war, tv_fn=state.blended_trade_value)
    )
    for cliff in state.tier_cliffs():
        gap = cliff.get("gap", 0)
        strategy_notes.append(
            f"{cliff['pos']} tier cliff after {cliff['player']} "
            f"({int(gap)} TV gap to {cliff['next']})"
        )

    return RookieDraftView(
        league_id=league_id,
        league_name=league_row.name,
        draft_id=resolved_draft_id,
        draft_status=draft.get("status"),
        picks_made=picks_made,
        total_picks=total_picks,
        next_pick_no=next_info.get("pick_no"),
        on_clock=on_clock,
        my_roster_id=my_roster.sleeper_roster_id if my_roster else None,
        drafting_roster_id=drafting_roster_id,
        drafting_team_name=drafting_team_name,
        is_my_pick=bool(next_info.get("is_my_pick")),
        next_pick_info=RookieDraftNextPickInfo(
            pick_no=next_info.get("pick_no"),
            round=next_info.get("round"),
            slot=next_info.get("slot"),
            is_my_pick=bool(next_info.get("is_my_pick")),
            picks_until_mine=next_info.get("picks_until_mine"),
            total_picks=next_info.get("total_picks"),
            back_to_back=bool(next_info.get("back_to_back")),
            consecutive_picks=list(next_info.get("consecutive_picks") or []),
        ),
        starter_needs=starter_needs,
        board=board,
        bpa_top=bpa_top,
        need_top=need_top,
        value_pivot=value_pivot,
        timeline=timeline,
        strategy_notes=strategy_notes,
        adp_source=state._adp_index().source_label,
        fetched_at=datetime.now(timezone.utc),
        poll_seconds=poll_seconds,
    )
