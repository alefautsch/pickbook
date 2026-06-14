"""Sleeper draft pick inventory sync and trade-value assignment."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import delete, desc, inspect, select
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

from backend.api.settings import _read_settings
from backend.db.models import League, LeagueSnapshot, RosterDraftPick
from dynasty_draft.inseason_pick_values import (
    SlotTier,
    infer_slot_tier,
    pick_label,
    pick_slot_certainty,
    seasons_until,
    slot_in_round,
    value_pick,
)
from dynasty_draft.ktc_pick_slots import rookie_prospect_values
from dynasty_draft.ktc_values import KtcStore
from dynasty_draft.sleeper_client import SleeperClient
from dynasty_draft.war_data import WarData


def _draft_rounds(league_remote: dict[str, Any]) -> int:
    settings = league_remote.get("settings") or {}
    return int(settings.get("draft_rounds") or 3)


def _future_seasons(current_season: str | int, *, years: int = 3) -> list[str]:
    """Include the current league season (upcoming rookie draft) plus future years."""
    base = int(current_season)
    return [str(base + offset) for offset in range(years)]


def build_league_pick_inventory(
    *,
    league_remote: dict[str, Any],
    rosters: list[dict[str, Any]],
    traded_picks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Reconstruct who owns each future pick slot (Sleeper traded_picks model)."""
    draft_rounds = _draft_rounds(league_remote)
    seasons = _future_seasons(league_remote.get("season") or "2026")
    roster_ids = [str(row.get("roster_id")) for row in rosters if row.get("roster_id") is not None]

    defaults: list[dict[str, Any]] = []
    for season in seasons:
        for round_no in range(1, draft_rounds + 1):
            for roster_id in roster_ids:
                defaults.append(
                    {
                        "season": season,
                        "round": round_no,
                        "original_roster_id": roster_id,
                        "owner_roster_id": roster_id,
                    }
                )

    traded_keys = {
        (str(tp["season"]), int(tp["round"]), str(tp["roster_id"]))
        for tp in traded_picks
        if tp.get("season") and tp.get("round") is not None and tp.get("roster_id") is not None
    }

    inventory = [
        row
        for row in defaults
        if (row["season"], row["round"], row["original_roster_id"]) not in traded_keys
    ]

    for tp in traded_picks:
        if not tp.get("season") or tp.get("round") is None:
            continue
        inventory.append(
            {
                "season": str(tp["season"]),
                "round": int(tp["round"]),
                "original_roster_id": str(tp["roster_id"]),
                "owner_roster_id": str(tp.get("owner_id") or tp["roster_id"]),
            }
        )

    return inventory


def _traded_pick_key(tp: dict[str, Any]) -> tuple[str, int, str] | None:
    if not tp.get("season") or tp.get("round") is None or tp.get("roster_id") is None:
        return None
    return (str(tp["season"]), int(tp["round"]), str(tp["roster_id"]))


def collect_league_traded_picks(
    client: SleeperClient,
    league_id: str,
) -> list[dict[str, Any]]:
    """League traded_picks plus startup/rookie draft traded_picks (2026 lives here)."""
    merged: list[dict[str, Any]] = []
    seen: set[tuple[str, int, str]] = set()

    def _add(row: dict[str, Any]) -> None:
        key = _traded_pick_key(row)
        if key is None or key in seen:
            return
        seen.add(key)
        merged.append(
            {
                "season": str(row["season"]),
                "round": int(row["round"]),
                "roster_id": str(row["roster_id"]),
                "owner_id": str(row.get("owner_id") or row["roster_id"]),
            }
        )

    for tp in client.get_traded_picks(league_id):
        _add(tp)

    for draft in client.get_league_drafts(league_id):
        draft_id = draft.get("draft_id")
        if not draft_id:
            continue
        try:
            draft_traded = client._get(f"/draft/{draft_id}/traded_picks")
        except Exception:
            continue
        for tp in draft_traded or []:
            _add(tp)

    return merged


ROOKIE_PLAYER_TYPE = 1


