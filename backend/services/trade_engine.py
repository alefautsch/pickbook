"""Trade expendability, fit scoring, and consolidation-aware package valuation."""

from __future__ import annotations

from typing import Any

from backend.services.analysis_service import TRADE_SURPLUS_BOTTOM_N, TRADE_SURPLUS_TOP_N

DEPTH_TV_DISCOUNT = 0.70
PIECE_COUNT_PENALTY = 0.95
CONSOLIDATION_PREMIUM = 0.12
FAIRNESS_BAND = 0.05
MIN_EXPENDABILITY_TO_SELL = 0.30

_DEPTH_RANK_SCORES = (0.05, 0.35, 0.65, 1.0)


def surplus_positions_for_roster(
    position_strength: dict[str, Any] | None,
    roster_id: str,
    *,
    top_n: int = TRADE_SURPLUS_TOP_N,
    bottom_n: int = TRADE_SURPLUS_BOTTOM_N,
) -> tuple[set[str], set[str]]:
    """Position groups where roster ranks top-N (surplus) or bottom-N (need)."""
    if not position_strength:
        return set(), set()
    teams = position_strength.get("teams") or []
    positions = position_strength.get("positions") or []
    surplus: set[str] = set()
    needs: set[str] = set()

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
        if my_rank is None:
            continue
        if my_rank <= top_n:
            surplus.add(pos)
        if my_rank > len(ranked) - bottom_n:
            needs.add(pos)
    return surplus, needs


def asset_tv(asset: dict[str, Any]) -> float:
    return float(asset.get("tv") or asset.get("trade_value") or 0)


def effective_package_tv(assets: list[dict[str, Any]]) -> float:
    """Discount depth pieces; penalize multi-asset packages vs a single stud."""
    if not assets:
        return 0.0
    tvs = sorted((asset_tv(a) for a in assets), reverse=True)
    if len(tvs) == 1:
        return tvs[0]
    top = tvs[0]
    rest = sum(tv * DEPTH_TV_DISCOUNT for tv in tvs[1:])
    penalty = PIECE_COUNT_PENALTY ** (len(tvs) - 1)
    return (top + rest) * penalty


