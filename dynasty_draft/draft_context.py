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


_FLEX_ELIGIBLE = frozenset({"RB", "WR", "TE"})
_SF_ELIGIBLE = frozenset({"QB", "RB", "WR", "TE"})
_SLOT_LABELS = {"SUPER_FLEX": "SF"}


def _player_age(state: DraftState, player_id: str | None) -> int | None:
    if not player_id:
        return None
    sleeper = state.sleeper_players.get(player_id) or {}
    age = sleeper.get("age")
    if age is not None:
        return int(age)
    years_exp = sleeper.get("years_exp")
    if years_exp is not None and years_exp == 0:
        return None
    return None


def _roster_player_from_pick(state: DraftState, pick: dict[str, Any]) -> dict[str, Any]:
    player_id = pick.get("player_id")
    war_player = state._match_war(player_id) if player_id else None
    meta = pick.get("metadata") or {}
    sleeper = state.sleeper_players.get(player_id or "") or {}
    pos = (meta.get("position") or sleeper.get("position") or (war_player.pos if war_player else "")).upper()
    return {
        "player_id": player_id,
        "pick_no": pick.get("pick_no"),
        "name": war_player.name if war_player else state._sleeper_name(player_id or "") or "Unknown",
        "pos": pos,
        "team": (war_player.team if war_player else sleeper.get("team") or "").upper(),
        "age": _player_age(state, player_id),
        "trade_value": war_player.trade_value if war_player else None,
        "worp": war_player.worp if war_player else None,
        "porp": war_player.porp if war_player else None,
        "status": "drafted",
    }


def _starter_slot_plan(roster_positions: list[str]) -> list[tuple[str, str]]:
    """Return (slot_type, display_label) for each starter slot before bench."""
    plan: list[tuple[str, str]] = []
    for pos in roster_positions:
        if pos == "BN":
            break
        plan.append((pos, _SLOT_LABELS.get(pos, pos)))
    return plan


def _take_best(
    pool: list[dict[str, Any]],
    used: set[str],
    eligible: frozenset[str],
) -> dict[str, Any] | None:
    for player in pool:
        key = player.get("player_id") or player.get("name") or ""
        if not key or key in used:
            continue
        if player.get("pos") in eligible:
            used.add(key)
            return player
    return None


