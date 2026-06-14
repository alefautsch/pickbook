"""Resolve rookie-draft pick ownership from Sleeper traded_picks."""

from __future__ import annotations

from typing import Any

from dynasty_draft.sleeper_client import SleeperClient

PickOwnerKey = tuple[str, int, str]
PickOwnerIndex = dict[PickOwnerKey, str]


def _traded_pick_key(row: dict[str, Any]) -> PickOwnerKey | None:
    if not row.get("season") or row.get("round") is None or row.get("roster_id") is None:
        return None
    return (str(row["season"]), int(row["round"]), str(row["roster_id"]))


def collect_traded_picks(client: SleeperClient, league_id: str) -> list[dict[str, Any]]:
    """League traded_picks plus draft-level traded_picks (current season often on startup draft)."""
    merged: list[dict[str, Any]] = []
    seen: set[PickOwnerKey] = set()

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


def build_pick_owner_index(traded_picks: list[dict[str, Any]]) -> PickOwnerIndex:
    """Map (season, round, original_roster_id) → current owner roster id."""
    index: PickOwnerIndex = {}
    for row in traded_picks:
        season = row.get("season")
        round_no = row.get("round")
        original = row.get("roster_id")
        if season is None or round_no is None or original is None:
            continue
        key: PickOwnerKey = (str(season), int(round_no), str(original))
        index[key] = str(row.get("owner_id") or original)
    return index


def resolve_pick_owner(
    index: PickOwnerIndex,
    *,
    season: str,
    round_no: int,
    original_roster_id: int | str,
) -> int:
    """Owner for a franchise slot pick; defaults to original when not traded."""
    key: PickOwnerKey = (str(season), int(round_no), str(original_roster_id))
    owner = index.get(key)
    if owner is not None:
        return int(owner)
    return int(original_roster_id)