def _player_assets(assets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [a for a in assets if a.get("player_id")]


def _side_consolidating(assets: list[dict[str, Any]], other: list[dict[str, Any]]) -> bool:
    mine = _player_assets(assets)
    theirs = _player_assets(other)
    if len(mine) < len(theirs):
        return True
    if len(mine) > len(theirs):
        return False
    my_max = max((asset_tv(a) for a in mine), default=0)
    their_max = max((asset_tv(a) for a in theirs), default=0)
    return my_max > their_max


def evaluate_package_fairness(
    give_assets: list[dict[str, Any]],
    recv_assets: list[dict[str, Any]],
    *,
    fairness_band: float = FAIRNESS_BAND,
) -> dict[str, Any]:
    """Fairness: raw TV + consolidation tax; effective TV reported for depth context."""
    give_raw = sum(asset_tv(a) for a in give_assets)
    recv_raw = sum(asset_tv(a) for a in recv_assets)
    give_eff = effective_package_tv(give_assets)
    recv_eff = effective_package_tv(recv_assets)

    give_consolidating = _side_consolidating(give_assets, recv_assets)
    recv_consolidating = _side_consolidating(recv_assets, give_assets)

    # Tax acquiring a stud (fewer/higher assets): must overpay in raw TV.
    consolidation_tax = 0.0
    if recv_consolidating:
        consolidation_tax = recv_raw * CONSOLIDATION_PREMIUM
    elif give_consolidating:
        consolidation_tax = -give_raw * CONSOLIDATION_PREMIUM

    raw_baseline = max(give_raw, recv_raw, 1.0)
    net_raw = recv_raw - give_raw
    net_adj = net_raw - consolidation_tax
    pct_adj = net_adj / raw_baseline
    within = abs(pct_adj) <= fairness_band

    if within:
        label = "fair"
    elif net_adj > 0:
        label = "favors_you"
    else:
        label = "favors_counterparty"

    return {
        "give_total_tv": round(give_raw, 2),
        "receive_total_tv": round(recv_raw, 2),
        "give_effective_tv": round(give_eff, 2),
        "receive_effective_tv": round(recv_eff, 2),
        "consolidation_tax_tv": round(consolidation_tax, 2),
        "consolidation_premium_pct": int(CONSOLIDATION_PREMIUM * 100),
        "give_consolidating": give_consolidating,
        "receive_consolidating": recv_consolidating,
        "net_delta_tv": round(net_raw, 2),
        "net_delta_effective_tv": round(recv_eff - give_eff, 2),
        "net_delta_adjusted_tv": round(net_adj, 2),
        "net_delta_pct": round(net_raw / raw_baseline * 100, 2),
        "net_delta_adjusted_pct": round(pct_adj * 100, 2),
        "fairness_band": f"±{int(fairness_band * 100)}%",
        "within_band": within,
        "fairness": label,
    }


def _depth_rank_score(rank: int) -> float:
    idx = min(rank - 1, len(_DEPTH_RANK_SCORES) - 1)
    return _DEPTH_RANK_SCORES[max(0, idx)]


def _replaceability_score(tv: float, next_tv: float | None) -> float:
    if tv <= 0:
        return 0.0
    if next_tv is None:
        return 1.0
    gap = (tv - next_tv) / tv
    return max(0.0, min(1.0, 1.0 - gap))


def _strategy_sell_multiplier(
    *,
    contender_tier: str | None,
    age: int | None,
    ovr: int | None,
    hppg: float | None,
) -> float:
    tier = contender_tier or "competitive"
    if age is None:
        return 1.0
    if tier == "contender":
        if age >= 28 and (hppg or 0) >= 10:
            return 1.25
        if age <= 24 and (ovr or 0) >= 82:
            return 0.45
    elif tier == "rebuild":
        if age >= 28:
            return 1.3
        if age <= 23 and (ovr or 0) >= 78:
            return 0.4
    return 1.0


def expendability_fraction(
    player: dict[str, Any],
    *,
    depth_rank: int,
    position_is_surplus: bool,
    next_tv_at_position: float | None,
    contender_tier: str | None = None,
) -> float:
    depth = _depth_rank_score(depth_rank)
    surplus = 1.0 if position_is_surplus else 0.35
    replaceability = _replaceability_score(
        asset_tv(player),
        next_tv_at_position,
    )
    base = 0.45 * depth + 0.35 * surplus + 0.20 * replaceability
    mult = _strategy_sell_multiplier(
        contender_tier=contender_tier,
        age=player.get("age"),
        ovr=player.get("ovr") or player.get("dynasty_rating"),
        hppg=player.get("hppg"),
    )
    return max(0.0, min(1.0, base * mult))


def trade_fit_score(
    player: dict[str, Any],
    *,
    acquirer_need_positions: set[str],
    acquirer_surplus_positions: set[str],
    acquirer_tier: str | None = None,
    seller_tier: str | None = None,
) -> float:
    pos = player.get("position") or player.get("pos") or ""
    score = 0.5
    if pos in acquirer_need_positions:
        score += 0.35
    if pos in acquirer_surplus_positions:
        score -= 0.25

    age = player.get("age")
    hppg = player.get("hppg") or 0
    if acquirer_tier == "contender" and age is not None and age >= 25 and hppg >= 10:
        score += 0.15
    if acquirer_tier == "rebuild" and age is not None and age <= 24:
        score += 0.15
    if seller_tier == "rebuild" and acquirer_tier == "contender" and age is not None and age >= 27:
        score += 0.10
    if seller_tier == "contender" and acquirer_tier == "rebuild" and age is not None and age <= 25:
        score += 0.10
    return max(0.1, min(1.0, score))


def _position_groups(players: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for player in players:
        pos = player.get("position") or player.get("pos") or "?"
        groups.setdefault(pos, []).append(player)
    for pos in groups:
        groups[pos].sort(key=lambda p: asset_tv(p), reverse=True)
    return groups


def annotate_players_with_expendability(
    players: list[dict[str, Any]],
    *,
    surplus_positions: set[str] | None = None,
    contender_tier: str | None = None,
) -> list[dict[str, Any]]:
    surplus_positions = surplus_positions or set()
    groups = _position_groups(players)
    depth_rank: dict[str, int] = {}
    next_tv: dict[str, float | None] = {}
    for pos_players in groups.values():
        for idx, player in enumerate(pos_players):
            pid = str(player.get("player_id") or "")
            depth_rank[pid] = idx + 1
            next_tv[pid] = asset_tv(pos_players[idx + 1]) if idx + 1 < len(pos_players) else None

    annotated: list[dict[str, Any]] = []
    for player in players:
        pid = str(player.get("player_id") or "")
        pos = player.get("position") or player.get("pos") or ""
        frac = expendability_fraction(
            player,
            depth_rank=depth_rank.get(pid, 99),
            position_is_surplus=pos in surplus_positions,
            next_tv_at_position=next_tv.get(pid),
            contender_tier=contender_tier,
        )
        row = dict(player)
        row["expendability_score"] = round(frac * 100, 1)
        row["depth_rank"] = depth_rank.get(pid)
        annotated.append(row)
    return annotated


def top_trade_candidates(
    players: list[dict[str, Any]],
    *,
    surplus_positions: set[str] | None = None,
    contender_tier: str | None = None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    annotated = annotate_players_with_expendability(
        players,
        surplus_positions=surplus_positions,
        contender_tier=contender_tier,
    )
    candidates = [
        p
        for p in annotated
        if (p.get("expendability_score") or 0) >= MIN_EXPENDABILITY_TO_SELL * 100
    ]
    candidates.sort(key=lambda p: p.get("expendability_score") or 0, reverse=True)
    return [
        {
            "player_id": p.get("player_id"),
            "name": p.get("name"),
            "position": p.get("position") or p.get("pos"),
            "tv": p.get("tv"),
            "expendability_score": p.get("expendability_score"),
            "depth_rank": p.get("depth_rank"),
        }
        for p in candidates[:limit]
    ]


def package_quality_score(
    *,
    give_players: list[dict[str, Any]],
    recv_players: list[dict[str, Any]],
    expendability_by_id: dict[str, float],
    acquirer_need_positions: set[str],
    acquirer_surplus_positions: set[str],
    acquirer_tier: str | None,
    seller_tier: str | None,
    fairness: dict[str, Any],
) -> float:
    exp_vals = [
        expendability_by_id.get(str(p.get("player_id")), 0) / 100.0
        for p in give_players
    ]
    fit_vals = [
        trade_fit_score(
            p,
            acquirer_need_positions=acquirer_need_positions,
            acquirer_surplus_positions=acquirer_surplus_positions,
            acquirer_tier=acquirer_tier,
            seller_tier=seller_tier,
        )
        for p in recv_players
    ]
    avg_exp = sum(exp_vals) / len(exp_vals) if exp_vals else 0.0
    avg_fit = sum(fit_vals) / len(fit_vals) if fit_vals else 0.0
    delta_penalty = 1.0 + abs(fairness.get("net_delta_adjusted_pct") or 0) / 10.0
    return round(avg_exp * avg_fit / delta_penalty, 4)
