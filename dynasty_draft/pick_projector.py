from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from dynasty_draft.draft_context import _team_display_name
from dynasty_draft.recommender import DraftState
from dynasty_draft.war_data import POSITIONS, PlayerValue

PROJECTION_PICKS = 18

_BASE_NEEDS = {"QB": 2, "RB": 2, "WR": 3, "TE": 1}
_NEED_WEIGHT = 0.35
_ADP_WEIGHT = 0.65


def _roster_id_for_slot(state: DraftState, slot: int) -> int | None:
    roster_id = (state.draft.get("slot_to_roster_id") or {}).get(str(slot))
    return int(roster_id) if roster_id is not None else None


def _roster_id_for_pick(state: DraftState, pick_no: int) -> int | None:
    return _roster_id_for_slot(state, state._pick_slot(pick_no))


def _team_name(state: DraftState, roster_id: int) -> str:
    users_by_id = {str(u.get("user_id")): u for u in (state.league_users or [])}
    draft_order = state.draft.get("draft_order") or {}
    slot_to_roster = state.draft.get("slot_to_roster_id") or {}
    roster_to_user: dict[int, str] = {}
    for user_id, slot in draft_order.items():
        rid = slot_to_roster.get(str(slot))
        if rid is not None:
            roster_to_user[int(rid)] = str(user_id)
    user = users_by_id.get(roster_to_user.get(roster_id, ""))
    return _team_display_name(user, roster_id)


def _initial_roster_counts(state: DraftState) -> dict[int, Counter[str]]:
    counts: dict[int, Counter[str]] = defaultdict(Counter)
    for pick in state.picks:
        if not pick.get("player_id"):
            continue
        roster_id = int(pick.get("roster_id", 0))
        pos = ((pick.get("metadata") or {}).get("position") or "").upper()
        if pos in POSITIONS:
            counts[roster_id][pos] += 1
    return counts


def _target_needs(state: DraftState) -> dict[str, int]:
    targets = dict(_BASE_NEEDS)
    if not state.is_superflex():
        targets["QB"] = 1
    qb_slots = sum(1 for p in state.roster_positions if p == "QB")
    sflex = sum(1 for p in state.roster_positions if p == "SUPER_FLEX")
    targets["QB"] = max(targets["QB"], qb_slots + sflex)
    targets["RB"] = max(targets["RB"], sum(1 for p in state.roster_positions if p == "RB"))
    targets["WR"] = max(targets["WR"], sum(1 for p in state.roster_positions if p == "WR"))
    targets["TE"] = max(targets["TE"], sum(1 for p in state.roster_positions if p == "TE"))
    return targets


def _need_boost(pos: str, roster_counts: Counter[str], targets: dict[str, int], round_no: int) -> float:
    gap = max(0, targets.get(pos, 0) - roster_counts.get(pos, 0))
    if gap == 0:
        return 0.0
    weight = 0.12
    if pos == "QB":
        weight = 0.18 if round_no <= 8 else 0.12
    elif pos == "RB":
        weight = 0.14 if round_no <= 4 else 0.08
    elif pos == "WR":
        weight = 0.10
    elif pos == "TE":
        weight = 0.11
    return gap * weight


def _available_pool(state: DraftState) -> list[tuple[str, PlayerValue]]:
    return sorted(state.available_players(), key=lambda item: item[1].trade_value, reverse=True)


def _pick_for_team(
    pool: list[tuple[str, PlayerValue]],
    roster_counts: Counter[str],
    targets: dict[str, int],
    round_no: int,
    max_tv: float,
) -> tuple[str, PlayerValue] | None:
    if not pool:
        return None
    best: tuple[str, PlayerValue] | None = None
    best_score = -1.0
    for player_id, player in pool:
        adp_norm = player.trade_value / max_tv if max_tv else 0.0
        need = _need_boost(player.pos, roster_counts, targets, round_no)
        score = _ADP_WEIGHT * adp_norm + _NEED_WEIGHT * need
        if score > best_score:
            best_score = score
            best = (player_id, player)
    return best


