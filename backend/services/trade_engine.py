"""Trade tagging, fit scoring, and consolidation-aware package valuation."""

from __future__ import annotations

from typing import Any, Literal

from backend.services.analysis_service import (
    TRADE_SURPLUS_BOTTOM_N,
    TRADE_SURPLUS_TOP_N,
)

DEPTH_TV_DISCOUNT = 0.70
PIECE_COUNT_PENALTY = 0.95
CONSOLIDATION_PREMIUM = 0.15
# Catalog pick TV overstates trade certainty for mid/late rounds.
PICK_TRADE_TV_MULTIPLIER: dict[int, float] = {
    1: 1.0,
    2: 0.50,
    3: 0.32,
    4: 0.22,
}
PICK_TRADE_TV_DEFAULT = 0.15
FAIRNESS_BAND = 0.05

# KTC-style stud premium (% of single-player TV) — consolidation is worth paying up for.
STUD_PREMIUM_ELITE = 0.40  # TV >= 7500
STUD_PREMIUM_HIGH = 0.30  # TV >= 6000
STUD_PREMIUM_MID = 0.20  # TV >= 5000
STUD_PREMIUM_SOLID = 0.12  # TV >= 4500
DEPTH_VOLUME_PENALTY = 0.12  # 3+ asset packages
TWIN_DEPTH_BONUS = 0.08  # two similar-value players

TradeTag = Literal["core", "trade"]

_DEPTH_RANK_SCORES = (0.05, 0.35, 0.65, 1.0)

# Marginal PPG above next realistic backup → core piece.
_CORE_DELTA_BY_TIER: dict[str, float] = {
    "contender": 6.0,
    "competitive": 5.0,
    "rebuild": 4.0,
}

# Below this marginal PPG, depth is a trade chip (if not already core).
_TRADE_DELTA_BY_TIER: dict[str, float] = {
    "contender": 2.5,
    "competitive": 2.0,
    "rebuild": 1.5,
}

# TV percentile minus production percentile — sell-high signal.
_SELL_HIGH_GAP = 22.0


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


def is_pick_asset(asset: dict[str, Any]) -> bool:
    if asset.get("player_id"):
        return False
    return asset.get("round") is not None or bool(asset.get("label"))


def pick_trade_tv_multiplier(round_no: int) -> float:
    if round_no <= 1:
        return 1.0
    return PICK_TRADE_TV_MULTIPLIER.get(round_no, PICK_TRADE_TV_DEFAULT)


def pick_trade_profile(round_no: int) -> str:
    if round_no <= 1:
        return "first_round_capital"
    if round_no == 2:
        return "dart_throw"
    return "long_shot"


def asset_tv_for_trade(asset: dict[str, Any]) -> float:
    raw = asset_tv(asset)
    if not is_pick_asset(asset):
        return raw
    round_no = int(asset.get("round") or 0)
    return round(raw * pick_trade_tv_multiplier(round_no), 2)


def production_ppg(player: dict[str, Any]) -> float:
    """Recent actuals weighted more than projection."""
    hppg = player.get("hppg")
    projected = player.get("projected_ppg")
    if hppg is not None and projected is not None:
        return round(0.65 * float(hppg) + 0.35 * float(projected), 2)
    if hppg is not None:
        return float(hppg)
    if projected is not None:
        return float(projected)
    return 0.0


def effective_package_tv(assets: list[dict[str, Any]]) -> float:
    """Discount depth pieces; penalize multi-asset packages vs a single stud."""
    if not assets:
        return 0.0
    tvs = sorted((asset_tv_for_trade(a) for a in assets), reverse=True)
    if len(tvs) == 1:
        return tvs[0]
    top = tvs[0]
    rest = sum(tv * DEPTH_TV_DISCOUNT for tv in tvs[1:])
    penalty = PIECE_COUNT_PENALTY ** (len(tvs) - 1)
    return (top + rest) * penalty


