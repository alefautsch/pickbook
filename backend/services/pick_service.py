"""Sleeper draft pick inventory sync and trade-value assignment."""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete, desc, inspect, select
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

from backend.db.models import League, LeagueSnapshot, RosterDraftPick
from dynasty_draft.inseason_pick_values import (
    infer_slot_tier,
    pick_label,
    seasons_until,
    slot_in_round,
    value_pick,
)
from dynasty_draft.sleeper_client import SleeperClient


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


def _table_exists(db: Session, table_name: str) -> bool:
    bind = db.get_bind()
    return inspect(bind).has_table(table_name)


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
    traded = client.get_traded_picks(league_id)

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
    league_size = league_row.total_rosters or len(rosters) or 12
    current_season = league_row.season

    db.execute(delete(RosterDraftPick).where(RosterDraftPick.league_id == league_id))

    count = 0
    for row in inventory:
        original_id = row["original_roster_id"]
        original_rank = rank_by_roster.get(original_id)
        slot_tier = infer_slot_tier(original_rank, league_size=league_size)
        slot_no = slot_in_round(original_rank, league_size=league_size)
        seasons_out = seasons_until(current_season, row["season"])
        tv = value_pick(
            round_no=row["round"],
            slot_tier=slot_tier,
            seasons_out=seasons_out,
            slot_in_round_no=slot_no,
        )
        label = pick_label(
            season=row["season"],
            round_no=row["round"],
            slot_tier=slot_tier,
            slot_in_round_no=slot_no,
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

    league_row = db.get(League, league_id)
    league_size = (league_row.total_rosters if league_row else None) or 12

    snap = db.scalar(
        select(LeagueSnapshot)
        .where(LeagueSnapshot.league_id == league_id)
        .order_by(desc(LeagueSnapshot.computed_at))
        .limit(1)
    )
    rank_by_roster = _dynasty_rank_by_roster(snap.rankings_json if snap else None)

    return [
        {
            "season": row.season,
            "round": row.round,
            "original_roster_id": row.original_roster_id,
            "owner_roster_id": row.owner_roster_id,
            "slot_tier": row.slot_tier,
            "slot_in_round": slot_in_round(
                rank_by_roster.get(row.original_roster_id),
                league_size=league_size,
            ),
            "trade_value": row.trade_value,
            "label": row.label,
            "is_own_slot": row.original_roster_id == row.owner_roster_id,
        }
        for row in rows
    ]
