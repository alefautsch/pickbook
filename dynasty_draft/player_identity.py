"""Resolve duplicate Sleeper players that share a war.csv name."""

from __future__ import annotations

from typing import TYPE_CHECKING

from dynasty_draft.war_data import PlayerValue, normalize_name

if TYPE_CHECKING:
    from dynasty_draft.recommender import DraftState


def snapshot_identity_score(
    *,
    dynasty_rookie: bool = False,
    years_exp: int | None = None,
    position: str | None = None,
    nfl_team: str | None = None,
    sleeper_position: str | None = None,
    sleeper_team: str | None = None,
) -> int:
    score = 0
    spos = (sleeper_position or position or "").upper()
    pos = (position or "").upper()
    if spos and pos and spos == pos:
        score += 10
    steam = (sleeper_team or "").upper()
    team = (nfl_team or "").upper()
    if steam and team and steam == team:
        score += 5
    if dynasty_rookie:
        score += 5
    if years_exp is not None and years_exp == 0:
        score += 3
    return score


def sleeper_identity_score(
    state: DraftState,
    player_id: str,
    war_player: PlayerValue | None = None,
) -> int:
    sleeper = state.sleeper_players.get(player_id) or {}
    war_player = war_player or state._match_war(player_id)
    return snapshot_identity_score(
        dynasty_rookie=state._is_rookie(player_id),
        years_exp=state._years_exp(player_id),
        position=war_player.pos if war_player else None,
        nfl_team=war_player.team if war_player else None,
        sleeper_position=sleeper.get("position"),
        sleeper_team=sleeper.get("team"),
    )


def pick_best_player_id(
    state: DraftState,
    player_ids: list[str],
    *,
    war_by_id: dict[str, PlayerValue] | None = None,
) -> str | None:
    best_id: str | None = None
    best_score = -1
    for player_id in player_ids:
        war_player = (war_by_id or {}).get(player_id) or state._match_war(player_id)
        if war_player is None:
            continue
        score = sleeper_identity_score(state, player_id, war_player)
        if score > best_score:
            best_score = score
            best_id = player_id
    return best_id


def group_player_ids_by_name(
    state: DraftState,
    player_ids: list[str],
) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {}
    for player_id in player_ids:
        name = normalize_name(state.sleeper_players.get(player_id, {}).get("full_name") or "")
        if not name:
            continue
        groups.setdefault(name, []).append(player_id)
    return groups
