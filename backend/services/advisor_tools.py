"""Advisor tool implementations — on-demand league data for the in-season tool loop."""

from __future__ import annotations

import ast
import json
import operator
from dataclasses import dataclass
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.db.models import League, PlayerSnapshot, Roster, RosterDraftPick
from backend.services.web_search_service import search_web
from backend.services.analysis_service import TRADE_SURPLUS_BOTTOM_N, TRADE_SURPLUS_TOP_N
from backend.services.pick_service import get_roster_draft_picks
from backend.services.portfolio_service import get_free_agents
from backend.services.read_service import get_league_rankings, get_player_card, get_team_detail
from backend.services.trade_validation_service import (
    build_validation_payload,
    validate_trade_with_llm,
    validation_accept_score,
)
from backend.services.trade_engine import (
    FAIRNESS_BAND,
    annotate_picks_with_trade_tags,
    annotate_players_with_trade_tags,
    asset_tv,
    effective_package_tv,
    evaluate_package_fairness,
    package_quality_score,
    top_trade_candidates,
    trade_fit_score,
)
TOP_FA_DEFAULT = 24
TOP_ROSTER_PLAYERS = 16

_CALC_OPS: dict[type, Any] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def safe_calculate(expression: str) -> float:
    """Evaluate a numeric expression with + - * / ** and parentheses only."""
    expr = expression.strip()
    if not expr:
        raise ValueError("expression is required")
    tree = ast.parse(expr, mode="eval")

    def _eval(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return _eval(node.body)
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)):
                return float(node.value)
            raise ValueError("only numeric literals allowed")
        if isinstance(node, ast.BinOp):
            op_type = type(node.op)
            if op_type not in _CALC_OPS:
                raise ValueError(f"unsupported operator: {op_type.__name__}")
            return _CALC_OPS[op_type](_eval(node.left), _eval(node.right))
        if isinstance(node, ast.UnaryOp):
            op_type = type(node.op)
            if op_type not in _CALC_OPS:
                raise ValueError(f"unsupported operator: {op_type.__name__}")
            return _CALC_OPS[op_type](_eval(node.operand))
        raise ValueError("unsupported expression")

    return round(_eval(tree), 4)


def _pick_key(pick: dict[str, Any]) -> tuple[str, int, str]:
    return (str(pick["season"]), int(pick["round"]), str(pick["original_roster_id"]))


def _positional_notes(
    give_players: list[dict[str, Any]],
    receive_players: list[dict[str, Any]],
) -> list[str]:
    notes: list[str] = []
    give_by_pos: dict[str, int] = {}
    recv_by_pos: dict[str, int] = {}
    for row in give_players:
        pos = row.get("position") or row.get("pos") or "?"
        give_by_pos[pos] = give_by_pos.get(pos, 0) + 1
    for row in receive_players:
        pos = row.get("position") or row.get("pos") or "?"
        recv_by_pos[pos] = recv_by_pos.get(pos, 0) + 1
    for pos, count in recv_by_pos.items():
        if give_by_pos.get(pos, 0) < count:
            notes.append(f"Receive {count} {pos} — fills a roster hole")
    for pos, count in give_by_pos.items():
        if recv_by_pos.get(pos, 0) < count:
            notes.append(f"Give {count} {pos} — moves surplus depth")
    if not notes:
        notes.append("Positional swap is roughly neutral")
    return notes


def evaluate_trade_package(
    give: dict[str, Any],
    receive: dict[str, Any],
    *,
    resolve_player: Callable[[str], dict[str, Any] | None],
    resolve_pick: Callable[[dict[str, Any]], dict[str, Any] | None],
) -> dict[str, Any]:
    """Pure TV evaluation for player + pick packages."""
    give_players_raw = give.get("players") or []
    recv_players_raw = receive.get("players") or []
    give_picks_raw = give.get("picks") or []
    recv_picks_raw = receive.get("picks") or []

    give_players: list[dict[str, Any]] = []
    recv_players: list[dict[str, Any]] = []
    missing: list[str] = []

    for pid in give_players_raw:
        row = resolve_player(str(pid))
        if row is None:
            missing.append(f"player:{pid}")
            continue
        give_players.append(row)
    for pid in recv_players_raw:
        row = resolve_player(str(pid))
        if row is None:
            missing.append(f"player:{pid}")
            continue
        recv_players.append(row)

    give_picks: list[dict[str, Any]] = []
    recv_picks: list[dict[str, Any]] = []
    for pick in give_picks_raw:
        row = resolve_pick(pick)
        if row is None:
            missing.append(f"pick:{_pick_key(pick)}")
            continue
        give_picks.append(row)
    for pick in recv_picks_raw:
        row = resolve_pick(pick)
        if row is None:
            missing.append(f"pick:{_pick_key(pick)}")
            continue
        recv_picks.append(row)

    give_assets = give_players + give_picks
    recv_assets = recv_players + recv_picks
    fairness = evaluate_package_fairness(give_assets, recv_assets)
    return {
        **fairness,
        "give": {
            "players": give_players,
            "picks": give_picks,
        },
        "receive": {
            "players": recv_players,
            "picks": recv_picks,
        },
        "positional_notes": _positional_notes(give_players, recv_players),
        "missing_assets": missing,
    }


