from __future__ import annotations

from copy import deepcopy
from typing import Any

from dynasty_draft.pick_projector import (
    _available_pool,
    _initial_roster_counts,
    _simulate_pick,
    _target_needs,
)
from dynasty_draft.recommender import DraftState

# Startup pick trades are almost always even (2-for-2, 3-for-3).
COMMON_SWAP_SIZES = (2, 3)


def pick_label(state: DraftState, pick_no: int) -> str:
    teams = state._teams()
    round_no = (pick_no - 1) // teams + 1
    pos_in_round = (pick_no - 1) % teams + 1
    return f"{round_no}.{pos_in_round:02d}"


def pick_no_from_round_position(state: DraftState, round_no: int, pos_in_round: int) -> int:
    teams = state._teams()
    return (round_no - 1) * teams + pos_in_round


def my_pick_in_round(state: DraftState, round_no: int) -> int | None:
    if state.my_slot is None:
        return None
    teams = state._teams()
    slot = state.my_slot
    if round_no % 2 == 1:
        return (round_no - 1) * teams + slot
    return round_no * teams - slot + 1


def slot_pick_schedule(state: DraftState, slot: int) -> list[dict[str, Any]]:
    teams = state._teams()
    rounds = state._rounds()
    rows: list[dict[str, Any]] = []
    for round_no in range(1, rounds + 1):
        if round_no % 2 == 1:
            pick_no = (round_no - 1) * teams + slot
        else:
            pick_no = round_no * teams - slot + 1
        rows.append(
            {
                "pick_no": pick_no,
                "round": round_no,
                "slot": slot,
                "label": pick_label(state, pick_no),
            }
        )
    return rows


def _simulate_through(
    state: DraftState,
    through_pick: int,
) -> list[tuple[str, Any]]:
    start = len(state.picks) + 1
    pool = _available_pool(state)
    roster_counts = _initial_roster_counts(state)
    targets = _target_needs(state)
    max_tv = pool[0][1].trade_value if pool else 1.0
    for pick_no in range(start, through_pick):
        _, pool = _simulate_pick(state, pick_no, pool, roster_counts, targets, max_tv)
    return pool


def project_pick_value(state: DraftState, pick_no: int) -> dict[str, Any]:
    """Project best available player (by ADP+needs sim) at a future pick."""
    if pick_no <= len(state.picks):
        return {
            "pick_no": pick_no,
            "label": pick_label(state, pick_no),
            "status": "completed",
            "expected_player": None,
            "expected_tv": 0.0,
            "expected_worp": None,
        }

    pool = _simulate_through(state, pick_no)
    if not pool:
        return {
            "pick_no": pick_no,
            "label": pick_label(state, pick_no),
            "status": "future",
            "expected_player": None,
            "expected_tv": 0.0,
            "expected_worp": None,
        }

    roster_counts = deepcopy(_initial_roster_counts(state))
    targets = _target_needs(state)
    max_tv = pool[0][1].trade_value if pool else 1.0
    row, _ = _simulate_pick(state, pick_no, pool, roster_counts, targets, max_tv, source="pick_value")
    bookend = pick_no in _bookend_picks(state)
    if not row:
        player_id, top = pool[0]
        return {
            "pick_no": pick_no,
            "label": pick_label(state, pick_no),
            "status": "future",
            "expected_player": top.name,
            "expected_pos": top.pos,
            "expected_age": state._player_age(player_id),
            "expected_tv": top.trade_value,
            "expected_worp": top.worp,
            "is_bookend": bookend,
        }
    return {
        "pick_no": pick_no,
        "label": pick_label(state, pick_no),
        "status": "future",
        "expected_player": row["name"],
        "expected_pos": row["pos"],
        "expected_age": row.get("age"),
        "expected_tv": row["trade_value"],
        "expected_worp": None,
        "is_bookend": bookend,
    }


def _bookend_picks(state: DraftState) -> set[int]:
    if state.my_slot is None:
        return set()
    bookends: set[int] = set()
    streak: list[int] = []
    for pick_no in range(1, state._teams() * state._rounds() + 1):
        if state._pick_slot(pick_no) == state.my_slot:
            streak.append(pick_no)
        elif streak:
            if len(streak) >= 2:
                bookends.update(streak)
            streak = []
    if len(streak) >= 2:
        bookends.update(streak)
    return bookends


def build_my_future_pick_values(state: DraftState) -> list[dict[str, Any]]:
    if state.my_slot is None:
        return []
    current = len(state.picks) + 1
    rows: list[dict[str, Any]] = []
    for row in slot_pick_schedule(state, state.my_slot):
        if row["pick_no"] < current:
            continue
        projected = project_pick_value(state, row["pick_no"])
        rows.append({**row, **projected})
    return rows


def evaluate_pick_swap(
    state: DraftState,
    give_pick_nos: list[int],
    receive_pick_nos: list[int],
) -> dict[str, Any]:
    give_rows = [project_pick_value(state, pick_no) for pick_no in give_pick_nos]
    receive_rows = [project_pick_value(state, pick_no) for pick_no in receive_pick_nos]
    give_tv = sum(row.get("expected_tv") or 0 for row in give_rows)
    receive_tv = sum(row.get("expected_tv") or 0 for row in receive_rows)
    return {
        "give": give_rows,
        "receive": receive_rows,
        "give_total_tv": give_tv,
        "receive_total_tv": receive_tv,
        "net_tv": receive_tv - give_tv,
        "is_balanced_count": len(give_pick_nos) == len(receive_pick_nos),
        "pick_count_note": (
            "Startup pick trades are usually even (2-for-2, 3-for-3)."
            if len(give_pick_nos) == len(receive_pick_nos)
            else "Uneven pick counts — partner may want a player sweetener."
        ),
    }


def build_pick_trade_context(state: DraftState) -> dict[str, Any]:
    """Future pick values + example swap for startup pick-position trades."""
    future = build_my_future_pick_values(state)
    bookends = [row for row in future if row.get("is_bookend")]

    examples: list[dict[str, Any]] = []
    if state.my_slot is not None:
        # Common bookend-for-spread swap: e.g. 2.01+8.01 for 3.01+5.01 (slot 10)
        give = [my_pick_in_round(state, r) for r in (2, 8)]
        receive = [pick_no_from_round_position(state, r, 1) for r in (3, 5)]
        if all(pick is not None for pick in give + receive):
            examples.append(
                {
                    "name": "bookend_for_spread",
                    "description": (
                        "Trade clustered bookend picks for earlier-in-round picks "
                        "(e.g. give 2.01 + 8.01, get 3.01 + 5.01 in a 2-for-2 swap)."
                    ),
                    **evaluate_pick_swap(state, give, receive),
                }
            )

    return {
        "notation": "Labels like 2.01 = round 2, pick 1 in that round (overall pick # varies by league size).",
        "startup_trade_norms": [
            "Pick-position trades in startup drafts are almost always even (2-for-2, 3-for-3).",
            "Bookend pairs (back-to-back) are premium — trading them spreads your picks through a round.",
            "Compare swaps using projected TV of the player likely available at each pick.",
            "If you dislike a player likely to be there at your slot (e.g. QB at 1.11), swap picks not players.",
        ],
        "my_future_pick_values": future,
        "my_bookend_picks": bookends,
        "example_swaps": examples,
    }
