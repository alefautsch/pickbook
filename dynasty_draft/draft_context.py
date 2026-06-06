from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from dynasty_draft.recommender import DraftState
from dynasty_draft.war_data import PlayerValue, normalize_name


def _blended_tv(state: DraftState, war_player: PlayerValue | None) -> float | None:
    if war_player is None:
        return None
    return state.blended_trade_value(war_player)


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
        "trade_value": _blended_tv(state, war_player),
        "worp": war_player.worp if war_player else None,
        "porp": war_player.porp if war_player else None,
        "projected_worp": None,
        "dynasty_rating": None,
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
                "porp": None,
                "projected_worp": None,
                "dynasty_rating": None,
                "status": status,
                "is_me": is_me,
            }
        )

    pool: list[tuple[str, Any]] = []
    enrich_by_pick: dict[int, tuple[str, Any]] = {}
    for row in rows:
        if row.get("status") != "done":
            continue
        pick = picks_by_no.get(int(row["pick_no"]))
        if not pick:
            continue
        player_id = pick.get("player_id")
        war_player = state._match_war(player_id) if player_id else None
        if player_id and war_player:
            pool.append((player_id, war_player))
            enrich_by_pick[int(row["pick_no"])] = (player_id, war_player)

    dynasty_by_id = state.dynasty_scores(pool) if pool else {}
    for pick_no, (player_id, war_player) in enrich_by_pick.items():
        row = next(r for r in rows if r.get("pick_no") == pick_no)
        row["player_id"] = player_id
        state.enrich_player_worp(row)
        dynasty = dynasty_by_id.get(player_id) or {}
        row["dynasty_rating"] = dynasty.get("dynasty_rating")
        row["dynasty_rookie"] = dynasty.get("dynasty_rookie")

    return rows


_FLEX_ELIGIBLE = frozenset({"RB", "WR", "TE"})
_SF_ELIGIBLE = frozenset({"QB", "RB", "WR", "TE"})
_SLOT_LABELS = {"SUPER_FLEX": "SF"}


def _sleeper_id_for_name(state: DraftState, name: str) -> str | None:
    key = normalize_name(name)
    for player_id, sleeper in state.sleeper_players.items():
        if normalize_name(sleeper.get("full_name") or "") == key:
            return player_id
    return None