def _package_trade_inputs(pkg: dict[str, Any]) -> tuple[str, dict[str, Any], dict[str, Any]]:
    """Convert a suggest_trades package into evaluate_trade give/receive ids."""
    cp_id = str((pkg.get("counterparty") or {}).get("roster_id") or "")

    def _player_ids(rows: list[dict[str, Any]]) -> list[str]:
        return [str(p["player_id"]) for p in rows if p.get("player_id")]

    def _pick_refs(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        refs: list[dict[str, Any]] = []
        for pick in rows:
            if pick.get("player_id"):
                continue
            refs.append(
                {
                    "season": pick["season"],
                    "round": pick["round"],
                    "original_roster_id": pick["original_roster_id"],
                }
            )
        return refs

    give = pkg.get("give") or {}
    recv = pkg.get("receive") or {}
    return (
        cp_id,
        {"players": _player_ids(give.get("players") or []), "picks": _pick_refs(give.get("picks") or [])},
        {"players": _player_ids(recv.get("players") or []), "picks": _pick_refs(recv.get("picks") or [])},
    )


def rank_packages_by_counterparty_validation(
    packages: list[dict[str, Any]],
    *,
    my_roster_id: str,
    resolve_player: Callable[[str], dict[str, Any] | None],
    resolve_pick: Callable[[dict[str, Any]], dict[str, Any] | None],
    load_team: Callable[[str], dict[str, Any]],
    trade_surplus: dict[str, Any] | None,
    api_key: str | None,
    max_validate: int = 2,
) -> list[dict[str, Any]]:
    """Validate packages from the counterparty lens and re-rank by accept likelihood."""
    if not packages or not api_key or not str(api_key).strip():
        return packages

    my_team = load_team(str(my_roster_id))
    if my_team.get("error"):
        return packages
    if trade_surplus:
        my_team = {
            **my_team,
            "surplus": (trade_surplus.get("surplus") or my_team.get("surplus") or []),
            "needs": (trade_surplus.get("needs") or my_team.get("needs") or []),
        }

    validated: list[dict[str, Any]] = []
    tail: list[dict[str, Any]] = []

    for idx, pkg in enumerate(packages):
        if idx >= max_validate:
            tail.extend(packages[idx:])
            break

        cp_id, give_in, recv_in = _package_trade_inputs(pkg)
        if not cp_id:
            tail.append(pkg)
            continue

        eval_result = evaluate_trade_package(
            give_in,
            recv_in,
            resolve_player=resolve_player,
            resolve_pick=resolve_pick,
        )
        if eval_result.get("missing_assets"):
            enriched = dict(pkg)
            enriched["counterparty_validation"] = {
                "error": "missing_assets",
                "missing_assets": eval_result["missing_assets"],
            }
            tail.append(enriched)
            continue

        their_team = load_team(cp_id)
        if their_team.get("error"):
            tail.append(pkg)
            continue

        payload = build_validation_payload(
            proposer_roster_id=str(my_roster_id),
            counterparty_roster_id=cp_id,
            proposer_team=my_team,
            counterparty_team=their_team,
            give=eval_result["give"],
            receive=eval_result["receive"],
            tv_evaluation=eval_result,
        )
        validation = validate_trade_with_llm(payload, api_key=api_key)
        enriched = dict(pkg)
        enriched["counterparty_validation"] = validation
        score = validation_accept_score(validation)
        enriched["validation_accept_score"] = score
        validated.append(enriched)

    def _sort_key(row: dict[str, Any]) -> tuple[float, float, float]:
        vas = row.get("validation_accept_score")
        accept = vas if vas is not None else -1.0
        return (
            accept,
            float(row.get("acquisition_score") or row.get("package_quality") or 0),
            -abs(float(row.get("net_delta_adjusted_pct") or 0)),
        )

    validated.sort(key=_sort_key, reverse=True)
    return validated + tail


def _team_surplus_needs(
    position_strength: dict[str, Any] | None,
    roster_id: str,
    *,
    top_n: int = TRADE_SURPLUS_TOP_N,
    bottom_n: int = TRADE_SURPLUS_BOTTOM_N,
) -> dict[str, list[dict[str, Any]]]:
    if not position_strength:
        return {"surplus": [], "needs": []}
    teams = position_strength.get("teams") or []
    positions = position_strength.get("positions") or []
    team = next((t for t in teams if str(t.get("roster_id")) == str(roster_id)), None)
    if team is None:
        return {"surplus": [], "needs": []}

    surplus: list[dict[str, Any]] = []
    needs: list[dict[str, Any]] = []
    for pos in positions:
        ranked = sorted(
            [
                {
                    "roster_id": str(t["roster_id"]),
                    "avg_ovr": (t.get("by_position") or {}).get(pos),
                }
                for t in teams
                if (t.get("by_position") or {}).get(pos) is not None
            ],
            key=lambda row: row["avg_ovr"] or 0,
            reverse=True,
        )
        if not ranked:
            continue
        rank_by_roster = {row["roster_id"]: idx + 1 for idx, row in enumerate(ranked)}
        my_rank = rank_by_roster.get(str(roster_id))
        my_ovr = (team.get("by_position") or {}).get(pos)
        if my_rank is None:
            continue
        item = {
            "position": pos,
            "avg_ovr": my_ovr,
            "league_rank": my_rank,
            "league_size": len(ranked),
        }
        if my_rank <= top_n:
            surplus.append(item)
        if my_rank > len(ranked) - bottom_n:
            needs.append(item)
    return {"surplus": surplus, "needs": needs}


def _players_for_roster(
    snapshots: dict[str, PlayerSnapshot],
    roster_player_ids: list[str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for pid in roster_player_ids:
        snap = snapshots.get(pid)
        if snap is None:
            continue
        rows.append(
            {
                "player_id": snap.sleeper_player_id,
                "name": snap.player_name,
                "position": snap.position,
                "pos": snap.position,
                "ovr": snap.dynasty_rating,
                "tv": snap.trade_value,
                "hppg": snap.hppg,
                "projected_ppg": snap.projected_ppg,
                "age": snap.age,
            }
        )
    rows.sort(key=lambda r: r.get("tv") or 0, reverse=True)
    return rows


def _balance_with_pick(
    give_assets: list[dict[str, Any]],
    recv_assets: list[dict[str, Any]],
    *,
    my_picks: list[dict[str, Any]],
    their_picks: list[dict[str, Any]],
    target_delta: float = 0.0,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Add at most one pick to move effective TV delta toward target."""
    give_eff = effective_package_tv(give_assets)
    recv_eff = effective_package_tv(recv_assets)
    delta = recv_eff - give_eff - target_delta
    if abs(delta) <= max(recv_eff, give_eff, 1) * FAIRNESS_BAND:
        return give_assets, recv_assets

    if delta < 0:
        for pick in sorted(their_picks, key=lambda p: p.get("trade_value") or 0):
            trial_recv = effective_package_tv(recv_assets + [pick])
            if abs(trial_recv - give_eff) < abs(delta):
                return give_assets, recv_assets + [pick]
    else:
        for pick in sorted(my_picks, key=lambda p: p.get("trade_value") or 0):
            trial_give = effective_package_tv(give_assets + [pick])
            if abs(recv_eff - trial_give) < abs(delta):
                return give_assets + [pick], recv_assets
    return give_assets, recv_assets


def _flex_depth_give_pool(my_annotated: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """FLEX surplus → movable RB/WR/TE depth (low lineup impact first)."""
    pool = [
        p
        for p in my_annotated
        if (p.get("position") or "").upper() in {"RB", "WR", "TE"}
        and p.get("trade_tag") == "trade"
    ]
    pool.sort(key=lambda p: (p.get("lineup_delta_ppg") or 0, asset_tv(p)))
    return pool


def _surplus_give_pool(
    my_annotated: list[dict[str, Any]],
    hook_pos: str,
    *,
    my_surplus_positions: set[str],
) -> list[dict[str, Any]]:
    pos = hook_pos.upper()
    if pos == "FLEX":
        flex = _flex_depth_give_pool(my_annotated)
        if flex:
            return flex
        pool = [
            p
            for p in my_annotated
            if (p.get("position") or "").upper() in {"RB", "WR", "TE"}
            and p.get("trade_tag") != "core"
            and int(p.get("depth_rank") or 99) >= 2
        ]
        pool.sort(key=lambda p: (p.get("lineup_delta_ppg") or 0, asset_tv(p)))
        return pool[:4]

    pool = sorted(
        [p for p in my_annotated if (p.get("position") or "").upper() == pos],
        key=lambda p: p.get("lineup_delta_ppg") or 0,
    )
    trade_first = [p for p in pool if p.get("trade_tag") == "trade"]
    depth_movable = [
        p
        for p in pool
        if p.get("trade_tag") != "core" and int(p.get("depth_rank") or 99) >= 2
    ]
    merged: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for row in trade_first + depth_movable:
        pid = str(row.get("player_id") or "")
        if pid in seen_ids:
            continue
        seen_ids.add(pid)
        merged.append(row)
    return merged[:4]


def _counterparty_recv_pool(
    their_annotated: list[dict[str, Any]],
    *,
    direction: str,
    hook_pos: str,
    my_need_positions: set[str],
    my_surplus_positions: set[str],
    my_tier: str | None,
    their_tier: str | None,
    limit: int = 4,
) -> list[dict[str, Any]]:
    """Players the counterparty might realistically move in a surplus hook trade."""
    pos = hook_pos.upper()
    candidates: list[dict[str, Any]] = []

    if direction == "sell":
        for player in their_annotated:
            player_pos = (player.get("position") or "").upper()
            if player_pos not in my_need_positions or player_pos == pos:
                continue
            tag = player.get("trade_tag")
            if tag == "core":
                continue
            candidates.append(player)
    else:
        for player in their_annotated:
            if (player.get("position") or "").upper() != pos:
                continue
            tag = player.get("trade_tag")
            depth = int(player.get("depth_rank") or 99)
            if tag == "core":
                continue
            if tag != "trade" and depth <= 1:
                continue
            candidates.append(player)

    candidates.sort(
        key=lambda p: trade_fit_score(
            p,
            acquirer_need_positions=my_need_positions,
            acquirer_surplus_positions=my_surplus_positions,
            acquirer_tier=my_tier,
            seller_tier=their_tier,
        )
        * _target_acquirability_score(p),
        reverse=True,
    )
    return candidates[:limit]


def _my_surplus_offer_pool(
    my_annotated: list[dict[str, Any]],
    *,
    hook_pos: str,
    my_surplus_positions: set[str],
) -> list[dict[str, Any]]:
    """Assets we offer when buying from a surplus hook (non-hook surplus positions)."""
    pos = hook_pos.upper()
    eligible: list[dict[str, Any]] = []
    for player in my_annotated:
        player_pos = (player.get("position") or "").upper()
        if player_pos == pos:
            continue
        if player_pos not in my_surplus_positions and "FLEX" not in my_surplus_positions:
            continue
        if player_pos not in my_surplus_positions and player_pos not in {"RB", "WR", "TE"}:
            continue
        if player.get("trade_tag") == "core":
            continue
        eligible.append(player)

    trade_first = [p for p in eligible if p.get("trade_tag") == "trade"]
    if trade_first:
        trade_first.sort(key=lambda p: p.get("lineup_delta_ppg") or 0)
        return trade_first[:4]
    depth = [p for p in eligible if int(p.get("depth_rank") or 99) >= 2]
    depth.sort(key=lambda p: p.get("lineup_delta_ppg") or 0)
    return depth[:4]


# Stud acquisition: slight overpay is expected; block lopsided wins and cheap core steals.
ACQUISITION_OVERPAY_BAND = 0.15
ACQUISITION_MAX_FAVOR_YOU = 0.05
ACQUISITION_MAX_SWING = 0.28
CORE_TARGET_EXTRA_OVERPAY = 0.10


def _find_player_on_rosters(
    roster_players: dict[str, list[dict[str, Any]]],
    player_id: str,
) -> tuple[str, dict[str, Any]] | None:
    pid = str(player_id)
    for roster_id, players in roster_players.items():
        for player in players:
            if str(player.get("player_id") or "") == pid:
                return str(roster_id), player
    return None


def _acquisition_package_ok(
    fairness: dict[str, Any],
    *,
    target_is_core: bool,
    give_assets: list[dict[str, Any]] | None = None,
    lubricant_mode: bool = False,
) -> bool:
    pct = float(fairness.get("net_delta_adjusted_pct") or 0) / 100.0
    max_overpay = ACQUISITION_OVERPAY_BAND + (
        CORE_TARGET_EXTRA_OVERPAY if target_is_core else 0.0
    )
    if lubricant_mode and give_assets and any(a.get("player_id") for a in give_assets):
        # Depth + future picks for a stud often needs more real-world overpay.
        max_overpay = max(max_overpay, 0.22)
    if pct > ACQUISITION_MAX_FAVOR_YOU:
        return False
    if pct < -max_overpay:
        return False
    if abs(pct) > ACQUISITION_MAX_SWING:
        return False
    return True


def _unique_packages(
    candidates: list[tuple[list[dict[str, Any]], list[dict[str, Any]]]],
) -> list[tuple[list[dict[str, Any]], list[dict[str, Any]]]]:
    seen: set[str] = set()
    out: list[tuple[list[dict[str, Any]], list[dict[str, Any]]]] = []
    for give, recv in candidates:
        key = json.dumps(
            {
                "give": sorted(
                    [
                        p.get("player_id")
                        or f"{p.get('season')}-{p.get('round')}-{p.get('original_roster_id')}"
                        for p in give
                    ]
                ),
                "recv": sorted(
                    [
                        p.get("player_id")
                        or f"{p.get('season')}-{p.get('round')}-{p.get('original_roster_id')}"
                        for p in recv
                    ]
                ),
            },
            sort_keys=True,
        )
        if key in seen:
            continue
        seen.add(key)
        out.append((give, recv))
    return out


KEY_POSITION_DEFAULTS: dict[str, dict[str, Any]] = {
    "RB": {"min_tv": 5500, "max_age": 28},
    "WR": {"min_tv": 5500, "max_age": 28},
    "QB": {"min_tv": 6000, "max_age": 30},
    "TE": {"min_tv": 4500, "max_age": 29},
}


def _league_key_players_at_position(
    roster_players: dict[str, list[dict[str, Any]]],
    *,
    my_roster_id: str,
    position: str,
    min_tv: float,
    max_age: int,
    limit: int = 12,
) -> list[tuple[str, dict[str, Any]]]:
    pos = position.upper()
    targets: list[tuple[str, dict[str, Any]]] = []
    for roster_id, players in roster_players.items():
        if str(roster_id) == str(my_roster_id):
            continue
        for player in players:
            if (player.get("position") or "").upper() != pos:
                continue
            tv = asset_tv(player)
            age = player.get("age")
            if tv < min_tv:
                continue
            if age is not None and int(age) > max_age:
                continue
            targets.append((str(roster_id), player))
    targets.sort(key=lambda row: asset_tv(row[1]), reverse=True)
    return targets[:limit]


def _target_acquirability_score(player: dict[str, Any]) -> float:
    """Prefer trade-tagged studs; deprioritize obvious core pieces."""
    tv = asset_tv(player)
    tag = player.get("trade_tag")
    if tag == "trade":
        return tv * 1.15
    if tag is None:
        return tv
    if tag == "core":
        return tv * 0.55
    return tv * 0.85


def generate_position_acquisition_packages(
    *,
    my_roster_id: str,
    target_position: str,
    roster_players: dict[str, list[dict[str, Any]]],
    picks_by_roster: dict[str, list[dict[str, Any]]],
    trade_surplus: dict[str, Any] | None = None,
    contender_tier_by_roster: dict[str, str] | None = None,
    team_names: dict[str, str] | None = None,
    max_suggestions: int = 8,
    max_targets: int = 10,
    min_tv: float | None = None,
    max_age: int | None = None,
    keep_current_first: bool = True,
    lubricant_mode: bool = True,
) -> list[dict[str, Any]]:
    """Scan the league for key players at a position and build acquisition packages."""
    pos = target_position.upper()
    defaults = KEY_POSITION_DEFAULTS.get(pos, {"min_tv": 5000, "max_age": 28})
    min_tv_val = float(min_tv if min_tv is not None else defaults["min_tv"])
    max_age_val = int(max_age if max_age is not None else defaults["max_age"])

    ranked_targets: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
    for their_id, player in _league_key_players_at_position(
        roster_players,
        my_roster_id=my_roster_id,
        position=pos,
        min_tv=min_tv_val,
        max_age=max_age_val,
        limit=max_targets * 2,
    ):
        their_tier = (contender_tier_by_roster or {}).get(their_id)
        annotated = annotate_players_with_trade_tags(
            roster_players.get(their_id, []),
            surplus_positions=set(),
            contender_tier=their_tier,
        )
        annotated_by_id = {str(p["player_id"]): p for p in annotated}
        row = annotated_by_id.get(str(player["player_id"]), player)
        ranked_targets.append((their_id, player, row))

    ranked_targets.sort(key=lambda t: _target_acquirability_score(t[2]), reverse=True)
    seen_players: set[str] = set()
    all_packages: list[dict[str, Any]] = []

    for their_id, _player, row in ranked_targets:
        pid = str(row.get("player_id") or "")
        if not pid or pid in seen_players:
            continue
        seen_players.add(pid)
        if len(seen_players) > max_targets:
            break

        for pkg in generate_acquisition_packages(
            my_roster_id=my_roster_id,
            target_player_id=pid,
            roster_players=roster_players,
            picks_by_roster=picks_by_roster,
            trade_surplus=trade_surplus,
            contender_tier_by_roster=contender_tier_by_roster,
            max_suggestions=2,
            keep_current_first=keep_current_first,
            lubricant_mode=lubricant_mode,
        ):
            cp = pkg.setdefault("counterparty", {})
            cp["team_name"] = (team_names or {}).get(their_id)
            cp["target_trade_tag"] = row.get("trade_tag")
            cp["target_tv"] = asset_tv(row)
            cp["target_age"] = row.get("age")
            all_packages.append(pkg)

    # One best package per target player, then rank globally.
    best_by_target: dict[str, dict[str, Any]] = {}
    for pkg in all_packages:
        cp = pkg.get("counterparty") or {}
        pid = str(cp.get("target_player_id") or "")
        if not pid:
            continue
        prev = best_by_target.get(pid)
        if prev is None or (pkg.get("acquisition_score") or 0) > (prev.get("acquisition_score") or 0):
            best_by_target[pid] = pkg

    merged = list(best_by_target.values())
    merged.sort(
        key=lambda s: (s.get("acquisition_score") or 0, s.get("package_quality") or 0),
        reverse=True,
    )
    return merged[:max_suggestions]


def _pick_slot_key(pick: dict[str, Any]) -> tuple[str, int, str]:
    return (str(pick["season"]), int(pick["round"]), str(pick["original_roster_id"]))


def _filter_reserved_picks(
    picks: list[dict[str, Any]],
    reserved: set[tuple[str, int, str]],
) -> list[dict[str, Any]]:
    if not reserved:
        return picks
    return [p for p in picks if _pick_slot_key(p) not in reserved]


def _default_reserved_picks(
    my_roster_id: str,
    picks: list[dict[str, Any]],
    *,
    keep_current_first: bool,
    current_season: str = "2026",
) -> set[tuple[str, int, str]]:
    """Reserve own current-year R1 (e.g. 1.01 for Jeremiah Love class)."""
    if not keep_current_first:
        return set()
    reserved: set[tuple[str, int, str]] = set()
    for pick in picks:
        if (
            str(pick.get("season")) == current_season
            and int(pick.get("round") or 0) == 1
            and str(pick.get("original_roster_id")) == str(my_roster_id)
        ):
            reserved.add(_pick_slot_key(pick))
    return reserved


def _build_acquisition_templates(
    target_row: dict[str, Any],
    *,
    my_picks: list[dict[str, Any]],
    my_trade_players: list[dict[str, Any]],
    their_picks: list[dict[str, Any]],
    reserved_pick_keys: set[tuple[str, int, str]],
    current_season: str = "2026",
    lubricant_mode: bool = True,
) -> list[tuple[list[dict[str, Any]], list[dict[str, Any]]]]:
    """Package shapes for stud acquisition. Lubricant mode favors cross-year picks + depth."""
    templates: list[tuple[list[dict[str, Any]], list[dict[str, Any]]]] = []
    available = _filter_reserved_picks(my_picks, reserved_pick_keys)
    current_picks = sorted(
        [p for p in available if str(p.get("season")) == current_season],
        key=asset_tv,
        reverse=True,
    )
    future_picks = sorted(
        [p for p in available if str(p.get("season")) > current_season],
        key=asset_tv,
        reverse=True,
    )
    current_non_r1 = [p for p in current_picks if int(p.get("round") or 0) >= 2]
    future_1sts = [p for p in future_picks if int(p.get("round") or 0) == 1]
    their_future_1sts = [
        p
        for p in their_picks
        if int(p.get("round") or 0) == 1 and str(p.get("season")) > current_season
    ]

    top_trade = my_trade_players[:4]
    target_pos = (target_row.get("position") or "").upper()
    pos_swap = [
        p
        for p in my_trade_players
        if (p.get("position") or "").upper() == target_pos
    ]
    offer_players = list(top_trade[:4])
    for p in pos_swap:
        if p not in offer_players:
            offer_players.append(p)

    their_current_late = [
        p
        for p in their_picks
        if str(p.get("season")) == current_season and int(p.get("round") or 0) >= 3
    ]
    their_future_late = [
        p
        for p in their_picks
        if str(p.get("season")) > current_season and int(p.get("round") or 0) >= 2
    ]
    pick_backs = (their_future_late + their_current_late)[:3]

    def _with_pick_backs(
        give: list[dict[str, Any]],
    ) -> list[tuple[list[dict[str, Any]], list[dict[str, Any]]]]:
        out: list[tuple[list[dict[str, Any]], list[dict[str, Any]]]] = [(
            give,
            [target_row],
        )]
        give_tv = sum(asset_tv(a) for a in give)
        target_tv = asset_tv(target_row)
        if give_tv > target_tv * 1.06:
            for back in pick_backs:
                out.append((give, [target_row, back]))
        return out

    if lubricant_mode:
        # Cross-year lubricant: future 1st + trade depth (no current 1.01).
        if future_1sts and top_trade:
            templates.append(([top_trade[0], future_1sts[0]], [target_row]))
        if future_1sts and len(top_trade) >= 2:
            templates.append(([top_trade[0], top_trade[1], future_1sts[0]], [target_row]))
        if future_1sts and current_non_r1:
            templates.append(([current_non_r1[0], future_1sts[0]], [target_row]))
        if future_1sts and len(current_non_r1) >= 2:
            templates.append(([current_non_r1[0], current_non_r1[1], future_1sts[0]], [target_row]))
        if len(future_1sts) >= 2:
            templates.append((future_1sts[:2], [target_row]))
        if future_1sts:
            templates.append(([future_1sts[0]], [target_row]))
        # Future-for-future back (not same-season slot swaps).
        if future_1sts and their_future_1sts:
            templates.append(([future_1sts[0]], [target_row, their_future_1sts[0]]))
        # Player + current picks (2.01 + 3.01 style) — picks as lubricant, not 1.01.
        for player in offer_players[:5]:
            if len(current_non_r1) >= 2:
                templates.extend(
                    _with_pick_backs([player, current_non_r1[0], current_non_r1[1]])
                )
            if current_non_r1:
                templates.extend(_with_pick_backs([player, current_non_r1[0]]))
            if current_non_r1 and future_1sts:
                templates.append(([player, current_non_r1[0], future_1sts[0]], [target_row]))
        if top_trade and current_non_r1:
            templates.append(([top_trade[0], current_non_r1[0]], [target_row]))
        if len(top_trade) >= 2 and current_non_r1:
            templates.append(([top_trade[0], top_trade[1], current_non_r1[0]], [target_row]))
        if len(top_trade) >= 2 and future_1sts and current_non_r1:
            templates.append(
                ([top_trade[0], current_non_r1[0], future_1sts[0]], [target_row])
            )
        return templates

    # Premium mode: may include reserved picks (1.01) in overload packages.
    top_picks = available[:4]
    their_1sts = [p for p in their_picks if int(p.get("round") or 0) == 1][:2]
    if len(top_picks) >= 3:
        templates.append((top_picks[:3], [target_row]))
    if len(top_picks) >= 2:
        templates.append((top_picks[:2], [target_row]))
    if top_picks:
        templates.append(([top_picks[0]], [target_row]))
    if top_picks and top_trade:
        templates.append(([top_trade[0], top_picks[0]], [target_row]))
    if len(top_picks) >= 2 and top_trade:
        templates.append(([top_trade[0], *top_picks[:2]], [target_row]))
    if len(top_trade) >= 2 and top_picks:
        templates.append(([top_trade[0], top_trade[1], top_picks[0]], [target_row]))
    if len(top_picks) >= 2 and their_1sts:
        templates.append((top_picks[:2], [target_row, their_1sts[0]]))
    return templates


def generate_acquisition_packages(
    *,
    my_roster_id: str,
    target_player_id: str,
    roster_players: dict[str, list[dict[str, Any]]],
    picks_by_roster: dict[str, list[dict[str, Any]]],
    trade_surplus: dict[str, Any] | None = None,
    contender_tier_by_roster: dict[str, str] | None = None,
    max_suggestions: int = 5,
    keep_current_first: bool = True,
    lubricant_mode: bool = True,
    current_season: str = "2026",
) -> list[dict[str, Any]]:
    """Build stud-acquisition packages for a specific counterparty player."""
    located = _find_player_on_rosters(roster_players, target_player_id)
    if located is None:
        return []
    their_id, target = located
    if their_id == str(my_roster_id):
        return []

    my_tier = (contender_tier_by_roster or {}).get(str(my_roster_id))
    their_tier = (contender_tier_by_roster or {}).get(their_id)
    ts = trade_surplus or {}
    my_surplus_positions = {row["position"] for row in ts.get("surplus") or []}
    my_need_positions = {row["position"] for row in ts.get("needs") or []}

    their_players = roster_players.get(their_id, [])
    their_annotated = {
        str(p["player_id"]): p
        for p in annotate_players_with_trade_tags(
            their_players,
            surplus_positions=set(),
            contender_tier=their_tier,
        )
    }
    target_row = their_annotated.get(str(target_player_id), target)
    target_is_core = target_row.get("trade_tag") == "core"

    my_players = roster_players.get(str(my_roster_id), [])
    my_annotated = annotate_players_with_trade_tags(
        my_players,
        surplus_positions=my_surplus_positions,
        contender_tier=my_tier,
    )
    my_trade_players = [
        p
        for p in my_annotated
        if p.get("trade_tag") != "core"
        and (
            p.get("trade_tag") == "trade"
            or (p.get("depth_rank") or 99) >= 3
            or (
                (p.get("position") or "").upper()
                == (target_row.get("position") or "").upper()
                and p.get("trade_tag") != "core"
            )
        )
    ]
    my_trade_players.sort(key=lambda p: asset_tv(p), reverse=True)

    my_picks = annotate_picks_with_trade_tags(
        picks_by_roster.get(str(my_roster_id), []),
        contender_tier=my_tier,
    )
    my_picks.sort(key=lambda p: asset_tv(p), reverse=True)
    reserved_keys = _default_reserved_picks(
        str(my_roster_id),
        my_picks,
        keep_current_first=keep_current_first,
        current_season=current_season,
    )

    their_picks = sorted(
        picks_by_roster.get(their_id, []),
        key=lambda p: asset_tv(p),
        reverse=True,
    )
    their_1sts = [p for p in their_picks if int(p.get("round") or 0) == 1][:2]

    tradability_by_id = {
        str(p["player_id"]): (
            0.85 if p.get("trade_tag") == "trade" else 0.05 if p.get("trade_tag") == "core" else 0.35
        )
        for p in my_annotated
    }

    templates = _build_acquisition_templates(
        target_row,
        my_picks=my_picks,
        my_trade_players=my_trade_players,
        their_picks=their_picks,
        reserved_pick_keys=reserved_keys,
        current_season=current_season,
        lubricant_mode=lubricant_mode,
    )

    suggestions: list[dict[str, Any]] = []
    for give_list, recv_list in _unique_packages(templates):
        if any(p.get("trade_tag") == "core" for p in give_list if p.get("player_id")):
            continue
        if target_is_core and not any(
            int(p.get("round") or 0) == 1 for p in give_list if not p.get("player_id")
        ):
            continue
        if reserved_keys and any(
            _pick_slot_key(p) in reserved_keys for p in give_list if not p.get("player_id")
        ):
            continue

        fairness = evaluate_package_fairness(give_list, recv_list)
        stretch = not _acquisition_package_ok(
            fairness,
            target_is_core=target_is_core,
            give_assets=give_list,
            lubricant_mode=lubricant_mode,
        )
        if stretch and not lubricant_mode:
            continue
        if stretch and abs(float(fairness.get("net_delta_adjusted_pct") or 0)) > ACQUISITION_MAX_SWING * 100:
            continue

        give_player_rows = [p for p in give_list if p.get("player_id")]
        recv_player_rows = [p for p in recv_list if p.get("player_id")]
        quality = package_quality_score(
            give_players=give_player_rows,
            recv_players=recv_player_rows,
            give_assets=give_list,
            tradability_by_id=tradability_by_id,
            acquirer_need_positions=my_need_positions,
            acquirer_surplus_positions=my_surplus_positions,
            acquirer_tier=my_tier,
            seller_tier=their_tier,
            fairness=fairness,
        )
        closeness = 1.0 - abs(float(fairness.get("net_delta_adjusted_pct") or 0)) / 100.0
        suggestions.append(
            {
                "counterparty": {
                    "roster_id": their_id,
                    "team_name": None,
                    "direction": "acquire",
                    "position_hook": target_row.get("position"),
                    "contender_tier": their_tier,
                    "target_player_id": str(target_player_id),
                    "target_player_name": target_row.get("name"),
                    "target_is_core": target_is_core,
                    "reserved_picks": [
                        f"{s} R{r}" for s, r, _ in sorted(reserved_keys)
                    ],
                    "lubricant_mode": lubricant_mode,
                },
                "give": {
                    "players": give_player_rows,
                    "picks": [p for p in give_list if not p.get("player_id")],
                },
                "receive": {
                    "players": recv_player_rows,
                    "picks": [p for p in recv_list if not p.get("player_id")],
                },
                **fairness,
                "package_quality": quality,
                "stretch": stretch,
                "acquisition_score": round(quality * 0.6 + closeness * 40 - (10 if stretch else 0), 2),
                "rationale": (
                    f"Acquire {target_row.get('name')} ({target_row.get('position')}) — "
                    f"{'core target; paid with premium picks' if target_is_core else 'stud acquisition'}; "
                    f"adj {fairness.get('net_delta_adjusted_pct'):+.1f}%"
                ),
            }
        )

    suggestions.sort(
        key=lambda s: (s.get("acquisition_score") or 0, s.get("package_quality") or 0),
        reverse=True,
    )
    return suggestions[:max_suggestions]


def _position_pool(
    annotated: list[dict[str, Any]],
    position: str,
    *,
    exclude_core: bool = True,
    min_depth: int = 1,
    max_depth: int = 99,
    trade_preferred: bool = False,
) -> list[dict[str, Any]]:
    pos = position.upper()
    pool: list[dict[str, Any]] = []
    for player in annotated:
        if (player.get("position") or "").upper() != pos:
            continue
        if exclude_core and player.get("trade_tag") == "core":
            continue
        depth = int(player.get("depth_rank") or 99)
        if depth < min_depth or depth > max_depth:
            continue
        pool.append(player)
    if trade_preferred:
        pool.sort(
            key=lambda p: (1 if p.get("trade_tag") == "trade" else 0, asset_tv(p)),
            reverse=True,
        )
    else:
        pool.sort(key=asset_tv, reverse=True)
    return pool


def generate_need_swap_packages(
    *,
    my_roster_id: str,
    roster_players: dict[str, list[dict[str, Any]]],
    picks_by_roster: dict[str, list[dict[str, Any]]],
    trade_surplus: dict[str, Any] | None = None,
    contender_tier_by_roster: dict[str, str] | None = None,
    team_names: dict[str, str] | None = None,
    need_position: str | None = None,
    target_player_id: str | None = None,
    max_suggestions: int = 8,
    keep_current_first: bool = True,
    lubricant_mode: bool = True,
    current_season: str = "2026",
) -> list[dict[str, Any]]:
    """Mutual-need trades — surplus + depth out, stud + depth back."""
    ts = trade_surplus or {}
    my_surplus_positions = {row["position"] for row in ts.get("surplus") or []}
    my_need_positions = {row["position"] for row in ts.get("needs") or []}
    if need_position:
        my_need_positions = {need_position.upper()}
    if not my_need_positions:
        return []

    my_tier = (contender_tier_by_roster or {}).get(str(my_roster_id))
    my_annotated = annotate_players_with_trade_tags(
        roster_players.get(str(my_roster_id), []),
        surplus_positions=my_surplus_positions,
        contender_tier=my_tier,
    )
    tradability_by_id = {
        str(p["player_id"]): (
            0.85 if p.get("trade_tag") == "trade" else 0.05 if p.get("trade_tag") == "core" else 0.35
        )
        for p in my_annotated
    }
    my_picks = annotate_picks_with_trade_tags(
        picks_by_roster.get(str(my_roster_id), []),
        contender_tier=my_tier,
    )
    reserved_keys = _default_reserved_picks(
        str(my_roster_id), my_picks, keep_current_first=keep_current_first, current_season=current_season
    )
    available_picks = _filter_reserved_picks(my_picks, reserved_keys)
    current_non_r1 = [
        p
        for p in available_picks
        if str(p.get("season")) == current_season and int(p.get("round") or 0) >= 2
    ]
    future_1sts = [
        p
        for p in available_picks
        if str(p.get("season")) > current_season and int(p.get("round") or 0) == 1
    ]
    offer_surplus_positions = {p for p in my_surplus_positions if p != "FLEX"} or {"WR"}

    counterparties = [
        cp
        for cp in ts.get("counterparties") or []
        if cp.get("direction") == "buy" and (cp.get("position") or "").upper() in my_need_positions
    ]
    if target_player_id:
        located = _find_player_on_rosters(roster_players, target_player_id)
        if located:
            their_id, _ = located
            counterparties = [
                cp for cp in counterparties if str(cp.get("roster_id")) == their_id
            ] or [{"roster_id": their_id, "position": need_position or "?", "direction": "buy"}]

    suggestions: list[dict[str, Any]] = []
    seen_cp: set[str] = set()

    for cp in counterparties:
        their_id = str(cp.get("roster_id") or "")
        if not their_id or their_id in seen_cp or their_id == str(my_roster_id):
            continue
        seen_cp.add(their_id)
        need_pos = (cp.get("position") or "").upper()
        their_tier = (contender_tier_by_roster or {}).get(their_id)
        their_annotated = annotate_players_with_trade_tags(
            roster_players.get(their_id, []),
            surplus_positions=set(),
            contender_tier=their_tier,
        )
        their_studs = _position_pool(their_annotated, need_pos, min_depth=1, max_depth=2)
        if target_player_id:
            their_studs = [
                p for p in their_annotated if str(p.get("player_id")) == str(target_player_id)
            ] or their_studs[:1]
        if not their_studs:
            continue

        for surplus_pos in offer_surplus_positions:
            my_surplus = _position_pool(
                my_annotated, surplus_pos, min_depth=1, max_depth=6, trade_preferred=True
            )
            my_depth_at_need = _position_pool(
                my_annotated, need_pos, min_depth=2, max_depth=5, exclude_core=True
            )
            their_return = _position_pool(
                their_annotated, surplus_pos, min_depth=2, max_depth=5, exclude_core=True
            )
            if not my_surplus:
                continue

            templates: list[tuple[list[dict[str, Any]], list[dict[str, Any]]]] = []
            for stud in their_studs[:2]:
                for surplus_player in my_surplus[:3]:
                    depth_options: list[dict[str, Any] | None] = my_depth_at_need[:2] or [None]
                    for depth_piece in depth_options:
                        give_players = [surplus_player] + ([depth_piece] if depth_piece else [])
                        for back in their_return[:2] or [None]:
                            recv_players = [stud] + ([back] if back else [])
                            templates.append((give_players, recv_players))
                        if lubricant_mode and current_non_r1:
                            templates.append((give_players, [stud]))
                            templates.append(([*give_players, current_non_r1[0]], [stud]))
                            if future_1sts:
                                templates.append(([*give_players, future_1sts[0]], [stud]))

            for give_list, recv_list in _unique_packages(templates):
                if any(p.get("trade_tag") == "core" for p in give_list if p.get("player_id")):
                    continue
                fairness = evaluate_package_fairness(give_list, recv_list)
                pct = float(fairness.get("net_delta_adjusted_pct") or 0) / 100.0
                if abs(pct) > ACQUISITION_MAX_SWING:
                    continue
                if pct > ACQUISITION_MAX_FAVOR_YOU + 0.08:
                    continue

                stud_row = recv_list[0]
                give_player_rows = [p for p in give_list if p.get("player_id")]
                recv_player_rows = [p for p in recv_list if p.get("player_id")]
                quality = package_quality_score(
                    give_players=give_player_rows,
                    recv_players=recv_player_rows,
                    give_assets=give_list,
                    tradability_by_id=tradability_by_id,
                    acquirer_need_positions=my_need_positions,
                    acquirer_surplus_positions=my_surplus_positions,
                    acquirer_tier=my_tier,
                    seller_tier=their_tier,
                    fairness=fairness,
                )
                closeness = 1.0 - abs(pct)
                suggestions.append(
                    {
                        "counterparty": {
                            "roster_id": their_id,
                            "team_name": (team_names or {}).get(their_id),
                            "direction": "need_swap",
                            "position_hook": need_pos,
                            "surplus_hook": surplus_pos,
                            "contender_tier": their_tier,
                            "target_player_id": str(stud_row.get("player_id")),
                            "target_player_name": stud_row.get("name"),
                            "trade_pattern": "need_swap_with_depth",
                        },
                        "give": {
                            "players": give_player_rows,
                            "picks": [p for p in give_list if not p.get("player_id")],
                        },
                        "receive": {
                            "players": recv_player_rows,
                            "picks": [p for p in recv_list if not p.get("player_id")],
                        },
                        **fairness,
                        "package_quality": quality,
                        "acquisition_score": round(quality * 0.6 + closeness * 40, 2),
                        "rationale": (
                            f"Need {need_pos}: {surplus_pos} surplus"
                            + (
                                f" + {need_pos} depth"
                                if len(give_player_rows) > 1
                                and (give_player_rows[1].get("position") or "").upper() == need_pos
                                else ""
                            )
                            + f" for {stud_row.get('name')}"
                            + (
                                f" + {recv_player_rows[1].get('name')}"
                                if len(recv_player_rows) > 1
                                else ""
                            )
                            + f" ({fairness.get('net_delta_adjusted_pct'):+.1f}% adj)"
                        ),
                    }
                )

    if target_player_id:
        for pkg in generate_acquisition_packages(
            my_roster_id=my_roster_id,
            target_player_id=str(target_player_id),
            roster_players=roster_players,
            picks_by_roster=picks_by_roster,
            trade_surplus=trade_surplus,
            contender_tier_by_roster=contender_tier_by_roster,
            max_suggestions=3,
            keep_current_first=keep_current_first,
            lubricant_mode=lubricant_mode,
            current_season=current_season,
        ):
            cp = pkg.setdefault("counterparty", {})
            cp["trade_pattern"] = "same_position_upgrade"
            cp["direction"] = "need_swap"
            suggestions.append(pkg)

    suggestions.sort(
        key=lambda s: (s.get("acquisition_score") or 0, s.get("package_quality") or 0),
        reverse=True,
    )
    return suggestions[:max_suggestions]


def generate_trade_suggestions(
    *,
    my_roster_id: str,
    trade_surplus: dict[str, Any] | None,
    roster_players: dict[str, list[dict[str, Any]]],
    picks_by_roster: dict[str, list[dict[str, Any]]],
    target_roster_id: str | None = None,
    target_player_id: str | None = None,
    target_position: str | None = None,
    max_suggestions: int = 5,
    contender_tier_by_roster: dict[str, str] | None = None,
    keep_current_first: bool = True,
    lubricant_mode: bool = True,
) -> list[dict[str, Any]]:
    """Trade packages from trade_surplus or targeted stud acquisition."""
    if target_player_id:
        return generate_acquisition_packages(
            my_roster_id=my_roster_id,
            target_player_id=str(target_player_id),
            roster_players=roster_players,
            picks_by_roster=picks_by_roster,
            trade_surplus=trade_surplus,
            contender_tier_by_roster=contender_tier_by_roster,
            max_suggestions=max_suggestions,
            keep_current_first=keep_current_first,
            lubricant_mode=lubricant_mode,
        )

    if target_position and not target_roster_id:
        return generate_position_acquisition_packages(
            my_roster_id=my_roster_id,
            target_position=target_position,
            roster_players=roster_players,
            picks_by_roster=picks_by_roster,
            trade_surplus=trade_surplus,
            contender_tier_by_roster=contender_tier_by_roster,
            max_suggestions=max(max_suggestions, 8),
            keep_current_first=keep_current_first,
            lubricant_mode=lubricant_mode,
        )

    if target_position and target_roster_id:
        pos = target_position.upper()
        their_players = roster_players.get(str(target_roster_id), [])
        ranked = sorted(
            [p for p in their_players if (p.get("position") or "").upper() == pos],
            key=asset_tv,
            reverse=True,
        )
        if ranked:
            return generate_acquisition_packages(
                my_roster_id=my_roster_id,
                target_player_id=str(ranked[0]["player_id"]),
                roster_players=roster_players,
                picks_by_roster=picks_by_roster,
                trade_surplus=trade_surplus,
                contender_tier_by_roster=contender_tier_by_roster,
                max_suggestions=max_suggestions,
            )

    if not trade_surplus:
        return []

    my_players = roster_players.get(str(my_roster_id), [])
    my_surplus_positions = {row["position"] for row in trade_surplus.get("surplus") or []}
    my_need_positions = {row["position"] for row in trade_surplus.get("needs") or []}
    my_tier = (contender_tier_by_roster or {}).get(str(my_roster_id))

    my_annotated = annotate_players_with_trade_tags(
        my_players,
        surplus_positions=my_surplus_positions,
        contender_tier=my_tier,
    )
    tradability_by_id = {
        str(p["player_id"]): (
            0.85
            if p.get("trade_tag") == "trade"
            else 0.05
            if p.get("trade_tag") == "core"
            else 0.35
        )
        for p in my_annotated
    }
    my_trade_picks = [
        p
        for p in annotate_picks_with_trade_tags(
            picks_by_roster.get(str(my_roster_id), []),
            contender_tier=my_tier,
        )
        if p.get("trade_tag") == "trade"
    ]
    reserved_keys = _default_reserved_picks(
        str(my_roster_id),
        picks_by_roster.get(str(my_roster_id), []),
        keep_current_first=keep_current_first,
    )
    balance_picks = _filter_reserved_picks(my_trade_picks, reserved_keys)
    if lubricant_mode:
        balance_picks = [
            p
            for p in balance_picks
            if not (
                str(p.get("season")) == "2026" and int(p.get("round") or 0) == 1
            )
        ] or balance_picks

    counterparties = trade_surplus.get("counterparties") or []
    if target_roster_id:
        counterparties = [
            c for c in counterparties if str(c.get("roster_id")) == str(target_roster_id)
        ]

    seen: set[tuple[str, str, str]] = set()
    suggestions: list[dict[str, Any]] = []

    for cp in counterparties:
        their_id = str(cp.get("roster_id") or "")
        pos = cp.get("position") or ""
        direction = cp.get("direction") or ""
        key = (their_id, pos, direction)
        if key in seen or not their_id:
            continue
        seen.add(key)

        their_players = roster_players.get(their_id, [])
        if not their_players:
            continue

        their_tier = (contender_tier_by_roster or {}).get(their_id)
        their_annotated = annotate_players_with_trade_tags(
            their_players,
            surplus_positions=set(),
            contender_tier=their_tier,
        )

        if direction == "sell" and pos not in my_surplus_positions:
            continue
        if direction == "buy" and pos not in my_need_positions:
            continue

        if direction == "sell":
            give_candidates = _surplus_give_pool(
                my_annotated, pos, my_surplus_positions=my_surplus_positions
            )
            recv_candidates = _counterparty_recv_pool(
                their_annotated,
                direction=direction,
                hook_pos=pos,
                my_need_positions=my_need_positions,
                my_surplus_positions=my_surplus_positions,
                my_tier=my_tier,
                their_tier=their_tier,
            )
        else:
            recv_candidates = _counterparty_recv_pool(
                their_annotated,
                direction=direction,
                hook_pos=pos,
                my_need_positions=my_need_positions,
                my_surplus_positions=my_surplus_positions,
                my_tier=my_tier,
                their_tier=their_tier,
            )
            give_candidates = _my_surplus_offer_pool(
                my_annotated,
                hook_pos=pos,
                my_surplus_positions=my_surplus_positions,
            )

        if not recv_candidates:
            continue
        if not give_candidates:
            continue

        package_templates: list[tuple[list[dict[str, Any]], list[dict[str, Any]]]] = []
        for give_asset in give_candidates[:3]:
            for recv_asset in recv_candidates[:3]:
                package_templates.append(([give_asset], [recv_asset]))
                if len(give_candidates) > 1 and len(recv_candidates) > 1:
                    alt_give = give_candidates[1] if give_asset != give_candidates[1] else give_candidates[0]
                    alt_recv = recv_candidates[1] if recv_asset != recv_candidates[1] else recv_candidates[0]
                    package_templates.append(([give_asset, alt_give], [recv_asset, alt_recv]))

        for give_list, recv_list in _unique_packages(package_templates):
            give_list, recv_list = _balance_with_pick(
                give_list,
                recv_list,
                my_picks=balance_picks,
                their_picks=picks_by_roster.get(their_id, []),
            )
            if reserved_keys and any(
                not p.get("player_id") and _pick_slot_key(p) in reserved_keys
                for p in give_list
            ):
                continue

            fairness = evaluate_package_fairness(give_list, recv_list)
            pct = abs(float(fairness.get("net_delta_adjusted_pct") or 0))
            if pct > ACQUISITION_MAX_SWING * 100:
                continue

            give_player_rows = [p for p in give_list if p.get("player_id")]
            recv_player_rows = [p for p in recv_list if p.get("player_id")]
            quality = package_quality_score(
                give_players=give_player_rows,
                recv_players=recv_player_rows,
                give_assets=give_list,
                tradability_by_id=tradability_by_id,
                acquirer_need_positions=my_need_positions,
                acquirer_surplus_positions=my_surplus_positions,
                acquirer_tier=my_tier,
                seller_tier=their_tier,
                fairness=fairness,
            )
            avg_fit = (
                sum(
                    trade_fit_score(
                        p,
                        acquirer_need_positions=my_need_positions,
                        acquirer_surplus_positions=my_surplus_positions,
                        acquirer_tier=my_tier,
                        seller_tier=their_tier,
                    )
                    for p in recv_player_rows
                )
                / len(recv_player_rows)
                if recv_player_rows
                else 0.0
            )
            avg_tradability = (
                sum(tradability_by_id.get(str(p.get("player_id")), 0.35) for p in give_player_rows)
                / len(give_player_rows)
                if give_player_rows
                else 0.85
                if any(not p.get("player_id") for p in give_list)
                else 0.0
            )

            suggestions.append(
                {
                    "counterparty": {
                        "roster_id": their_id,
                        "team_name": cp.get("team_name"),
                        "direction": direction,
                        "position_hook": pos,
                        "contender_tier": their_tier,
                    },
                    "give": {
                        "players": give_player_rows,
                        "picks": [p for p in give_list if not p.get("player_id")],
                    },
                    "receive": {
                        "players": recv_player_rows,
                        "picks": [p for p in recv_list if not p.get("player_id")],
                    },
                    **fairness,
                    "package_quality": quality,
                    "avg_tradability": round(avg_tradability, 3),
                    "avg_trade_fit": round(avg_fit, 3),
                    "rationale": (
                        f"{'Sell' if direction == 'sell' else 'Buy'} {pos} leverage — "
                        f"they rank #{cp.get('their_rank')} at {pos}, you rank #{cp.get('my_rank')}"
                    ),
                }
            )

    suggestions.sort(key=lambda s: s.get("package_quality") or 0, reverse=True)
    return suggestions[: max(max_suggestions, 12)]


@dataclass
class AdvisorToolContext:
    db: Session
    league_id: str
    my_roster_id: str
    focused_roster_id: str


class AdvisorTools:
    def __init__(self, ctx: AdvisorToolContext):
        self.ctx = ctx
        self._snapshots: dict[str, PlayerSnapshot] | None = None
        self._pick_index: dict[tuple[str, int, str], dict[str, Any]] | None = None

    def _load_snapshots(self) -> dict[str, PlayerSnapshot]:
        if self._snapshots is None:
            self._snapshots = {
                row.sleeper_player_id: row
                for row in self.ctx.db.scalars(
                    select(PlayerSnapshot).where(
                        PlayerSnapshot.league_id == self.ctx.league_id
                    )
                ).all()
            }
        return self._snapshots

    def _load_pick_index(self) -> dict[tuple[str, int, str], dict[str, Any]]:
        if self._pick_index is None:
            rows = self.ctx.db.scalars(
                select(RosterDraftPick).where(
                    RosterDraftPick.league_id == self.ctx.league_id
                )
            ).all()
            self._pick_index = {
                (row.season, row.round, row.original_roster_id): {
                    "season": row.season,
                    "round": row.round,
                    "original_roster_id": row.original_roster_id,
                    "owner_roster_id": row.owner_roster_id,
                    "slot_tier": row.slot_tier,
                    "trade_value": row.trade_value,
                    "label": row.label,
                }
                for row in rows
            }
        return self._pick_index

    def _resolve_player(self, player_id: str) -> dict[str, Any] | None:
        snap = self._load_snapshots().get(player_id)
        if snap is None:
            return None
        return {
            "player_id": snap.sleeper_player_id,
            "name": snap.player_name,
            "position": snap.position,
            "ovr": snap.dynasty_rating,
            "tv": snap.trade_value,
            "hppg": snap.hppg,
            "injury": snap.injury_status,
        }

    def _resolve_pick(self, pick: dict[str, Any]) -> dict[str, Any] | None:
        key = _pick_key(pick)
        return self._load_pick_index().get(key)

    def _roster_player_ids(self, roster_id: str) -> list[str]:
        roster = self.ctx.db.scalar(
            select(Roster).where(
                Roster.league_id == self.ctx.league_id,
                Roster.sleeper_roster_id == roster_id,
            )
        )
        if roster is None:
            return []
        from backend.db.models import RosterPlayer

        return [
            rp.sleeper_player_id
            for rp in self.ctx.db.scalars(
                select(RosterPlayer).where(RosterPlayer.roster_id == roster.id)
            ).all()
        ]

    def _position_strength(self) -> dict[str, Any] | None:
        from backend.services.read_service import get_league_analysis

        analysis = get_league_analysis(self.ctx.db, self.ctx.league_id)
        if analysis is None or analysis.position_strength is None:
            return None
        return analysis.position_strength.model_dump()

    def proposer_roster_id(self) -> str:
        """Roster whose assets/surplus drive trade tools (focused team when pivoted)."""
        return str(self.ctx.focused_roster_id or self.ctx.my_roster_id)

    def _trade_surplus(self) -> dict[str, Any] | None:
        from backend.services.analysis_service import compute_trade_surplus_for_roster
        from backend.services.read_service import get_league_analysis

        pos_strength = self._position_strength()
        proposer = self.proposer_roster_id
        if pos_strength:
            computed = compute_trade_surplus_for_roster(pos_strength, proposer)
            if computed:
                return computed

        analysis = get_league_analysis(self.ctx.db, self.ctx.league_id)
        if analysis is None or analysis.trade_surplus is None:
            return None
        cached = analysis.trade_surplus.model_dump()
        if str(cached.get("roster_id")) == proposer:
            return cached
        return None

    def _contender_tier_by_roster(self) -> dict[str, str]:
        from backend.services.read_service import get_league_analysis

        analysis = get_league_analysis(self.ctx.db, self.ctx.league_id)
        if analysis is None or analysis.contender_index is None:
            return {}
        return {
            str(row.roster_id): row.tier
            for row in analysis.contender_index.teams
            if row.tier
        }

    def get_team(self, roster_id: str) -> dict[str, Any]:
        detail = get_team_detail(self.ctx.db, self.ctx.league_id, str(roster_id))
        if detail is None:
            return {"error": f"Team {roster_id} not found"}

        pos_strength = self._position_strength()
        pos_info = _team_surplus_needs(pos_strength, str(roster_id))
        surplus_positions = {row["position"] for row in pos_info["surplus"]}
        roster_rows = [
            {
                "player_id": p.player_id,
                "name": p.player_name,
                "position": p.position,
                "pos": p.position,
                "ovr": p.ovr,
                "tv": p.trade_value,
                "hppg": p.hppg,
                "projected_ppg": p.projected_ppg,
                "age": p.age,
            }
            for p in detail.roster[:TOP_ROSTER_PLAYERS]
        ]
        players = annotate_players_with_trade_tags(
            roster_rows,
            surplus_positions=surplus_positions,
            contender_tier=detail.contender_tier,
        )
        trade_candidates = top_trade_candidates(
            roster_rows,
            picks=[p.model_dump() for p in detail.draft_picks],
            surplus_positions=surplus_positions,
            contender_tier=detail.contender_tier,
        )
        return {
            "roster_id": detail.roster_id,
            "team_name": detail.team_name,
            "is_me": detail.is_me,
            "dynasty_rank": detail.dynasty_rank,
            "contender_tier": detail.contender_tier,
            "avg_dynasty_rating": detail.avg_dynasty_rating,
            "starter_total_ppg": detail.starter_total_ppg,
            "total_trade_value": detail.total_trade_value,
            "draft_pick_value": detail.draft_pick_value,
            "needs": pos_info["needs"],
            "surplus": pos_info["surplus"],
            "starter_needs": _starter_needs_from_detail(detail),
            "draft_picks": [p.model_dump() for p in detail.draft_picks],
            "players": players,
            "trade_candidates": trade_candidates,
            "injuries": [i.model_dump() for i in detail.injuries],
        }

    def get_player(self, player_id: str) -> dict[str, Any]:
        card = get_player_card(self.ctx.db, str(player_id), self.ctx.league_id)
        if card is None:
            return {"error": f"Player {player_id} not found in league pool"}
        return {
            "player_id": card.player_id,
            "name": card.player_name,
            "position": card.position,
            "ovr": card.ovr,
            "tv": card.trade_value,
            "hppg": card.hppg,
            "hppg_expected": card.hppg_expected,
            "worp_ppg": card.worp_ppg,
            "injury_status": card.injury_status,
            "injury_body_part": card.injury_body_part,
            "outlook": card.outlook,
            "win_now_rating": card.lenses.win_now_rating if card.lenses else None,
            "age": card.age,
            "trade_tag": card.trade_tag,
            "lineup_delta_ppg": card.lineup_delta_ppg,
            "tv_vs_production_gap": card.tv_vs_production_gap,
            "depth_rank": card.depth_rank,
        }

    def search_players(self, query: str, position: str | None = None) -> dict[str, Any]:
        q = query.strip()
        if len(q) < 2:
            return {"query": q, "hits": [], "note": "query must be at least 2 characters"}

        pattern = f"%{q}%"
        snaps = self.ctx.db.scalars(
            select(PlayerSnapshot)
            .where(
                PlayerSnapshot.league_id == self.ctx.league_id,
                PlayerSnapshot.player_name.ilike(pattern),
            )
            .order_by(PlayerSnapshot.dynasty_rating.desc().nullslast())
            .limit(30)
        ).all()

        rostered: set[str] = set()
        for roster in self.ctx.db.scalars(
            select(Roster).where(Roster.league_id == self.ctx.league_id)
        ).all():
            rostered.update(self._roster_player_ids(roster.sleeper_roster_id))

        hits: list[dict[str, Any]] = []
        for snap in snaps:
            if position and snap.position != position.upper():
                continue
            hits.append(
                {
                    "player_id": snap.sleeper_player_id,
                    "name": snap.player_name,
                    "position": snap.position,
                    "ovr": snap.dynasty_rating,
                    "tv": snap.trade_value,
                    "rostered": snap.sleeper_player_id in rostered,
                }
            )
            if len(hits) >= 20:
                break
        return {"query": q, "position_filter": position, "hits": hits}

    def get_league_rankings(self) -> dict[str, Any]:
        rankings = get_league_rankings(self.ctx.db, self.ctx.league_id)
        if rankings is None:
            return {"error": "Rankings not available — sync the league first"}

        def _row(team: dict[str, Any]) -> dict[str, Any]:
            return {
                "team": team.get("team_name"),
                "roster_id": team.get("roster_id"),
                "is_me": team.get("is_me"),
                "avg_dynasty_rating": team.get("avg_dynasty_rating"),
                "starter_total_ppg": team.get("starter_total_ppg"),
                "total_trade_value": team.get("total_trade_value"),
                "draft_pick_value": team.get("draft_pick_value"),
                "dynasty_rank": team.get("dynasty_rank"),
                "starter_ppg_rank": team.get("starter_ppg_rank"),
                "tv_rank": team.get("tv_rank"),
                "win_rank": team.get("win_rank"),
                "contender_tier": team.get("contender_tier"),
            }

        return {
            "by_dynasty": [_row(t) for t in rankings.by_dynasty],
            "by_starter_ppg": [_row(t) for t in rankings.by_starter_ppg],
            "by_trade_value": [_row(t) for t in rankings.by_tv],
            "by_win_now": [_row(t) for t in rankings.by_win_now],
        }

    def get_free_agents(
        self,
        position: str | None = None,
        limit: int = TOP_FA_DEFAULT,
    ) -> dict[str, Any]:
        board = get_free_agents(self.ctx.db, self.ctx.league_id, position=position)
        if board is None:
            return {"players": []}
        cap = max(1, min(int(limit), 50))
        return {
            "position_filter": position,
            "total_available": board.total_available,
            "players": [
                {
                    "player_id": row.player_id,
                    "name": row.player_name,
                    "position": row.position,
                    "ovr": row.ovr,
                    "tv": row.trade_value,
                    "hppg": row.hppg,
                    "hppg_expected": row.hppg_expected,
                }
                for row in board.players[:cap]
            ],
        }

    def evaluate_trade(self, give: dict[str, Any], receive: dict[str, Any]) -> dict[str, Any]:
        return evaluate_trade_package(
            give,
            receive,
            resolve_player=self._resolve_player,
            resolve_pick=self._resolve_pick,
        )

    def validate_trade(
        self,
        counterparty_roster_id: str,
        give: dict[str, Any],
        receive: dict[str, Any],
    ) -> dict[str, Any]:
        """LLM validation from counterparty perspective (opt-in; requires Anthropic key)."""
        eval_result = evaluate_trade_package(
            give,
            receive,
            resolve_player=self._resolve_player,
            resolve_pick=self._resolve_pick,
        )
        if eval_result.get("missing_assets"):
            return {
                "error": "Could not resolve all trade assets",
                "missing_assets": eval_result["missing_assets"],
            }

        proposer_id = self.proposer_roster_id
        my_team = self.get_team(proposer_id)
        their_team = self.get_team(str(counterparty_roster_id))
        if their_team.get("error"):
            return their_team

        payload = build_validation_payload(
            proposer_roster_id=proposer_id,
            counterparty_roster_id=str(counterparty_roster_id),
            proposer_team=my_team,
            counterparty_team=their_team,
            give=eval_result["give"],
            receive=eval_result["receive"],
            tv_evaluation=eval_result,
        )
        settings = get_settings()
        validation = validate_trade_with_llm(
            payload,
            api_key=settings.anthropic_api_key,
        )
        tv_summary = {
            key: eval_result.get(key)
            for key in (
                "give_total_tv",
                "receive_total_tv",
                "net_delta_adjusted_pct",
                "fairness",
                "within_band",
                "consolidation_tax_tv",
                "positional_notes",
            )
        }
        return {
            "counterparty_roster_id": str(counterparty_roster_id),
            "counterparty_team_name": their_team.get("team_name"),
            "proposer_roster_id": proposer_id,
            "tv_evaluation": tv_summary,
            "resolved_trade": {
                "give": eval_result["give"],
                "receive": eval_result["receive"],
            },
            "validation": validation,
        }

    def suggest_trades(
        self,
        target_roster_id: str | None = None,
        target_player_id: str | None = None,
        target_position: str | None = None,
        need_position: str | None = None,
        swap_mode: bool = False,
        keep_current_first: bool = True,
        lubricant_mode: bool = True,
        rank_by_validation: bool = False,
    ) -> dict[str, Any]:
        proposer_id = self.proposer_roster_id
        trade_surplus = self._trade_surplus()
        snapshots = self._load_snapshots()

        roster_players: dict[str, list[dict[str, Any]]] = {}
        picks_by_roster: dict[str, list[dict[str, Any]]] = {}
        team_names: dict[str, str] = {}

        for roster in self.ctx.db.scalars(
            select(Roster).where(Roster.league_id == self.ctx.league_id)
        ).all():
            rid = roster.sleeper_roster_id
            team_names[rid] = roster.team_name or rid
            roster_players[rid] = _players_for_roster(
                snapshots, self._roster_player_ids(rid)
            )
            picks_by_roster[rid] = get_roster_draft_picks(
                self.ctx.db, self.ctx.league_id, rid
            )

        tiers = self._contender_tier_by_roster()
        if swap_mode:
            packages = generate_need_swap_packages(
                my_roster_id=proposer_id,
                roster_players=roster_players,
                picks_by_roster=picks_by_roster,
                trade_surplus=trade_surplus,
                contender_tier_by_roster=tiers,
                team_names=team_names,
                need_position=need_position or target_position,
                target_player_id=target_player_id,
                keep_current_first=keep_current_first,
                lubricant_mode=lubricant_mode,
            )
        elif target_position and not target_player_id and not target_roster_id:
            packages = generate_position_acquisition_packages(
                my_roster_id=proposer_id,
                target_position=target_position,
                roster_players=roster_players,
                picks_by_roster=picks_by_roster,
                trade_surplus=trade_surplus,
                contender_tier_by_roster=tiers,
                team_names=team_names,
                keep_current_first=keep_current_first,
                lubricant_mode=lubricant_mode,
            )
        else:
            packages = generate_trade_suggestions(
                my_roster_id=proposer_id,
                trade_surplus=trade_surplus,
                roster_players=roster_players,
                picks_by_roster=picks_by_roster,
                target_roster_id=target_roster_id,
                target_player_id=target_player_id,
                target_position=target_position,
                contender_tier_by_roster=tiers,
                keep_current_first=keep_current_first,
                lubricant_mode=lubricant_mode,
            )

        validation_ranked = False
        if rank_by_validation:
            settings = get_settings()
            ranked = rank_packages_by_counterparty_validation(
                packages,
                my_roster_id=proposer_id,
                resolve_player=self._resolve_player,
                resolve_pick=self._resolve_pick,
                load_team=self.get_team,
                trade_surplus=trade_surplus,
                api_key=settings.anthropic_api_key,
            )
            validation_ranked = any(
                p.get("counterparty_validation") for p in ranked
            )
            packages = ranked

        return {
            "proposer_roster_id": proposer_id,
            "my_roster_id": self.ctx.my_roster_id,
            "viewing_as_roster_id": proposer_id,
            "target_roster_id": target_roster_id,
            "target_player_id": target_player_id,
            "target_position": target_position,
            "need_position": need_position,
            "swap_mode": swap_mode,
            "validation_ranked": validation_ranked,
            "trade_surplus_summary": {
                "surplus": (trade_surplus or {}).get("surplus") or [],
                "needs": (trade_surplus or {}).get("needs") or [],
            },
            "packages": packages,
        }

    def calculate(self, expression: str) -> dict[str, Any]:
        try:
            value = safe_calculate(expression)
            return {"expression": expression, "result": value}
        except (ValueError, SyntaxError, ZeroDivisionError) as exc:
            return {"expression": expression, "error": str(exc)}

    def web_search(self, query: str) -> dict[str, Any]:
        settings = get_settings()
        return search_web(query, api_key=settings.brave_api_key)

    def dispatch(self, name: str, tool_input: dict[str, Any]) -> dict[str, Any]:
        if name == "get_team":
            return self.get_team(str(tool_input.get("roster_id", "")))
        if name == "get_player":
            return self.get_player(str(tool_input.get("player_id", "")))
        if name == "search_players":
            return self.search_players(
                str(tool_input.get("query", "")),
                tool_input.get("position"),
            )
        if name == "get_league_rankings":
            return self.get_league_rankings()
        if name == "get_free_agents":
            return self.get_free_agents(
                tool_input.get("position"),
                int(tool_input.get("limit") or TOP_FA_DEFAULT),
            )
        if name == "evaluate_trade":
            return self.evaluate_trade(
                tool_input.get("give") or {},
                tool_input.get("receive") or {},
            )
        if name == "validate_trade":
            return self.validate_trade(
                str(tool_input.get("counterparty_roster_id", "")),
                tool_input.get("give") or {},
                tool_input.get("receive") or {},
            )
        if name == "suggest_trades":
            tid = tool_input.get("target_roster_id")
            return self.suggest_trades(
                str(tid) if tid else None,
                str(tool_input["target_player_id"])
                if tool_input.get("target_player_id")
                else None,
                str(tool_input["target_position"]).upper()
                if tool_input.get("target_position")
                else None,
                str(tool_input["need_position"]).upper()
                if tool_input.get("need_position")
                else None,
                swap_mode=bool(tool_input.get("swap_mode", False)),
                keep_current_first=bool(tool_input.get("keep_current_first", True)),
                lubricant_mode=bool(tool_input.get("lubricant_mode", True)),
                rank_by_validation=bool(tool_input.get("rank_by_validation", False)),
            )
        if name == "calculate":
            return self.calculate(str(tool_input.get("expression", "")))
        if name == "web_search":
            return self.web_search(str(tool_input.get("query", "")))
        return {"error": f"Unknown tool: {name}"}


def _starter_needs_from_detail(detail: Any) -> dict[str, int]:
    from collections import defaultdict

    counts: dict[str, int] = defaultdict(int)
    for group in detail.depth_chart:
        counts[group.position] = len(group.players)
    needs: dict[str, int] = {}
    targets = {"QB": 2, "RB": 4, "WR": 5, "TE": 2}
    for pos, target in targets.items():
        gap = max(0, target - counts.get(pos, 0))
        if gap:
            needs[pos] = gap
    flex_depth = counts.get("RB", 0) + counts.get("WR", 0) + counts.get("TE", 0)
    needs["FLEX"] = max(0, 3 - flex_depth)
    return needs


ADVISOR_TOOL_SPECS: list[dict[str, Any]] = [
    {
        "name": "get_team",
        "description": "Roster summary: players, positional needs/surplus, valued draft picks, injuries.",
        "input_schema": {
            "type": "object",
            "properties": {
                "roster_id": {"type": "string", "description": "Sleeper roster id"},
            },
            "required": ["roster_id"],
        },
    },
    {
        "name": "get_player",
        "description": "Player card: OVR, TV, HPPG, trade_tag, injury, outlook, win-now lens.",
        "input_schema": {
            "type": "object",
            "properties": {
                "player_id": {"type": "string", "description": "Sleeper player id"},
            },
            "required": ["player_id"],
        },
    },
    {
        "name": "search_players",
        "description": "Search league player pool by name (optional position filter).",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "position": {"type": "string", "description": "QB, RB, WR, or TE"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_league_rankings",
        "description": "Dynasty, starter PPG, trade value, and win-now standings.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_free_agents",
        "description": "Top available free agents by OVR/TV.",
        "input_schema": {
            "type": "object",
            "properties": {
                "position": {"type": "string"},
                "limit": {"type": "integer", "description": "Max rows (default 24)"},
            },
        },
    },
    {
        "name": "evaluate_trade",
        "description": (
            "Evaluate a trade package. Players by sleeper_player_id; picks by "
            "{season, round, original_roster_id}. Returns raw + effective TV, "
            "consolidation-adjusted fairness (±5%), positional notes."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "give": {
                    "type": "object",
                    "properties": {
                        "players": {"type": "array", "items": {"type": "string"}},
                        "picks": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "season": {"type": "string"},
                                    "round": {"type": "integer"},
                                    "original_roster_id": {"type": "string"},
                                },
                                "required": ["season", "round", "original_roster_id"],
                            },
                        },
                    },
                },
                "receive": {
                    "type": "object",
                    "properties": {
                        "players": {"type": "array", "items": {"type": "string"}},
                        "picks": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "season": {"type": "string"},
                                    "round": {"type": "integer"},
                                    "original_roster_id": {"type": "string"},
                                },
                                "required": ["season", "round", "original_roster_id"],
                            },
                        },
                    },
                },
            },
            "required": ["give", "receive"],
        },
    },
    {
        "name": "validate_trade",
        "description": (
            "Counterparty-perspective validation for a specific trade package. "
            "Call after suggest_trades or evaluate_trade when you need to judge whether "
            "the other manager would accept. Requires counterparty roster_id plus the "
            "same give/receive shape as evaluate_trade. Returns accept_likelihood, "
            "blockers, and suggested_tweak from their roster context."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "counterparty_roster_id": {
                    "type": "string",
                    "description": "Sleeper roster id of the other manager",
                },
                "give": {
                    "type": "object",
                    "properties": {
                        "players": {"type": "array", "items": {"type": "string"}},
                        "picks": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "season": {"type": "string"},
                                    "round": {"type": "integer"},
                                    "original_roster_id": {"type": "string"},
                                },
                                "required": ["season", "round", "original_roster_id"],
                            },
                        },
                    },
                },
                "receive": {
                    "type": "object",
                    "properties": {
                        "players": {"type": "array", "items": {"type": "string"}},
                        "picks": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "season": {"type": "string"},
                                    "round": {"type": "integer"},
                                    "original_roster_id": {"type": "string"},
                                },
                                "required": ["season", "round", "original_roster_id"],
                            },
                        },
                    },
                },
            },
            "required": ["counterparty_roster_id", "give", "receive"],
        },
    },
    {
        "name": "suggest_trades",
        "description": (
            "Trade ideas: surplus-based hooks or targeted stud acquisition when "
            "target_player_id / target_position is set. Uses KTC-adjusted fairness "
            "with acquisition overpay band. Set rank_by_validation=true to re-rank by "
            "counterparty accept_likelihood (extra LLM calls; default off)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "target_roster_id": {
                    "type": "string",
                    "description": "Optional counterparty roster id",
                },
                "target_player_id": {
                    "type": "string",
                    "description": "Acquire this player (builds pick-heavy packages)",
                },
                "target_position": {
                    "type": "string",
                    "description": "Acquire key players at position (RB, WR). Scans league if no roster set.",
                },
                "need_position": {
                    "type": "string",
                    "description": "With swap_mode: position you need filled (RB, WR, TE).",
                },
                "swap_mode": {
                    "type": "boolean",
                    "description": "Need-swap: trade surplus + depth for stud + depth back.",
                },
                "keep_current_first": {
                    "type": "boolean",
                    "description": "Reserve own current-year 1st (default true — keep 1.01 for rookie draft).",
                },
                "lubricant_mode": {
                    "type": "boolean",
                    "description": "Favor cross-year picks + depth over 1.01 overload (default true).",
                },
                "rank_by_validation": {
                    "type": "boolean",
                    "description": "Re-rank packages by counterparty accept_likelihood via LLM (default false; costs extra).",
                },
            },
        },
    },
    {
        "name": "calculate",
        "description": "Safe arithmetic for TV sums (numbers, + - * / **, parentheses).",
        "input_schema": {
            "type": "object",
            "properties": {
                "expression": {"type": "string"},
            },
            "required": ["expression"],
        },
    },
    {
        "name": "web_search",
        "description": (
            "Search the web for recent NFL injury updates, roster news, and beat reports. "
            "Use for time-sensitive context not in league snapshots (not for player TV/OVR)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
            },
            "required": ["query"],
        },
    },
]


def tool_result_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, default=str)