def _simulate_pick(
    state: DraftState,
    pick_no: int,
    pool: list[tuple[str, PlayerValue]],
    roster_counts: dict[int, Counter[str]],
    targets: dict[str, int],
    max_tv: float,
    *,
    source: str = "projected",
) -> tuple[dict[str, Any] | None, list[tuple[str, PlayerValue]]]:
    roster_id = _roster_id_for_pick(state, pick_no)
    if roster_id is None:
        return None, pool
    round_no = (pick_no - 1) // state._teams() + 1
    chosen = _pick_for_team(pool, roster_counts[roster_id], targets, round_no, max_tv)
    if chosen is None:
        return None, pool
    player_id, player = chosen
    pool = [p for p in pool if p[0] != player_id]
    roster_counts[roster_id][player.pos] += 1
    row = {
        "pick_no": pick_no,
        "team": _team_name(state, roster_id),
        "roster_id": roster_id,
        "name": player.name,
        "pos": player.pos,
        "trade_value": player.trade_value,
        "is_me": roster_id == state.my_roster_id,
        "source": source,
    }
    return row, pool


def _next_user_pick_after(state: DraftState, from_pick: int) -> int | None:
    total = state._teams() * state._rounds()
    my_slot = state.my_slot
    if my_slot is None:
        return None
    for pick_no in range(from_pick, total + 1):
        if state._pick_slot(pick_no) == my_slot:
            return pick_no
    return None


def project_next_picks(
    state: DraftState,
    *,
    num_picks: int = PROJECTION_PICKS,
    assume_user_recommendations: bool = True,
) -> dict[str, Any]:
    """
    Simulate picks before user's turn, user's bookend (hypothetical), then the next
    `num_picks` for the rest of the league. ADP = trade value; blended with team needs.
    """
    start_pick = len(state.picks) + 1
    consecutive = state.consecutive_pick_numbers(from_pick=start_pick)

    pool = _available_pool(state)
    roster_counts = _initial_roster_counts(state)
    targets = _target_needs(state)
    max_tv = pool[0][1].trade_value if pool else 1.0

    picks_before_user: list[dict[str, Any]] = []
    user_hypothetical: list[dict[str, Any]] = []

    if consecutive and state.my_roster_id is not None:
        for pick_no in range(start_pick, consecutive[0]):
            row, pool = _simulate_pick(
                state, pick_no, pool, roster_counts, targets, max_tv, source="before_your_turn"
            )
            if row:
                picks_before_user.append(row)

        recs = state.recommend(limit=12) if assume_user_recommendations else []
        used_positions: set[str] = set()
        for pick_no in consecutive:
            chosen: tuple[str, PlayerValue] | None = None
            if assume_user_recommendations:
                for candidate in recs:
                    match = next((p for p in pool if p[0] == candidate["player_id"]), None)
                    if not match:
                        continue
                    if used_positions and candidate["pos"] in used_positions and len(consecutive) > 1:
                        continue
                    chosen = match
                    used_positions.add(candidate["pos"])
                    break
            if chosen is None:
                round_no = (pick_no - 1) // state._teams() + 1
                chosen = _pick_for_team(pool, roster_counts[state.my_roster_id], targets, round_no, max_tv)
            if chosen is None:
                break
            player_id, player = chosen
            pool = [p for p in pool if p[0] != player_id]
            roster_counts[state.my_roster_id][player.pos] += 1
            user_hypothetical.append(
                {
                    "pick_no": pick_no,
                    "team": _team_name(state, state.my_roster_id),
                    "name": player.name,
                    "pos": player.pos,
                    "trade_value": player.trade_value,
                    "source": "projected_you",
                }
            )
        sim_start = consecutive[-1] + 1
    elif state.next_pick_info().get("is_my_pick") and state.my_roster_id is not None:
        sim_start = start_pick + 1
    else:
        sim_start = start_pick

    projected: list[dict[str, Any]] = []
    for pick_no in range(sim_start, sim_start + num_picks):
        row, pool = _simulate_pick(state, pick_no, pool, roster_counts, targets, max_tv)
        if row is None:
            break
        projected.append(row)

    next_user_pick = _next_user_pick_after(state, sim_start + len(projected))
    gone_names = {row["name"] for row in projected}
    likely_gone = [
        {"name": row["name"], "pos": row["pos"], "trade_value": row["trade_value"]}
        for row in projected
    ]

    return {
        "method": "trade_value_adp_plus_team_needs",
        "adp_weight": _ADP_WEIGHT,
        "need_weight": _NEED_WEIGHT,
        "picks_before_your_turn": picks_before_user,
        "user_hypothetical_picks": user_hypothetical,
        "simulated_from_pick": sim_start,
        "simulated_through_pick": projected[-1]["pick_no"] if projected else sim_start - 1,
        "your_next_pick_after_window": next_user_pick,
        "projected_picks": projected,
        "projected_off_board": likely_gone,
        "still_available_top_after_window": [
            {"name": p[1].name, "pos": p[1].pos, "trade_value": p[1].trade_value} for p in pool[:25]
        ],
    }