def _rookie_draft_reversed() -> bool:
    from dynasty_draft.config import load_config

    config = load_config()
    return bool((config.get("strategy") or {}).get("rookie_draft_reversed", True))


def _startup_is_rookie_order() -> bool:
    """Direct startup→rookie mapping only when the rookie draft is not reversed."""
    return not _rookie_draft_reversed()


def _rookie_draft_status_by_season(
    client: SleeperClient,
    league_id: str,
) -> dict[str, str]:
    out: dict[str, str] = {}
    for draft in client.get_league_drafts(league_id):
        settings = draft.get("settings") or {}
        if int(settings.get("player_type", 0) or 0) != ROOKIE_PLAYER_TYPE:
            continue
        season = str(draft.get("season") or "")
        if season:
            out[season] = str(draft.get("status") or "")
    return out


def _league_is_pre_draft(league_remote: dict[str, Any]) -> bool:
    return (league_remote.get("status") or "").lower() in ("pre_draft", "drafting")


def pick_slot_by_roster(
    client: SleeperClient,
    league_id: str,
    *,
    season: str,
) -> tuple[dict[str, int], bool]:
    """Map roster_id → slot within round (1 = 1.01), matching Sleeper pick labels.

    Sleeper's traded_picks API only stores franchise slot + owner — not 1.01.
    The UI derives pick numbers from a draft's draft_order. We mirror that:

    1. Rookie / pick-allocation draft (player_type=1) with draft_order set → use directly
    2. Else completed startup draft (player_type=2) → apply reversal if configured
    """
    drafts = client.get_league_drafts(league_id)
    rosters = client.get_rosters(league_id)
    uid_to_rid = {
        str(r["owner_id"]): str(r["roster_id"])
        for r in rosters
        if r.get("owner_id") is not None and r.get("roster_id") is not None
    }

    def _slots_from_order(order: dict[str, Any]) -> dict[str, int]:
        out: dict[str, int] = {}
        for uid, slot in order.items():
            rid = uid_to_rid.get(str(uid))
            if rid is not None:
                out[rid] = int(slot)
        return out

    rookie_drafts = [
        d
        for d in drafts
        if str(d.get("season") or "") == str(season)
        and int((d.get("settings") or {}).get("player_type", 0) or 0) == ROOKIE_PLAYER_TYPE
        and d.get("type") in ("snake", "linear")
        and d.get("status") in ("complete", "pre_draft", "drafting")
        and d.get("draft_order")
    ]
    if rookie_drafts:
        order = rookie_drafts[0].get("draft_order") or {}
        slots = _slots_from_order(order)
        if slots:
            return slots, True

    startup_drafts = [
        d
        for d in drafts
        if int((d.get("settings") or {}).get("player_type", 0) or 0) == 2
        and d.get("type") in ("snake", "linear")
        and d.get("status") == "complete"
    ]
    if startup_drafts:
        draft = max(
            startup_drafts,
            key=lambda d: int((d.get("settings") or {}).get("rounds") or 0),
        )
        order = draft.get("draft_order") or {}
        slots = _slots_from_order(order)
        if slots:
            return slots, _startup_is_rookie_order()

    return {}, False


def startup_draft_slot_by_roster(
    client: SleeperClient,
    league_id: str,
) -> dict[str, int]:
    """Map roster_id → startup player-draft slot (1 = first pick in startup)."""
    drafts = client.get_league_drafts(league_id)
    player_drafts = [
        d
        for d in drafts
        if d.get("type") in ("snake", "linear")
        and d.get("status") in ("complete", "pre_draft", "drafting")
        and int((d.get("settings") or {}).get("player_type", 0) or 0) == 2
    ]
    if not player_drafts:
        return {}
    player_draft = max(
        player_drafts,
        key=lambda d: int((d.get("settings") or {}).get("rounds") or 0),
    )
    draft_order = player_draft.get("draft_order") or {}
    if not draft_order:
        return {}

    out: dict[str, int] = {}
    for roster in client.get_rosters(league_id):
        rid = roster.get("roster_id")
        uid = roster.get("owner_id")
        if rid is None or uid is None:
            continue
        slot = draft_order.get(str(uid))
        if slot is not None:
            out[str(rid)] = int(slot)
    return out