def _war_player_for_roster_player(
    state: DraftState,
    player: dict[str, Any],
) -> tuple[str | None, Any | None]:
    """Resolve Sleeper id + war row for drafted or reserved (name-only) players."""
    player_id = player.get("player_id")
    if player_id:
        return player_id, state._match_war(player_id)
    name = player.get("name")
    if not name:
        return None, None
    war_player = state.war.lookup(name)
    if war_player is None:
        return None, None
    resolved_id = _sleeper_id_for_name(state, name)
    return resolved_id, war_player


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
    name = war_player.name if war_player else state._sleeper_name(player_id or "") or "Unknown"
    return {
        "player_id": player_id,
        "pick_no": pick.get("pick_no"),
        "name": name,
        "pos": pos,
        "team": (war_player.team if war_player else sleeper.get("team") or "").upper(),
        "age": _player_age(state, player_id),
        "trade_value": _blended_tv(state, war_player),
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
            war_player = state.war.lookup(row["name"])
            player_id = _sleeper_id_for_name(state, row["name"])
            reserved.append(
                {
                    "player_id": player_id,
                    "pick_no": None,
                    "name": row["name"],
                    "pos": (war_player.pos if war_player else row.get("pos")) or "?",
                    "team": (war_player.team if war_player else "") or "",
                    "age": _player_age(state, player_id),
                    "trade_value": (
                        state.blended_trade_value(war_player)
                        if war_player
                        else row.get("trade_value")
                    ),
                    "worp": war_player.worp if war_player else None,
                    "porp": war_player.porp if war_player else None,
                    "status": "reserved",
                }
            )
    return _finalize_lineup(drafted, reserved, state.roster_positions)


def _apply_dynasty_to_lineup(state: DraftState, team: dict[str, Any]) -> dict[str, Any]:
    """Attach per-player dynasty_rating (50–99) and team aggregates."""
    starters = [row["player"] for row in team.get("starters", []) if row.get("player")]
    bench = team.get("bench") or []
    all_players = starters + bench
    pool: list[tuple[str, Any]] = []
    for player in all_players:
        player_id, war_player = _war_player_for_roster_player(state, player)
        if not war_player:
            continue
        if player_id and not player.get("player_id"):
            player["player_id"] = player_id
            player["age"] = _player_age(state, player_id)
            if not player.get("team") and war_player.team:
                player["team"] = war_player.team
        score_id = player_id or f"reserved:{normalize_name(player['name'])}"
        pool.append((score_id, war_player))
        player["_dynasty_score_id"] = score_id

    if not pool:
        return {
            "total_dynasty_rating": 0,
            "starter_avg_dynasty_rating": 0,
            "avg_dynasty_rating": 0,
        }

    scores = state.dynasty_scores(pool)
    starter_ids = {player.get("_dynasty_score_id") for player in starters}
    for player in all_players:
        state.enrich_player_worp(player)
        score_id = player.get("_dynasty_score_id")
        if not score_id or score_id not in scores:
            continue
        scored = scores[score_id]
        player["dynasty_rating"] = scored.get("dynasty_rating")
        player["dynasty_rookie"] = scored.get("dynasty_rookie")

    ratings = [row.get("dynasty_rating", 0) for row in scores.values()]
    starter_ratings = [
        scores[sid].get("dynasty_rating", 0)
        for sid in starter_ids
        if sid and sid in scores
    ]
    return {
        "total_dynasty_rating": sum(ratings),
        "starter_avg_dynasty_rating": (
            round(sum(starter_ratings) / len(starter_ratings)) if starter_ratings else 0
        ),
        "avg_dynasty_rating": round(sum(ratings) / len(ratings)) if ratings else 0,
    }


def build_league_lineups(state: DraftState) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for team in _league_teams(state):
        lineup = build_team_lineup(
            state,
            team["roster_id"],
            include_reserved=team["is_me"],
        )
        merged = {**team, **lineup}
        merged.update(_apply_dynasty_to_lineup(state, merged))
        rows.append(merged)

    by_avg = sorted(rows, key=lambda row: row.get("avg_dynasty_rating") or 0, reverse=True)
    for idx, row in enumerate(by_avg, start=1):
        row["dynasty_rank"] = idx
    return rows


def build_my_team_lineup(state: DraftState) -> dict[str, Any]:
    if state.my_roster_id is None:
        return _finalize_lineup([], [], state.roster_positions)
    for team in build_league_lineups(state):
        if team.get("is_me"):
            return team
    lineup = build_team_lineup(state, state.my_roster_id, include_reserved=True)
    lineup.update(_apply_dynasty_to_lineup(state, lineup))
    return lineup


def build_league_rankings(state: DraftState) -> dict[str, list[dict[str, Any]]]:
    teams = build_league_lineups(state)

    def _rank_key_tv(row: dict[str, Any]) -> float:
        return float(row.get("total_trade_value") or 0)

    def _rank_key_win(row: dict[str, Any]) -> float:
        return float(row.get("win_now_score") or -1)

    def _rank_key_dynasty(row: dict[str, Any]) -> float:
        return float(row.get("avg_dynasty_rating") or 0)

    by_trade_value = sorted(teams, key=_rank_key_tv, reverse=True)
    by_win_now = sorted(teams, key=_rank_key_win, reverse=True)
    by_dynasty = sorted(teams, key=_rank_key_dynasty, reverse=True)
    for idx, row in enumerate(by_trade_value, start=1):
        row["tv_rank"] = idx
    for idx, row in enumerate(by_win_now, start=1):
        row["win_rank"] = idx
    return {
        "by_dynasty": by_dynasty,
        "by_trade_value": by_trade_value,
        "by_win_now": by_win_now,
    }


def league_rankings_summary(state: DraftState) -> dict[str, list[dict[str, Any]]]:
    """Compact league standings for advisor context."""
    rankings = build_league_rankings(state)

    def _row(team: dict[str, Any]) -> dict[str, Any]:
        return {
            "team": team["team_name"],
            "is_me": team["is_me"],
            "picks": team.get("pick_count") or 0,
            "avg_dynasty_rating": team.get("avg_dynasty_rating"),
            "starter_avg_dynasty_rating": team.get("starter_avg_dynasty_rating"),
            "total_trade_value": team.get("total_trade_value"),
            "win_now_score": team.get("win_now_score"),
            "dynasty_rank": team.get("dynasty_rank"),
            "tv_rank": team.get("tv_rank"),
            "win_rank": team.get("win_rank"),
        }

    return {
        "by_dynasty": [_row(team) for team in rankings["by_dynasty"]],
        "by_trade_value": [_row(team) for team in rankings["by_trade_value"]],
        "by_win_now": [_row(team) for team in rankings["by_win_now"]],
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
