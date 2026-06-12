"""Tests for trade expendability and package valuation."""

from backend.services.trade_engine import (
    annotate_players_with_expendability,
    effective_package_tv,
    evaluate_package_fairness,
    expendability_fraction,
    trade_fit_score,
)


def _player(pid: str, pos: str, tv: float, **kwargs) -> dict:
    return {"player_id": pid, "position": pos, "tv": tv, **kwargs}


def test_effective_package_tv_single_asset():
    assert effective_package_tv([{"tv": 8000}]) == 8000.0


def test_effective_package_tv_depth_discount():
    assets = [{"tv": 5000}, {"tv": 4000}, {"tv": 3000}]
    eff = effective_package_tv(assets)
    raw = 12000.0
    assert eff < raw
    expected = (5000 + 4000 * 0.70 + 3000 * 0.70) * (0.95**2)
    assert abs(eff - expected) < 0.01


def test_consolidation_premium_favors_stud_side():
    """Two mid pieces for one stud — raw TV even, adjusted favors the stud acquirer."""
    give = [_player("a", "WR", 5000), _player("b", "WR", 5000)]
    recv = [_player("c", "WR", 10000)]
    result = evaluate_package_fairness(give, recv)
    assert result["give_total_tv"] == 10000.0
    assert result["receive_total_tv"] == 10000.0
    assert result["receive_consolidating"] is True
    assert result["consolidation_tax_tv"] > 0
    assert result["fairness"] == "favors_counterparty"


def test_expendability_protects_stud_wr1():
    stud = expendability_fraction(
        _player("1", "WR", 7000, age=25, ovr=90),
        depth_rank=1,
        position_is_surplus=True,
        next_tv_at_position=4200,
        contender_tier="contender",
    )
    depth = expendability_fraction(
        _player("2", "WR", 4200, age=26, ovr=78),
        depth_rank=3,
        position_is_surplus=True,
        next_tv_at_position=2000,
        contender_tier="contender",
    )
    assert depth > stud


def test_annotate_players_depth_ranks():
    roster = [
        _player("w1", "WR", 7000),
        _player("w2", "WR", 4200),
        _player("r1", "RB", 3000),
    ]
    annotated = annotate_players_with_expendability(
        roster,
        surplus_positions={"WR"},
        contender_tier="competitive",
    )
    by_id = {p["player_id"]: p for p in annotated}
    assert by_id["w1"]["depth_rank"] == 1
    assert by_id["w2"]["depth_rank"] == 2
    assert by_id["w1"]["expendability_score"] < by_id["w2"]["expendability_score"]


def test_trade_fit_need_position():
    player = _player("1", "RB", 6000, age=27, hppg=12)
    fit = trade_fit_score(
        player,
        acquirer_need_positions={"RB"},
        acquirer_surplus_positions=set(),
        acquirer_tier="contender",
        seller_tier="rebuild",
    )
    low_fit = trade_fit_score(
        player,
        acquirer_need_positions=set(),
        acquirer_surplus_positions={"RB"},
        acquirer_tier="contender",
        seller_tier="rebuild",
    )
    assert fit > low_fit
