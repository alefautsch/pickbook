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
    pool = state.blend_pool(state.available_players())
    return sorted(pool, key=lambda item: item[1].trade_value, reverse=True)


def _pick_for_team(
    state: DraftState,
    pool: list[tuple[str, PlayerValue]],
    roster_counts: Counter[str],
    targets: dict[str, int],
    round_no: int,
    max_tv: float,
) -> tuple[str, PlayerValue] | None:
    if not pool:
        return None
    adp_index = state._adp_index()
    best: tuple[str, PlayerValue] | None = None
    best_score = -1.0
    for player_id, player in pool:
        adp_norm = adp_index.adp_norm(
            player.name,
            fallback_tv=player.trade_value,
            max_tv=max_tv,
        )
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
    chosen = _pick_for_team(state, pool, roster_counts[roster_id], targets, round_no, max_tv)
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
        "age": state._player_age(player_id),
        "trade_value": player.trade_value,
        "is_me": roster_id == state.my_roster_id,
        "source": source,
    }
    return row, pool


def _plan_user_bookend_picks(
    state: DraftState,
    pick_numbers: list[int],
    pool: list[tuple[str, PlayerValue]],
    roster_counts: dict[int, Counter[str]],
    targets: dict[str, int],
    max_tv: float,
    *,
    prefer_recommendations: bool = False,
) -> tuple[list[dict[str, Any]], list[tuple[str, PlayerValue]]]:
    """Assume the user takes their top diversified picks at a bookend pair."""
    if state.my_roster_id is None or not pick_numbers:
        return [], pool

    planned: list[dict[str, Any]] = []
    used_positions: set[str] = set()
    my_counts = roster_counts[state.my_roster_id]
    dynasty_by_id = state.dynasty_scores(pool)

    for pick_no in pick_numbers:
        recs = (
            state.dynasty_recommendations(pool, pick_no=pick_no, limit=20)
            if prefer_recommendations
            else []
        )
        chosen: tuple[str, PlayerValue, dict[str, Any]] | None = None

        for candidate in recs:
            match = next((p for p in pool if p[0] == candidate["player_id"]), None)
            if not match:
                continue
            if len(pick_numbers) > 1 and candidate["pos"] in used_positions:
                continue
            chosen = (match[0], match[1], candidate)
            used_positions.add(candidate["pos"])
            break
        if chosen is None and len(pick_numbers) > 1 and used_positions:
            for candidate in recs:
                match = next((p for p in pool if p[0] == candidate["player_id"]), None)
                if match:
                    chosen = (match[0], match[1], candidate)
                    break

        if chosen is None:
            ranked = sorted(
                pool,
                key=lambda row: (dynasty_by_id.get(row[0]) or {}).get("dynasty_rating") or 0,
                reverse=True,
            )
            for player_id, player in ranked:
                if len(pick_numbers) > 1 and player.pos in used_positions:
                    continue
                dynasty = dynasty_by_id.get(player_id) or {}
                chosen = (
                    player_id,
                    player,
                    {
                        "dynasty_rating": dynasty.get("dynasty_rating"),
                        "adp_pick": state._adp_index().pick_no(player.name),
                    },
                )
                used_positions.add(player.pos)
                break
            if chosen is None and ranked:
                player_id, player = ranked[0]
                dynasty = dynasty_by_id.get(player_id) or {}
                chosen = (
                    player_id,
                    player,
                    {
                        "dynasty_rating": dynasty.get("dynasty_rating"),
                        "adp_pick": state._adp_index().pick_no(player.name),
                    },
                )
                used_positions.add(player.pos)

        if chosen is None:
            break

        player_id, player, meta = chosen
        pool = [p for p in pool if p[0] != player_id]
        my_counts[player.pos] += 1
        dynasty = dynasty_by_id.get(player_id) or {}
        planned.append(
            {
                "pick_no": pick_no,
                "team": _team_name(state, state.my_roster_id),
                "name": player.name,
                "pos": player.pos,
                "age": state._player_age(player_id),
                "trade_value": player.trade_value,
                "dynasty_rating": meta.get("dynasty_rating") or dynasty.get("dynasty_rating"),
                "adp_pick": meta.get("adp_pick") or state._adp_index().pick_no(player.name),
                "source": "projected_you_dynasty",
            }
        )

    return planned, pool


def _bookend_from(state: DraftState, from_pick: int) -> list[int]:
    return state.consecutive_pick_numbers(from_pick=from_pick)