def _player_assets(assets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [a for a in assets if a.get("player_id")]


def stud_value_adjustment(assets: list[dict[str, Any]]) -> float:
    """KTC-style value bump for stud consolidation; penalty for depth volume."""
    players = _player_assets(assets)
    if not players:
        return 0.0
    raw = sum(asset_tv(a) for a in assets)
    if len(players) == 1:
        tv = asset_tv(players[0])
        if tv >= 7500:
            return round(tv * STUD_PREMIUM_ELITE, 1)
        if tv >= 6000:
            return round(tv * STUD_PREMIUM_HIGH, 1)
        if tv >= 5000:
            return round(tv * STUD_PREMIUM_MID, 1)
        if tv >= 4500:
            return round(tv * STUD_PREMIUM_SOLID, 1)
    if len(assets) >= 3:
        return round(-raw * DEPTH_VOLUME_PENALTY, 1)
    if len(players) == 2:
        tvs = sorted((asset_tv(p) for p in players), reverse=True)
        if tvs[0] > 0 and (tvs[0] - tvs[1]) / tvs[0] < 0.35:
            return round(raw * TWIN_DEPTH_BONUS, 1)
    return 0.0


def package_adjusted_tv(assets: list[dict[str, Any]]) -> tuple[float, float]:
    """Return (raw_total, raw_total + stud adjustment)."""
    raw = sum(asset_tv_for_trade(a) for a in assets)
    return raw, raw + stud_value_adjustment(assets)


def _side_consolidating(
    assets: list[dict[str, Any]], other: list[dict[str, Any]]
) -> bool:
    mine = _player_assets(assets)
    theirs = _player_assets(other)
    if len(mine) < len(theirs):
        return True
    if len(mine) > len(theirs):
        return False
    my_max = max((asset_tv(a) for a in mine), default=0)
    their_max = max((asset_tv(a) for a in theirs), default=0)
    return my_max > their_max


def _assign_package_stud_adjustments(
    give_assets: list[dict[str, Any]],
    recv_assets: list[dict[str, Any]],
) -> tuple[float, float, bool, bool]:
    """Apply at most one non-zero stud/value adjustment per trade (KTC-style)."""
    give_raw = stud_value_adjustment(give_assets)
    recv_raw = stud_value_adjustment(recv_assets)
    give_consolidating = _side_consolidating(give_assets, recv_assets)
    recv_consolidating = _side_consolidating(recv_assets, give_assets)

    if give_consolidating and recv_consolidating:
        give_consolidating = False
        recv_consolidating = False

    give_adj = 0.0
    recv_adj = 0.0

    if recv_consolidating and recv_raw != 0:
        recv_adj = recv_raw
    elif give_consolidating and give_raw != 0:
        give_adj = give_raw
    elif recv_raw < 0:
        recv_adj = recv_raw
    elif give_raw < 0:
        give_adj = give_raw

    return give_adj, recv_adj, give_consolidating, recv_consolidating


def evaluate_package_fairness(
    give_assets: list[dict[str, Any]],
    recv_assets: list[dict[str, Any]],
    *,
    fairness_band: float = FAIRNESS_BAND,
) -> dict[str, Any]:
    """Fairness: raw TV + one-sided stud adjustment + consolidation tax."""
    give_raw = sum(asset_tv_for_trade(a) for a in give_assets)
    recv_raw = sum(asset_tv_for_trade(a) for a in recv_assets)
    give_adj, recv_adj, give_consolidating, recv_consolidating = _assign_package_stud_adjustments(
        give_assets, recv_assets
    )
    give_total_adj = give_raw + give_adj
    recv_total_adj = recv_raw + recv_adj
    give_eff = effective_package_tv(give_assets)
    recv_eff = effective_package_tv(recv_assets)

    consolidation_tax = 0.0
    if recv_consolidating and recv_adj > 0:
        consolidation_tax = recv_total_adj * CONSOLIDATION_PREMIUM
    elif give_consolidating and give_adj > 0:
        consolidation_tax = -give_total_adj * CONSOLIDATION_PREMIUM

    raw_baseline = max(give_total_adj, recv_total_adj, 1.0)
    net_raw = recv_raw - give_raw
    net_adj_total = recv_total_adj - give_total_adj - consolidation_tax
    pct_adj = net_adj_total / raw_baseline
    within = abs(pct_adj) <= fairness_band

    if within:
        label = "fair"
    elif net_adj_total > 0:
        label = "favors_you"
    else:
        label = "favors_counterparty"

    return {
        "give_total_tv": round(give_raw, 2),
        "receive_total_tv": round(recv_raw, 2),
        "give_value_adjustment": round(give_adj, 2),
        "receive_value_adjustment": round(recv_adj, 2),
        "give_adjusted_tv": round(give_total_adj, 2),
        "receive_adjusted_tv": round(recv_total_adj, 2),
        "give_effective_tv": round(give_eff, 2),
        "receive_effective_tv": round(recv_eff, 2),
        "consolidation_tax_tv": round(consolidation_tax, 2),
        "consolidation_premium_pct": int(CONSOLIDATION_PREMIUM * 100),
        "give_consolidating": give_consolidating,
        "receive_consolidating": recv_consolidating,
        "net_delta_tv": round(net_raw, 2),
        "net_delta_adjusted_tv": round(recv_total_adj - give_total_adj, 2),
        "net_delta_effective_tv": round(recv_eff - give_eff, 2),
        "net_delta_adjusted_total_tv": round(net_adj_total, 2),
        "net_delta_pct": round(net_raw / max(give_raw, recv_raw, 1.0) * 100, 2),
        "net_delta_adjusted_pct": round(pct_adj * 100, 2),
        "fairness_band": f"±{int(fairness_band * 100)}%",
        "within_band": within,
        "fairness": label,
        "pick_trade_tv_note": (
            "Round 2+ pick catalog TV discounted in totals (dart throws / long shots)."
        ),
    }


def _position_groups_by_production(
    players: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for player in players:
        pos = player.get("position") or player.get("pos") or "?"
        groups.setdefault(pos, []).append(player)
    for pos in groups:
        groups[pos].sort(key=production_ppg, reverse=True)
    return groups


def lineup_delta_ppg(
    player: dict[str, Any], pos_players: list[dict[str, Any]]
) -> float:
    """Marginal PPG vs the next realistic backup at the same position."""
    sorted_players = sorted(pos_players, key=production_ppg, reverse=True)
    pid = str(player.get("player_id") or "")
    my_ppg = production_ppg(player)
    for idx, row in enumerate(sorted_players):
        if str(row.get("player_id") or "") != pid:
            continue
        if idx + 1 >= len(sorted_players):
            # Last on the depth chart: no backup below — not a lineup cliff.
            # Sole player at the position is still irreplaceable.
            if len(sorted_players) == 1:
                return round(my_ppg, 2)
            return 0.0
        backup_ppg = production_ppg(sorted_players[idx + 1])
        return round(my_ppg - backup_ppg, 2)
    return my_ppg


def _percentile_gap(
    player: dict[str, Any],
    pos_players: list[dict[str, Any]],
) -> float:
    """TV rank percentile minus production rank percentile within position (positive = sell-high)."""
    if len(pos_players) < 2:
        return 0.0
    pid = str(player.get("player_id") or "")
    by_tv = sorted(pos_players, key=asset_tv, reverse=True)
    by_prod = sorted(pos_players, key=production_ppg, reverse=True)
    n = len(pos_players)

    def _pct_rank(ordered: list[dict[str, Any]]) -> float:
        for idx, row in enumerate(ordered):
            if str(row.get("player_id") or "") == pid:
                return (n - idx) / n * 100.0
        return 50.0

    return round(_pct_rank(by_tv) - _pct_rank(by_prod), 1)


def assign_player_trade_tag(
    player: dict[str, Any],
    *,
    depth_rank: int,
    lineup_delta: float,
    tv_vs_production: float,
    position_is_surplus: bool,
    contender_tier: str | None = None,
) -> TradeTag | None:
    tier = contender_tier or "competitive"
    core_delta = _CORE_DELTA_BY_TIER.get(tier, 5.0)
    trade_delta = _TRADE_DELTA_BY_TIER.get(tier, 2.0)
    age = player.get("age")

    if lineup_delta >= core_delta:
        return "core"
    if depth_rank == 1 and lineup_delta >= core_delta * 0.55:
        return "core"

    if tier == "contender":
        if position_is_surplus and depth_rank >= 3 and lineup_delta < trade_delta:
            return "trade"
        if tv_vs_production >= _SELL_HIGH_GAP and age is not None and age >= 26:
            return "trade"
        if depth_rank >= 4 and lineup_delta < 3.5:
            return "trade"
        if depth_rank >= 6 and lineup_delta < 4.0:
            return "trade"

    elif tier == "rebuild":
        if age is not None and age >= 28 and lineup_delta < 4.0:
            return "trade"
        if tv_vs_production >= _SELL_HIGH_GAP and age is not None and age >= 27:
            return "trade"
        if position_is_surplus and depth_rank >= 4 and lineup_delta < trade_delta:
            return "trade"
        if depth_rank >= 5:
            return "trade"

    else:
        if position_is_surplus and depth_rank >= 4 and lineup_delta < trade_delta:
            return "trade"
        if depth_rank >= 5 and lineup_delta < 3.0:
            return "trade"

    return None


def assign_pick_trade_tag(
    pick: dict[str, Any],
    *,
    contender_tier: str | None = None,
) -> TradeTag | None:
    """Strategy-aware pick tradability — picks are stable currency."""
    tier = contender_tier or "competitive"
    round_no = int(pick.get("round") or 0)
    slot_tier = pick.get("slot_tier") or "mid"
    is_own = bool(pick.get("is_own_slot"))

    if tier == "rebuild":
        if round_no == 1 and slot_tier in ("early", "mid"):
            return "core"
        if round_no == 2 and slot_tier == "early":
            return "core"
        if slot_tier == "late" or round_no >= 3:
            return "trade"
        return None

    if tier == "contender":
        if is_own and round_no <= 2:
            return "trade"
        if is_own and round_no == 3:
            return "trade"
        if not is_own and slot_tier == "late":
            return "trade"
        return None

    # competitive
    if is_own and round_no >= 2 and slot_tier != "early":
        return "trade"
    if tier == "competitive" and not is_own and slot_tier == "early" and round_no == 1:
        return "core"
    return None


def annotate_players_with_trade_tags(
    players: list[dict[str, Any]],
    *,
    surplus_positions: set[str] | None = None,
    contender_tier: str | None = None,
) -> list[dict[str, Any]]:
    surplus_positions = surplus_positions or set()
    groups = _position_groups_by_production(players)
    depth_rank: dict[str, int] = {}
    for pos_players in groups.values():
        for idx, player in enumerate(pos_players):
            depth_rank[str(player.get("player_id") or "")] = idx + 1

    annotated: list[dict[str, Any]] = []
    for player in players:
        pid = str(player.get("player_id") or "")
        pos = player.get("position") or player.get("pos") or ""
        pos_players = groups.get(pos, [player])
        delta = lineup_delta_ppg(player, pos_players)
        tv_gap = _percentile_gap(player, pos_players)
        rank = depth_rank.get(pid, 99)
        tag = assign_player_trade_tag(
            player,
            depth_rank=rank,
            lineup_delta=delta,
            tv_vs_production=tv_gap,
            position_is_surplus=pos in surplus_positions,
            contender_tier=contender_tier,
        )
        row = dict(player)
        row["trade_tag"] = tag
        row["lineup_delta_ppg"] = delta
        row["production_ppg"] = production_ppg(player)
        row["tv_vs_production_gap"] = tv_gap
        row["depth_rank"] = rank
        annotated.append(row)
    return annotated


def annotate_picks_with_trade_tags(
    picks: list[dict[str, Any]],
    *,
    contender_tier: str | None = None,
) -> list[dict[str, Any]]:
    annotated: list[dict[str, Any]] = []
    for pick in picks:
        row = dict(pick)
        row["tv"] = asset_tv(pick)
        row["trade_tag"] = assign_pick_trade_tag(pick, contender_tier=contender_tier)
        annotated.append(row)
    return annotated


def top_trade_candidates(
    players: list[dict[str, Any]],
    *,
    picks: list[dict[str, Any]] | None = None,
    surplus_positions: set[str] | None = None,
    contender_tier: str | None = None,
    limit: int = 8,
) -> list[dict[str, Any]]:
    annotated = annotate_players_with_trade_tags(
        players,
        surplus_positions=surplus_positions,
        contender_tier=contender_tier,
    )
    pick_rows = annotate_picks_with_trade_tags(
        picks or [],
        contender_tier=contender_tier,
    )

    candidates: list[dict[str, Any]] = []
    for player in annotated:
        if player.get("trade_tag") != "trade":
            continue
        candidates.append(
            {
                "asset_type": "player",
                "player_id": player.get("player_id"),
                "name": player.get("name"),
                "position": player.get("position") or player.get("pos"),
                "tv": player.get("tv"),
                "trade_tag": "trade",
                "lineup_delta_ppg": player.get("lineup_delta_ppg"),
                "depth_rank": player.get("depth_rank"),
            }
        )

    for pick in pick_rows:
        if pick.get("trade_tag") != "trade":
            continue
        candidates.append(
            {
                "asset_type": "pick",
                "season": pick.get("season"),
                "round": pick.get("round"),
                "original_roster_id": pick.get("original_roster_id"),
                "name": pick.get("label"),
                "tv": pick.get("trade_value") or pick.get("tv"),
                "trade_tag": "trade",
                "slot_tier": pick.get("slot_tier"),
                "is_own_slot": pick.get("is_own_slot"),
            }
        )

    candidates.sort(
        key=lambda row: (
            row.get("tv") or 0,
            -(row.get("lineup_delta_ppg") or 99),
        ),
        reverse=True,
    )
    return candidates[:limit]


# --- Legacy expendability (deprecated; kept for gradual migration) ---

MIN_EXPENDABILITY_TO_SELL = 0.30


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
    tag = assign_player_trade_tag(
        player,
        depth_rank=depth_rank,
        lineup_delta=player.get("lineup_delta_ppg") or 0.0,
        tv_vs_production=player.get("tv_vs_production_gap") or 0.0,
        position_is_surplus=position_is_surplus,
        contender_tier=contender_tier,
    )
    if tag == "trade":
        return 0.75
    if tag == "core":
        return 0.05
    return 0.35


def annotate_players_with_expendability(
    players: list[dict[str, Any]],
    *,
    surplus_positions: set[str] | None = None,
    contender_tier: str | None = None,
) -> list[dict[str, Any]]:
    """Deprecated alias — returns trade-tag fields plus legacy expendability_score."""
    tagged = annotate_players_with_trade_tags(
        players,
        surplus_positions=surplus_positions,
        contender_tier=contender_tier,
    )
    for row in tagged:
        frac = expendability_fraction(
            row,
            depth_rank=row.get("depth_rank") or 99,
            position_is_surplus=(row.get("position") or row.get("pos") or "")
            in (surplus_positions or set()),
            next_tv_at_position=None,
            contender_tier=contender_tier,
        )
        row["expendability_score"] = round(frac * 100, 1)
    return tagged


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
    ppg = production_ppg(player)
    if acquirer_tier == "contender" and age is not None and age >= 25 and ppg >= 10:
        score += 0.15
    if acquirer_tier == "rebuild" and age is not None and age <= 24:
        score += 0.15
    if (
        seller_tier == "rebuild"
        and acquirer_tier == "contender"
        and age is not None
        and age >= 27
    ):
        score += 0.10
    if (
        seller_tier == "contender"
        and acquirer_tier == "rebuild"
        and age is not None
        and age <= 25
    ):
        score += 0.10
    return max(0.1, min(1.0, score))


def _tradability_weight(
    asset: dict[str, Any], tradability_by_id: dict[str, float]
) -> float:
    if asset.get("player_id"):
        return tradability_by_id.get(str(asset.get("player_id")), 0.35)
    if asset.get("season") and asset.get("trade_tag") == "trade":
        return 0.85
    if asset.get("season"):
        return 0.15
    return 0.35


def package_quality_score(
    *,
    give_players: list[dict[str, Any]],
    recv_players: list[dict[str, Any]],
    give_assets: list[dict[str, Any]] | None = None,
    expendability_by_id: dict[str, float] | None = None,
    tradability_by_id: dict[str, float] | None = None,
    acquirer_need_positions: set[str],
    acquirer_surplus_positions: set[str],
    acquirer_tier: str | None,
    seller_tier: str | None,
    fairness: dict[str, Any],
) -> float:
    tradability_by_id = tradability_by_id or expendability_by_id or {}
    give_all = give_assets or give_players
    exp_vals = [_tradability_weight(a, tradability_by_id) for a in give_all]
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


def starter_lineup_ppg(
    players: list[dict[str, Any]],
    roster_positions: list[str],
) -> float | None:
    """Sum of optimal-starter PPG (same logic as league starter_total_ppg)."""
    if not players or not roster_positions:
        return None
    from backend.services.analysis_service import _finalize_team_lineup

    return _finalize_team_lineup(players, roster_positions).get("starter_total_ppg")


def build_starter_lineup_slots(
    players: list[dict[str, Any]],
    roster_positions: list[str],
) -> list[dict[str, Any]]:
    """Optimal starters in roster slot order (QB, RB, WR, …)."""
    if not players or not roster_positions:
        return []
    from backend.services.analysis_service import _finalize_team_lineup

    lineup = _finalize_team_lineup(players, roster_positions)
    slots: list[dict[str, Any]] = []
    for row in lineup.get("starters") or []:
        player = row.get("player") or {}
        if not player:
            continue
        ppg = player.get("projected_ppg")
        if ppg is None:
            ppg = player.get("healthy_ppg")
        pid = player.get("player_id")
        ovr = player.get("dynasty_rating")
        slots.append(
            {
                "slot": str(row.get("slot") or "?"),
                "player_id": str(pid) if pid else None,
                "name": player.get("name"),
                "position": player.get("pos"),
                "ppg": round(float(ppg), 1) if ppg is not None else None,
                "ovr": int(ovr) if ovr is not None else None,
            }
        )
    return slots


def _annotate_lineup_slots(
    after_slots: list[dict[str, Any]],
    *,
    before_starter_ids: set[str],
    incoming_player_ids: set[str],
) -> list[dict[str, Any]]:
    annotated: list[dict[str, Any]] = []
    for slot in after_slots:
        pid = slot.get("player_id")
        pid_str = str(pid) if pid else ""
        is_incoming = pid_str in incoming_player_ids if pid_str else False
        is_changed = pid_str not in before_starter_ids if pid_str else False
        annotated.append(
            {
                **slot,
                "is_incoming": is_incoming,
                "is_changed": is_changed,
            }
        )
    return annotated


def _apply_trade_to_roster(
    roster: list[dict[str, Any]],
    *,
    remove_ids: set[str],
    add_players: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    remaining = [
        player
        for player in roster
        if str(player.get("player_id") or "") not in remove_ids
    ]
    existing = {str(player.get("player_id") or "") for player in remaining}
    for player in add_players:
        pid = str(player.get("player_id") or "")
        if pid and pid not in existing:
            remaining.append(player)
            existing.add(pid)
    return remaining


def roster_before_trade(
    current_roster: list[dict[str, Any]],
    *,
    received_players: list[dict[str, Any]],
    gave_players: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Rebuild pre-trade roster from current state (works for live and completed trades)."""
    received_ids = {
        str(p["player_id"]) for p in received_players if p.get("player_id")
    }
    reverted = [
        player
        for player in current_roster
        if str(player.get("player_id") or "") not in received_ids
    ]
    existing = {str(player.get("player_id") or "") for player in reverted}
    for player in gave_players:
        pid = str(player.get("player_id") or "")
        if pid and pid not in existing:
            reverted.append(player)
            existing.add(pid)
    return reverted


def evaluate_trade_lineup_deltas(
    side_a_roster: list[dict[str, Any]],
    side_b_roster: list[dict[str, Any]],
    *,
    give_players: list[dict[str, Any]],
    receive_players: list[dict[str, Any]],
    roster_positions: list[str],
    side_a_incoming_player_ids: set[str] | None = None,
    side_b_incoming_player_ids: set[str] | None = None,
    side_a_incoming_picks: list[dict[str, Any]] | None = None,
    side_b_incoming_picks: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Ideal starter PPG and post-trade lineup for each side (players only affect slots)."""
    give_ids = {str(p["player_id"]) for p in give_players if p.get("player_id")}
    recv_ids = {str(p["player_id"]) for p in receive_players if p.get("player_id")}
    incoming_a = side_a_incoming_player_ids or set()
    incoming_b = side_b_incoming_player_ids or set()

    a_after_roster = _apply_trade_to_roster(
        side_a_roster,
        remove_ids=give_ids,
        add_players=receive_players,
    )
    b_after_roster = _apply_trade_to_roster(
        side_b_roster,
        remove_ids=recv_ids,
        add_players=give_players,
    )

    before_a_slots = build_starter_lineup_slots(side_a_roster, roster_positions)
    after_a_slots = build_starter_lineup_slots(a_after_roster, roster_positions)
    before_b_slots = build_starter_lineup_slots(side_b_roster, roster_positions)
    after_b_slots = build_starter_lineup_slots(b_after_roster, roster_positions)

    before_a_ids = {str(s["player_id"]) for s in before_a_slots if s.get("player_id")}
    before_b_ids = {str(s["player_id"]) for s in before_b_slots if s.get("player_id")}

    a_before = starter_lineup_ppg(side_a_roster, roster_positions)
    a_after = starter_lineup_ppg(a_after_roster, roster_positions)
    b_before = starter_lineup_ppg(side_b_roster, roster_positions)
    b_after = starter_lineup_ppg(b_after_roster, roster_positions)

    def _side(
        before: float | None,
        after: float | None,
        after_slots: list[dict[str, Any]],
        before_ids: set[str],
        incoming_ids: set[str],
        incoming_picks: list[dict[str, Any]] | None,
    ) -> dict[str, Any]:
        if before is None and after is None and not after_slots:
            return {
                "before": None,
                "after": None,
                "delta": None,
                "starters": [],
                "incoming_picks": incoming_picks or [],
            }
        if before is None or after is None:
            delta = None
        else:
            delta = round(after - before, 1)
        return {
            "before": before,
            "after": after,
            "delta": delta,
            "starters": _annotate_lineup_slots(
                after_slots,
                before_starter_ids=before_ids,
                incoming_player_ids=incoming_ids,
            ),
            "incoming_picks": incoming_picks or [],
        }

    return {
        "side_a": _side(
            a_before,
            a_after,
            after_a_slots,
            before_a_ids,
            incoming_a,
            side_a_incoming_picks,
        ),
        "side_b": _side(
            b_before,
            b_after,
            after_b_slots,
            before_b_ids,
            incoming_b,
            side_b_incoming_picks,
        ),
    }