def _use_startup_slots_for_season(
    league_remote: dict[str, Any],
    pick_season: str,
    *,
    rookie_draft_statuses: dict[str, str] | None = None,
) -> bool:
    """Current-season picks follow startup order until the rookie draft completes."""
    current = str(league_remote.get("season") or "")
    if pick_season != current:
        return False
    status = (rookie_draft_statuses or {}).get(pick_season, "")
    return status != "complete"


def _contender_tier_by_roster(rankings_json: dict[str, Any] | None) -> dict[str, str]:
    if not rankings_json:
        return {}
    return {
        str(row.get("roster_id")): row.get("contender_tier") or "competitive"
        for row in rankings_json.get("by_dynasty") or []
        if row.get("roster_id") is not None
    }


def _dynasty_rank_by_roster(rankings_json: dict[str, Any] | None) -> dict[str, int]:
    if not rankings_json:
        return {}
    out: dict[str, int] = {}
    for row in rankings_json.get("by_dynasty") or []:
        rid = row.get("roster_id")
        rank = row.get("dynasty_rank")
        if rid is not None and rank is not None:
            out[str(rid)] = int(rank)
    return out


def _pick_slot_fields(
    *,
    league_remote: dict[str, Any],
    current_season: str,
    league_size: int,
    season: str,
    round_no: int,
    original_roster_id: str,
    owner_roster_id: str,
    rank_by_roster: dict[str, int],
    pick_slots: dict[str, int],
    pick_slots_direct: bool,
    rookie_draft_statuses: dict[str, str],
) -> tuple[SlotTier, int | None, str]:
    original_rank = rank_by_roster.get(original_roster_id)
    seasons_out = seasons_until(current_season, season)
    use_draft_slots = _use_startup_slots_for_season(
        league_remote,
        season,
        rookie_draft_statuses=rookie_draft_statuses,
    )
    draft_slot = pick_slots.get(original_roster_id) if use_draft_slots else None
    slot_is_direct = pick_slots_direct if use_draft_slots else False
    league_pre_draft = _league_is_pre_draft(league_remote)
    slot_tier = infer_slot_tier(
        original_rank,
        league_size=league_size,
        startup_draft_slot=draft_slot,
        startup_is_rookie_order=slot_is_direct,
    )
    slot_no = slot_in_round(
        original_rank,
        league_size=league_size,
        startup_draft_slot=draft_slot,
        startup_is_rookie_order=slot_is_direct,
    )
    certainty = pick_slot_certainty(
        is_own_slot=original_roster_id == owner_roster_id,
        seasons_out=seasons_out,
        league_pre_draft=league_pre_draft,
    )
    if use_draft_slots and slot_no is not None:
        certainty = "known"
    return slot_tier, slot_no, certainty


def _table_exists(db: Session, table_name: str) -> bool:
    bind = db.get_bind()
    return inspect(bind).has_table(table_name)


def _load_ktc_for_league(league_row: League | None) -> KtcStore | None:
    if league_row is None:
        return None
    try:
        return KtcStore.load(superflex=bool(league_row.superflex))
    except Exception:
        return None


def _load_war(db: Session) -> WarData:
    settings = _read_settings(db)
    return WarData(Path(str(settings.get("war_csv") or "war.csv")))


def _ktc_pick_lookup(store: KtcStore | None):
    if store is None:
        return None, None

    def _tier_lookup(season: str, round_no: int, slot_tier: SlotTier) -> float | None:
        value = store.lookup_pick(season, round_no, slot_tier)
        return float(value) if value is not None else None

    return _tier_lookup, store