def _targets_snapshot(
    state: DraftState,
    pool: list[tuple[str, PlayerValue]],
    limit: int = 12,
) -> list[dict[str, Any]]:
    dynasty_by_id = state.dynasty_scores(pool)
    ranked = sorted(
        pool,
        key=lambda row: (dynasty_by_id.get(row[0]) or {}).get("dynasty_rating") or 0,
        reverse=True,
    )
    adp = state._adp_index()
    rows: list[dict[str, Any]] = []
    for player_id, player in ranked[:limit]:
        dynasty = dynasty_by_id.get(player_id) or {}
        rows.append(
            {
                "name": player.name,
                "pos": player.pos,
                "age": state._player_age(player_id),
                "trade_value": player.trade_value,
                "dynasty_rating": dynasty.get("dynasty_rating"),
                "adp_pick": adp.pick_no(player.name),
            }
        )
    return rows


def project_next_picks(
    state: DraftState,
    *,
    num_picks: int = PROJECTION_PICKS,
    assume_user_recommendations: bool = True,
) -> dict[str, Any]:
    """
    Bookend-centric projection:
    1) Picks before your current bookend
    2) You take your planned pair at the current bookend
    3) League picks until your next bookend
    4) You take your planned pair at the next bookend
    """
    start_pick = len(state.picks) + 1
    current_bookend = _bookend_from(state, start_pick)
    next_bookend = (
        _bookend_from(state, current_bookend[-1] + 1) if current_bookend else []
    )

    pool = _available_pool(state)
    roster_counts = _initial_roster_counts(state)
    targets = _target_needs(state)
    max_tv = pool[0][1].trade_value if pool else 1.0

    picks_before_current: list[dict[str, Any]] = []
    current_planned: list[dict[str, Any]] = []
    between_projected: list[dict[str, Any]] = []
    next_planned: list[dict[str, Any]] = []

    if current_bookend and state.my_roster_id is not None:
        for pick_no in range(start_pick, current_bookend[0]):
            row, pool = _simulate_pick(
                state,
                pick_no,
                pool,
                roster_counts,
                targets,
                max_tv,
                source="before_current_bookend",
            )
            if row:
                picks_before_current.append(row)

        current_planned, pool = _plan_user_bookend_picks(
            state,
            current_bookend,
            pool,
            roster_counts,
            targets,
            max_tv,
            prefer_recommendations=assume_user_recommendations,
        )

        if next_bookend:
            after_current = current_bookend[-1] + 1
            for pick_no in range(after_current, next_bookend[0]):
                row, pool = _simulate_pick(
                    state,
                    pick_no,
                    pool,
                    roster_counts,
                    targets,
                    max_tv,
                    source="between_bookends",
                )
                if row:
                    between_projected.append(row)

            next_planned, pool = _plan_user_bookend_picks(
                state,
                next_bookend,
                pool,
                roster_counts,
                targets,
                max_tv,
                prefer_recommendations=True,
            )
        else:
            sim_start = current_bookend[-1] + 1
            for pick_no in range(sim_start, sim_start + num_picks):
                row, pool = _simulate_pick(state, pick_no, pool, roster_counts, targets, max_tv)
                if row is None:
                    break
                between_projected.append(row)
    else:
        for pick_no in range(start_pick, start_pick + num_picks):
            row, pool = _simulate_pick(state, pick_no, pool, roster_counts, targets, max_tv)
            if row is None:
                break
            between_projected.append(row)

    gone_between = [
        {"name": row["name"], "pos": row["pos"], "trade_value": row["trade_value"]}
        for row in between_projected
    ]
    targets_next = _targets_snapshot(state, pool, limit=15)

    return {
        "method": "bookend_pairs_league_tv_sim_user_dynasty_planned",
        "adp_weight": _ADP_WEIGHT,
        "need_weight": _NEED_WEIGHT,
        "adp_source": state._adp_index().source_label,
        "current_bookend": {
            "pick_numbers": current_bookend,
            "picks_before": picks_before_current,
            "planned_picks": current_planned,
        },
        "between_bookends": {
            "from_pick": between_projected[0]["pick_no"] if between_projected else None,
            "through_pick": between_projected[-1]["pick_no"] if between_projected else None,
            "projected_picks": between_projected,
            "likely_off_board": gone_between,
        },
        "next_bookend": {
            "pick_numbers": next_bookend,
            "planned_picks": next_planned,
            "targets_at_bookend": targets_next,
            "likely_gone_before": gone_between,
        },
        # Legacy fields consumed by UI / older prompt text
        "picks_before_your_turn": picks_before_current,
        "user_hypothetical_picks": current_planned,
        "simulated_from_pick": (
            between_projected[0]["pick_no"] if between_projected else (current_bookend[-1] + 1 if current_bookend else start_pick)
        ),
        "simulated_through_pick": (
            between_projected[-1]["pick_no"] if between_projected else start_pick - 1
        ),
        "your_next_pick_after_window": next_bookend[0] if next_bookend else None,
        "projected_picks": between_projected,
        "projected_off_board": gone_between,
        "still_available_top_after_window": _targets_snapshot(state, pool, limit=25),
    }
