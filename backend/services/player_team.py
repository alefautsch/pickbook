"""Resolve NFL team abbreviations when Sleeper / war.csv are stale or empty."""

from __future__ import annotations

from typing import Any, Protocol


class _WarTeam(Protocol):
    team: str | None
    name: str | None


def resolve_nfl_team(
    *,
    player_id: str,
    sleeper: dict[str, Any] | None = None,
    war_player: _WarTeam | None = None,
    healthy_ppg_store: Any | None = None,
    opportunity_store: Any | None = None,
    player_name: str | None = None,
) -> str | None:
    """Sleeper → war.csv → nflverse (healthy PPG / opportunity caches)."""
    sleeper = sleeper or {}
    st = (sleeper.get("team") or "").strip().upper()
    if st:
        return st

    if war_player and war_player.team:
        wt = str(war_player.team).strip().upper()
        if wt:
            return wt

    name = player_name
    if not name and war_player and war_player.name:
        name = war_player.name
    if not name:
        name = sleeper.get("full_name")

    if healthy_ppg_store is not None:
        row = healthy_ppg_store.lookup(str(player_id), name=name)
        if row is not None:
            team = getattr(row, "nfl_team", None)
            if team:
                return str(team).strip().upper()

    if opportunity_store is not None:
        row = opportunity_store.lookup(str(player_id), name=name)
        if row is not None:
            team = getattr(row, "nfl_team", None)
            if team:
                return str(team).strip().upper()

    return None
