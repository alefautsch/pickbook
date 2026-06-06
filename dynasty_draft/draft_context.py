from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from dynasty_draft.recommender import DraftState


def build_scoring_context(state: DraftState) -> dict[str, Any]:
    league = state.league or {}
    settings = league.get("scoring_settings") or {}
    roster_positions = state.roster_positions or league.get("roster_positions") or []

    ppr = settings.get("rec")
    te_premium = settings.get("bonus_rec_te") or 0
    pass_td = settings.get("pass_td")
    pass_td_40 = settings.get("pass_td_40p")
    rec_td_40 = settings.get("rec_td_40p")
    rush_td_40 = settings.get("rush_td_40p")
    superflex = state.is_superflex()

    # Sleeper provides these for Good Luck Assholes; fallbacks match league rules.
    summary_parts = [
        f"{ppr or 0.5} PPR" if ppr is not None else "0.5 PPR",
        "no TE premium" if not te_premium else f"+{te_premium} TE premium",
        "superflex" if superflex else "standard",
        f"{int(pass_td) if pass_td is not None else 4}-pt passing TDs",
    ]
    bonus_bits: list[str] = []
    if pass_td_40:
        bonus_bits.append(f"+{pass_td_40} pass TD 40+")
    if rec_td_40:
        bonus_bits.append(f"+{rec_td_40} rec TD 40+")
    if rush_td_40:
        bonus_bits.append(f"+{rush_td_40} rush TD 40+")
    if bonus_bits:
        summary_parts.append(", ".join(bonus_bits))

    return {
        "summary": ", ".join(summary_parts),
        "ppr": ppr if ppr is not None else 0.5,
        "te_premium": te_premium,
        "pass_td_points": pass_td if pass_td is not None else 4,
        "pass_td_40_bonus": pass_td_40,
        "rec_td_40_bonus": rec_td_40,
        "rush_td_40_bonus": rush_td_40,
        "superflex": superflex,
        "roster_positions": roster_positions,
        "source": "sleeper" if settings else "defaults",
    }


def _team_display_name(user: dict[str, Any] | None, roster_id: int) -> str:
    if not user:
        return f"Team {roster_id}"
    meta = user.get("metadata") or {}
    return meta.get("team_name") or user.get("display_name") or f"Team {roster_id}"


def _pick_row(state: DraftState, pick: dict[str, Any]) -> dict[str, Any]:
    player_id = pick.get("player_id")
    war_player = state._match_war(player_id) if player_id else None
    meta = pick.get("metadata") or {}
    name = war_player.name if war_player else state._sleeper_name(player_id or "") or "Unknown"
    return {
        "pick_no": pick.get("pick_no"),
        "round": pick.get("round"),
        "name": name,
        "pos": meta.get("position") or (war_player.pos if war_player else ""),
        "trade_value": war_player.trade_value if war_player else None,
        "worp": war_player.worp if war_player else None,
    }


def _roster_id_for_slot(state: DraftState, slot: int) -> int | None:
    roster_id = (state.draft.get("slot_to_roster_id") or {}).get(str(slot))
    return int(roster_id) if roster_id is not None else None


def _team_name_for_roster(state: DraftState, roster_id: int) -> str:
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


def build_draft_timeline(
    state: DraftState,
    *,
    past: int = 8,
    upcoming: int = 10,
) -> list[dict[str, Any]]:
    """Recent picks plus upcoming slots centered on the current pick."""
    teams = state._teams()
    rounds = state._rounds()
    total_picks = teams * rounds
    current_pick = len(state.picks) + 1
    start = max(1, current_pick - past)
    end = min(total_picks, current_pick + upcoming - 1)

    picks_by_no = {int(p["pick_no"]): p for p in state.picks if p.get("pick_no")}
    rows: list[dict[str, Any]] = []

    for pick_no in range(start, end + 1):
        if pick_no in picks_by_no:
            pick = picks_by_no[pick_no]
            roster_id = int(pick.get("roster_id", 0))
            row = _pick_row(state, pick)
            rows.append(
                {
                    **row,
                    "team": _team_name_for_roster(state, roster_id),
                    "status": "done",
                    "is_me": state.my_roster_id is not None and roster_id == state.my_roster_id,
                }
            )
            continue

        slot = state._pick_slot(pick_no)
        roster_id = _roster_id_for_slot(state, slot)
        is_me = state.my_roster_id is not None and roster_id == state.my_roster_id
        if pick_no == current_pick:
            status = "on_clock"
        elif is_me:
            status = "mine"
        else:
            status = "upcoming"
        rows.append(
            {
                "pick_no": pick_no,
                "round": (pick_no - 1) // teams + 1,
                "team": _team_name_for_roster(state, roster_id) if roster_id is not None else f"Slot {slot}",
                "name": "",
                "pos": "",
                "trade_value": None,
                "worp": None,
                "status": status,
                "is_me": is_me,
            }
        )
    return rows


def build_league_team_rosters(state: DraftState) -> list[dict[str, Any]]:
    users_by_id = {str(u.get("user_id")): u for u in (state.league_users or [])}
    by_roster: dict[int, list[dict[str, Any]]] = defaultdict(list)

    for pick in state.picks:
        if not pick.get("player_id"):
            continue
        roster_id = int(pick.get("roster_id", 0))
        by_roster[roster_id].append(pick)

    slot_to_roster = state.draft.get("slot_to_roster_id") or {}
    draft_order = state.draft.get("draft_order") or {}
    roster_to_slot: dict[int, int] = {}
    for user_id, slot in draft_order.items():
        roster_id = slot_to_roster.get(str(slot))
        if roster_id is not None:
            roster_to_slot[int(roster_id)] = int(slot)

    teams: list[dict[str, Any]] = []
    for roster_id in sorted(by_roster.keys()):
        picks = sorted(by_roster[roster_id], key=lambda p: p.get("pick_no", 0))
        owner_id = str(picks[0].get("picked_by") or "")
        user = users_by_id.get(owner_id)
        pick_rows = [_pick_row(state, p) for p in picks]
        pos_counts = Counter(row["pos"] for row in pick_rows if row.get("pos"))
        teams.append(
            {
                "team_name": _team_display_name(user, roster_id),
                "owner": (user or {}).get("display_name"),
                "roster_id": roster_id,
                "draft_slot": roster_to_slot.get(roster_id),
                "is_me": state.my_roster_id is not None and roster_id == state.my_roster_id,
                "pick_count": len(pick_rows),
                "position_counts": dict(sorted(pos_counts.items())),
                "picks": pick_rows,
            }
        )
    return teams