def _assign_lineup(
    players: list[dict[str, Any]],
    roster_positions: list[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    pool = sorted(players, key=lambda row: row.get("trade_value") or 0, reverse=True)
    used: set[str] = set()
    starters: list[dict[str, Any]] = []

    for slot_type, label in _starter_slot_plan(roster_positions):
        if slot_type == "QB":
            player = _take_best(pool, used, frozenset({"QB"}))
        elif slot_type == "RB":
            player = _take_best(pool, used, frozenset({"RB"}))
        elif slot_type == "WR":
            player = _take_best(pool, used, frozenset({"WR"}))
        elif slot_type == "TE":
            player = _take_best(pool, used, frozenset({"TE"}))
        elif slot_type == "FLEX":
            player = _take_best(pool, used, _FLEX_ELIGIBLE)
        elif slot_type == "SUPER_FLEX":
            player = _take_best(pool, used, _SF_ELIGIBLE)
        else:
            player = None
        starters.append({"slot": label, "player": player})

    bench = [
        player
        for player in pool
        if (player.get("player_id") or player.get("name") or "") not in used
    ]
    return starters, bench


def _starter_metric(starters: list[dict[str, Any]], field: str) -> float | None:
    values = [
        row["player"][field]
        for row in starters
        if row.get("player") and row["player"].get(field) is not None
    ]
    return sum(values) if values else None


def _finalize_lineup(
    drafted: list[dict[str, Any]],
    reserved: list[dict[str, Any]],
    roster_positions: list[str],
) -> dict[str, Any]:
    starters, bench = _assign_lineup(drafted, roster_positions)
    bench = sorted(bench, key=lambda row: row.get("trade_value") or 0, reverse=True)
    bench.extend(reserved)
    all_players = [row["player"] for row in starters if row.get("player")] + bench
    total_tv = sum(player.get("trade_value") or 0 for player in all_players)
    worp_values = [player.get("worp") for player in all_players if player.get("worp") is not None]
    starter_worp = _starter_metric(starters, "worp")
    starter_porp = _starter_metric(starters, "porp")
    win_now_score = None
    if starter_worp is not None or starter_porp is not None:
        win_now_score = (starter_worp or 0.0) + (starter_porp or 0.0) / 100.0
    return {
        "starters": starters,
        "bench": bench,
        "pick_count": len(drafted),
        "reserved_count": len(reserved),
        "total_trade_value": total_tv,
        "total_worp": sum(worp_values) if worp_values else None,
        "starter_worp": starter_worp,
        "starter_porp": starter_porp,
        "win_now_score": win_now_score,
    }


def _picks_for_roster(state: DraftState, roster_id: int) -> list[dict[str, Any]]:
    return [
        pick
        for pick in state.picks
        if pick.get("player_id") and int(pick.get("roster_id", -1)) == roster_id
    ]


def _league_teams(state: DraftState) -> list[dict[str, Any]]:
    users_by_id = {str(u.get("user_id")): u for u in (state.league_users or [])}
    draft_order = state.draft.get("draft_order") or {}
    slot_to_roster = state.draft.get("slot_to_roster_id") or {}
    teams: list[dict[str, Any]] = []
    for user_id, slot in draft_order.items():
        roster_id = slot_to_roster.get(str(slot))
        if roster_id is None:
            continue
        roster_id = int(roster_id)
        user = users_by_id.get(str(user_id))
        teams.append(
            {
                "team_name": _team_display_name(user, roster_id),
                "owner": (user or {}).get("display_name"),
                "roster_id": roster_id,
                "draft_slot": int(slot),
                "is_me": state.my_roster_id is not None and roster_id == state.my_roster_id,
            }
        )
    return sorted(teams, key=lambda row: row.get("draft_slot") or 99)


def build_team_lineup(state: DraftState, roster_id: int, *, include_reserved: bool = False) -> dict[str, Any]:
    drafted = [
        _roster_player_from_pick(state, pick)
        for pick in sorted(_picks_for_roster(state, roster_id), key=lambda row: row.get("pick_no", 0))
    ]
    reserved: list[dict[str, Any]] = []
    if include_reserved and state.strategy.is_vet_draft and roster_id == state.my_roster_id:
        for row in state.strategy.reserved_players(state.war):
            reserved.append(
                {
                    "player_id": None,
                    "pick_no": None,
                    "name": row["name"],
                    "pos": row.get("pos") or "?",
                    "team": "",
                    "age": None,
                    "trade_value": row.get("trade_value"),
                    "worp": None,
                    "porp": None,
                    "status": "reserved",
                }
            )
    return _finalize_lineup(drafted, reserved, state.roster_positions)


def build_my_team_lineup(state: DraftState) -> dict[str, Any]:
    if state.my_roster_id is None:
        return _finalize_lineup([], [], state.roster_positions)
    return build_team_lineup(state, state.my_roster_id, include_reserved=True)


def build_league_lineups(state: DraftState) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for team in _league_teams(state):
        lineup = build_team_lineup(
            state,
            team["roster_id"],
            include_reserved=team["is_me"],
        )
        rows.append({**team, **lineup})
    return rows


def build_league_rankings(state: DraftState) -> dict[str, list[dict[str, Any]]]:
    teams = build_league_lineups(state)

    def _rank_key_tv(row: dict[str, Any]) -> float:
        return float(row.get("total_trade_value") or 0)

    def _rank_key_win(row: dict[str, Any]) -> float:
        return float(row.get("win_now_score") or -1)

    by_trade_value = sorted(teams, key=_rank_key_tv, reverse=True)
    by_win_now = sorted(teams, key=_rank_key_win, reverse=True)
    for idx, row in enumerate(by_trade_value, start=1):
        row["tv_rank"] = idx
    for idx, row in enumerate(by_win_now, start=1):
        row["win_rank"] = idx
    return {
        "by_trade_value": by_trade_value,
        "by_win_now": by_win_now,
    }


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