def _ktc_slot_lookup(
    store: KtcStore | None,
    *,
    league_size: int,
    draft_rounds: int,
    current_season: str | int,
    rookie_values: list[float] | None,
):
    if store is None:
        return None

    def _lookup(season: str, round_no: int, slot_in_round: int) -> float | None:
        use_rookie = str(season) == str(current_season)
        value = store.slot_value(
            season,
            round_no,
            slot_in_round,
            league_size=league_size,
            rounds=draft_rounds,
            rookie_values=rookie_values,
            use_rookie_mode=use_rookie,
        )
        return float(value) if value is not None else None

    return _lookup


def sync_league_draft_picks(
    db: Session,
    league_id: str,
    *,
    client: SleeperClient | None = None,
    league_remote: dict[str, Any] | None = None,
    rosters_remote: list[dict[str, Any]] | None = None,
) -> int:
    """Pull Sleeper traded picks and persist valued inventory. Returns pick count."""
    client = client or SleeperClient()
    league_row = db.get(League, league_id)
    if league_row is None:
        return 0
    if not _table_exists(db, RosterDraftPick.__tablename__):
        return 0

    remote = league_remote or client.get_league(league_id)
    rosters = rosters_remote or client.get_rosters(league_id)
    traded = collect_league_traded_picks(client, league_id)

    inventory = build_league_pick_inventory(
        league_remote=remote,
        rosters=rosters,
        traded_picks=traded,
    )

    snap = db.scalar(
        select(LeagueSnapshot)
        .where(LeagueSnapshot.league_id == league_id)
        .order_by(desc(LeagueSnapshot.computed_at))
        .limit(1)
    )
    rank_by_roster = _dynasty_rank_by_roster(snap.rankings_json if snap else None)
    tier_by_roster = _contender_tier_by_roster(snap.rankings_json if snap else None)
    league_size = league_row.total_rosters or len(rosters) or 12
    current_season = league_row.season
    pick_slots, pick_slots_direct = pick_slot_by_roster(client, league_id, season=current_season)
    rookie_draft_statuses = _rookie_draft_status_by_season(client, league_id)
    draft_rounds = _draft_rounds(remote)
    ktc_store = _load_ktc_for_league(league_row)
    war = _load_war(db)
    rookie_values = rookie_prospect_values(
        war.players,
        ktc_lookup=ktc_store.lookup if ktc_store else None,
    )
    ktc_lookup, _ = _ktc_pick_lookup(ktc_store)
    ktc_slot_lookup = _ktc_slot_lookup(
        ktc_store,
        league_size=league_size,
        draft_rounds=draft_rounds,
        current_season=current_season,
        rookie_values=rookie_values,
    )

    db.execute(delete(RosterDraftPick).where(RosterDraftPick.league_id == league_id))

    count = 0
    for row in inventory:
        original_id = row["original_roster_id"]
        owner_id = row["owner_roster_id"]
        is_own = original_id == owner_id
        slot_tier, slot_no, certainty = _pick_slot_fields(
            league_remote=remote,
            current_season=current_season,
            league_size=league_size,
            season=row["season"],
            round_no=row["round"],
            original_roster_id=original_id,
            owner_roster_id=owner_id,
            rank_by_roster=rank_by_roster,
            pick_slots=pick_slots,
            pick_slots_direct=pick_slots_direct,
            rookie_draft_statuses=rookie_draft_statuses,
        )
        owner_tier = tier_by_roster.get(owner_id)
        seasons_out = seasons_until(current_season, row["season"])
        tv = value_pick(
            round_no=row["round"],
            slot_tier=slot_tier,
            seasons_out=seasons_out,
            slot_in_round_no=slot_no,
            is_own_slot=is_own,
            owner_contender_tier=owner_tier,
            slot_certainty=certainty,
            pick_season=row["season"],
            ktc_lookup=ktc_lookup,
            ktc_slot_lookup=ktc_slot_lookup,
            league_size=league_size,
        )
        label = pick_label(
            season=row["season"],
            round_no=row["round"],
            slot_tier=slot_tier,
            slot_in_round_no=slot_no,
            slot_certainty=certainty,
        )

        db.add(
            RosterDraftPick(
                league_id=league_id,
                owner_roster_id=row["owner_roster_id"],
                original_roster_id=original_id,
                season=row["season"],
                round=row["round"],
                slot_tier=slot_tier,
                trade_value=tv,
                label=label,
            )
        )
        count += 1

    return count


