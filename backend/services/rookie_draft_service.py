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
)
from backend.services.read_service import headshot_url, ovr_tier
from dynasty_draft.config import load_config
from dynasty_draft.draft_context import build_draft_timeline, build_scoring_context
from dynasty_draft.dynasty_score import DynastyRatingCurve, DynastyWeights
from dynasty_draft.external_adp import AdpStore
from dynasty_draft.healthy_ppg import HealthyPpgStore
from dynasty_draft.ktc_values import KtcStore
from dynasty_draft.projections import SleeperProjectionStore
from dynasty_draft.recommender import DraftState
from dynasty_draft.sleeper_client import SleeperClient
from dynasty_draft.strategy import DraftStrategy
from dynasty_draft.trade_value_blend import TradeValueBlend
from dynasty_draft.worp_blend import WorpBlend
from dynasty_draft.war_data import POSITIONS, PlayerValue, WarData

ROOKIE_PLAYER_TYPE = 1
DEFAULT_POLL_SECONDS = 20


class RookieDraftState(DraftState):
    """Rookie board pool = rookies only; OVR anchors = full universe (§5.7, same as LeagueScoringState)."""

    def _universe_pool(self) -> list[tuple[str, PlayerValue]]:
        pool: list[tuple[str, PlayerValue]] = []
        for player_id, sleeper_player in self.sleeper_players.items():
            pos = (sleeper_player.get("position") or "").upper()
            if pos not in POSITIONS:
                continue
            war_player = self._match_war(str(player_id))
            if war_player is None:
                continue
            if self.blended_trade_value(war_player) <= 0:
                continue
            pool.append((str(player_id), war_player))
        return pool

    def _dynasty_reference_pool(self) -> list[tuple[str, PlayerValue]]:
        """Fixed anchors from the full player universe — not the rookie sub-pool."""
        return self._universe_pool()


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


def build_rookie_draft_state(
    *,
    draft: dict[str, Any],
    picks: list[dict[str, Any]],
    league_row: League,
    league_users: list[dict[str, Any]],
    user_id: str,
    settings: dict[str, Any],
    client: SleeperClient,
) -> RookieDraftState:
    war_path = Path(str(settings.get("war_csv", "war.csv")))
    if not war_path.exists():
        raise FileNotFoundError(f"Missing WAR file: {war_path}")

    players = client.get_players()
    war = WarData(war_path)
    strategy = _load_strategy(settings)

    league_dict = {
        "league_id": league_row.sleeper_league_id,
        "name": league_row.name,
        "season": league_row.season,
        "total_rosters": league_row.total_rosters,
        "roster_positions": league_row.roster_positions_json,
        "scoring_settings": league_row.scoring_json,
    }

    state = RookieDraftState(
        draft=draft,
        picks=picks,
        league=league_dict,
        league_users=league_users,
        user_id=user_id,
        war=war,
        sleeper_players=players,
        trade_weight=float(settings.get("trade_weight", 0.65)),
        worp_weight=float(settings.get("worp_weight", 0.35)),
        dynasty_weights=DynastyWeights.from_config(settings.get("dynasty_weights")),
        dynasty_rating_curve=DynastyRatingCurve.from_config(settings.get("dynasty_rating_curve")),
        strategy=strategy,
    )

    if settings.get("ktc_enabled", True):
        try:
            state.ktc = KtcStore.load(superflex=state.is_superflex())
        except Exception:
            state.ktc = None
    state.trade_blend = TradeValueBlend.from_config(settings, ktc_available=state.ktc is not None)
    state.worp_blend = WorpBlend.from_config(settings)

    config = load_config()
    try:
        state.adp_store = AdpStore.load(config, superflex=state.is_superflex())
    except Exception:
        state.adp_store = None

    try:
        scoring = build_scoring_context(state)
        state.projection_store = SleeperProjectionStore.load(
            client,
            season=str(settings.get("season", league_row.season)),
            teams=state._teams(),
            roster_positions=state.roster_positions,
            superflex=state.is_superflex(),
            ppr=float(scoring.get("ppr", 0.5)),
            war=war,
            sleeper_players=players,
        )
    except Exception:
        state.projection_store = None

    try:
        scoring = build_scoring_context(state)
        state.healthy_ppg_store = HealthyPpgStore.load(
            sleeper_players=players,
            war=war,
            teams=state._teams(),
            roster_positions=state.roster_positions,
            superflex=state.is_superflex(),
            ppr=float(scoring.get("ppr", 0.5)),
        )
    except Exception:
        state.healthy_ppg_store = None

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


def _timeline_rows(state: DraftState) -> list[RookieDraftTimelineRow]:
    raw = build_draft_timeline(state, past=None, upcoming=None)
    rows: list[RookieDraftTimelineRow] = []
    for row in raw:
        ovr = row.get("dynasty_rating")
        rows.append(
            RookieDraftTimelineRow(
                pick_no=int(row["pick_no"]),
                round=row.get("round"),
                team_name=row.get("team"),
                player_id=str(row["player_id"]) if row.get("player_id") else None,
                player_name=row.get("name") or None,
                position=row.get("pos") or None,
                ovr=int(ovr) if ovr is not None else None,
                dynasty_rookie=bool(row.get("dynasty_rookie")),
                status=str(row.get("status") or "done"),
                is_me=bool(row.get("is_me")),
            )
        )
    return rows


def get_rookie_draft_view(
    db: Session,
    league_id: str,
    *,
    draft_id: str | None = None,
    roster_id: str | None = None,
    client: SleeperClient | None = None,
) -> RookieDraftView | None:
    league_row = db.get(League, league_id)
    if league_row is None:
        return None

    settings = _read_settings(db)
    username = (settings.get("sleeper_username") or "").strip()
    if not username:
        raise ValueError("sleeper_username not configured in settings")

    client = client or SleeperClient()
    user = client.get_user(username)
    user_id = str(user["user_id"])

    resolved_draft_id = resolve_rookie_draft_id(client, league_id, override=draft_id)
    if not resolved_draft_id:
        return None

    draft = client.get_draft(resolved_draft_id)
    picks = client.get_draft_picks(resolved_draft_id)
    league_users = client.get_league_users(league_id)

    state = build_rookie_draft_state(
        draft=draft,
        picks=picks,
        league_row=league_row,
        league_users=league_users,
        user_id=user_id,
        settings=settings,
        client=client,
    )

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
    timeline = _timeline_rows(state)
    clock_row = next((row for row in timeline if row.status == "on_clock"), None)

    on_clock_roster_id: str | None = None
    pick_no = next_info.get("pick_no")
    if pick_no is not None:
        slot = state._pick_slot(int(pick_no))
        rid = (draft.get("slot_to_roster_id") or {}).get(str(slot))
        if rid is not None:
            on_clock_roster_id = str(rid)

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
    board = [_board_row_from_bpa(row, idx + 1) for idx, row in enumerate(bpa_all)]
    bpa_top = board[:15]

    teams = state._teams()
    rounds = state._rounds()
    total_picks = teams * rounds
    picks_made = len(picks)

    config = load_config()
    poll_seconds = int(config.get("poll_seconds", DEFAULT_POLL_SECONDS))

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
        timeline=timeline,
        strategy_notes=state.strategy.strategy_notes(state.war, tv_fn=state.blended_trade_value),
        adp_source=state._adp_index().source_label,
        fetched_at=datetime.now(timezone.utc),
        poll_seconds=poll_seconds,
    )