def get_roster_draft_picks(
    db: Session,
    league_id: str,
    roster_id: str,
) -> list[dict[str, Any]]:
    try:
        rows = db.scalars(
            select(RosterDraftPick)
            .where(
                RosterDraftPick.league_id == league_id,
                RosterDraftPick.owner_roster_id == roster_id,
            )
            .order_by(
                RosterDraftPick.season,
                RosterDraftPick.round,
                RosterDraftPick.original_roster_id,
            )
        ).all()
    except ProgrammingError:
        db.rollback()
        return []

    if not rows:
        return []

    league_row = db.get(League, league_id)
    league_size = (league_row.total_rosters if league_row else None) or 12
    current_season = league_row.season if league_row else rows[0].season

    snap = db.scalar(
        select(LeagueSnapshot)
        .where(LeagueSnapshot.league_id == league_id)
        .order_by(desc(LeagueSnapshot.computed_at))
        .limit(1)
    )
    rank_by_roster = _dynasty_rank_by_roster(snap.rankings_json if snap else None)
    tier_by_roster = _contender_tier_by_roster(snap.rankings_json if snap else None)

    client = SleeperClient()
    pick_slots, pick_slots_direct = pick_slot_by_roster(client, league_id, season=current_season)
    rookie_draft_statuses = _rookie_draft_status_by_season(client, league_id)
    league_remote: dict[str, Any] | None = None
    if league_row:
        try:
            league_remote = client.get_league(league_id)
        except Exception:
            league_remote = None
    if league_remote is None:
        league_remote = {"season": current_season, "status": "in_season"}

    ktc_store = _load_ktc_for_league(league_row)
    war = _load_war(db)
    draft_rounds = _draft_rounds(league_remote)
    rookie_values = rookie_prospect_values(
        war.players,
        ktc_lookup=ktc_store.lookup if ktc_store else None,
    )
    ktc_lookup, _ = _ktc_pick_lookup(ktc_store)
    ktc_slot_lookup = _ktc_slot_lookup(
        ktc_store,
        league_size=league_size,
        draft_rounds=draft_rounds,
        current_season=current_season,
        rookie_values=rookie_values,
    )

    out: list[dict[str, Any]] = []
    for row in rows:
        slot_tier, slot_no, certainty = _pick_slot_fields(
            league_remote=league_remote,
            current_season=current_season,
            league_size=league_size,
            season=row.season,
            round_no=row.round,
            original_roster_id=row.original_roster_id,
            owner_roster_id=row.owner_roster_id,
            rank_by_roster=rank_by_roster,
            pick_slots=pick_slots,
            pick_slots_direct=pick_slots_direct,
            rookie_draft_statuses=rookie_draft_statuses,
        )
        seasons_out = seasons_until(current_season, row.season)
        is_own = row.original_roster_id == row.owner_roster_id
        trade_value = value_pick(
            round_no=row.round,
            slot_tier=slot_tier,
            seasons_out=seasons_out,
            slot_in_round_no=slot_no,
            is_own_slot=is_own,
            owner_contender_tier=tier_by_roster.get(row.owner_roster_id),
            slot_certainty=certainty,
            pick_season=row.season,
            ktc_lookup=ktc_lookup,
            ktc_slot_lookup=ktc_slot_lookup,
            league_size=league_size,
        )
        label = pick_label(
            season=row.season,
            round_no=row.round,
            slot_tier=slot_tier,
            slot_in_round_no=slot_no,
            slot_certainty=certainty,
        )
        out.append(
            {
                "season": row.season,
                "round": row.round,
                "original_roster_id": row.original_roster_id,
                "owner_roster_id": row.owner_roster_id,
                "slot_tier": slot_tier,
                "slot_in_round": slot_no,
                "trade_value": trade_value,
                "label": label,
                "is_own_slot": is_own,
            }
        )
    return out
