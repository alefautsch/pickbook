"""Tests for trade tagging and package valuation."""

from backend.services.trade_engine import (
    annotate_players_with_trade_tags,
    assign_pick_trade_tag,
    assign_player_trade_tag,
    effective_package_tv,
    evaluate_package_fairness,
    lineup_delta_ppg,
    production_ppg,
    top_trade_candidates,
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
    give = [_player("a", "WR", 5000), _player("b", "WR", 5000)]
    recv = [_player("c", "WR", 10000)]
    result = evaluate_package_fairness(give, recv)
    assert result["give_total_tv"] == 10000.0
    assert result["receive_total_tv"] == 10000.0
    assert result["receive_consolidating"] is True
    assert result["receive_value_adjustment"] > 0
    assert result["consolidation_tax_tv"] > 0
    # KTC stud adjustment makes the consolidated side more expensive to acquire.
    assert result["fairness"] == "favors_you"


def test_production_ppg_weights_recent():
    blended = production_ppg(_player("1", "WR", 1000, hppg=18.0, projected_ppg=10.0))
    assert blended > 14.0
    assert blended < 18.0


def test_lineup_delta_ppg_stud_vs_backup():
    roster = [
        _player("w1", "WR", 7000, hppg=18.0),
        _player("w2", "WR", 4200, hppg=10.0),
    ]
    delta = lineup_delta_ppg(roster[0], roster)
    assert delta == 8.0


def test_lineup_delta_ppg_last_on_depth_chart_not_inflated():
    """QB3 with no backup behind should not get full PPG as marginal value."""
    roster = [
        _player("qb1", "QB", 7000, hppg=18.0),
        _player("qb2", "QB", 4000, hppg=15.0),
        _player("qb3", "QB", 3000, hppg=14.0),
    ]
    assert lineup_delta_ppg(roster[2], roster) == 0.0
    tag = assign_player_trade_tag(
        roster[2],
        depth_rank=3,
        lineup_delta=0.0,
        tv_vs_production=0.0,
        position_is_surplus=False,
        contender_tier="contender",
    )
    assert tag is None


def test_lineup_delta_ppg_sole_position_player():
    roster = [_player("qb1", "QB", 5000, hppg=16.0)]
    assert lineup_delta_ppg(roster[0], roster) == 16.0


def test_core_tag_for_high_lineup_delta():
    tag = assign_player_trade_tag(
        _player("1", "WR", 7000, hppg=18.0),
        depth_rank=2,
        lineup_delta=8.0,
        tv_vs_production=5.0,
        position_is_surplus=True,
        contender_tier="contender",
    )
    assert tag == "core"


def test_trade_tag_for_replaceable_depth():
    tag = assign_player_trade_tag(
        _player("2", "WR", 2000, hppg=4.0, age=27),
        depth_rank=6,
        lineup_delta=1.0,
        tv_vs_production=10.0,
        position_is_surplus=True,
        contender_tier="contender",
    )
    assert tag == "trade"


def test_annotate_players_production_depth_ranks():
    roster = [
        _player("w1", "WR", 4200, hppg=18.0),
        _player("w2", "WR", 7000, hppg=10.0),
        _player("w3", "WR", 1000, hppg=5.5, age=27),
        _player("w4", "WR", 800, hppg=5.0, age=28),
    ]
    annotated = annotate_players_with_trade_tags(
        roster,
        surplus_positions={"WR"},
        contender_tier="contender",
    )
    by_id = {p["player_id"]: p for p in annotated}
    assert by_id["w1"]["depth_rank"] == 1
    assert by_id["w1"]["trade_tag"] == "core"
    assert by_id["w2"]["trade_tag"] is None
    assert by_id["w3"]["trade_tag"] == "trade"


def test_contender_own_first_is_trade_pick():
    pick = {
        "round": 1,
        "slot_tier": "late",
        "is_own_slot": True,
        "trade_value": 4200,
    }
    assert assign_pick_trade_tag(pick, contender_tier="contender") == "trade"


def test_rebuild_early_first_is_core_pick():
    pick = {
        "round": 1,
        "slot_tier": "early",
        "is_own_slot": True,
        "trade_value": 8500,
    }
    assert assign_pick_trade_tag(pick, contender_tier="rebuild") == "core"


def test_top_trade_candidates_include_picks():
    players = [
        _player("w1", "WR", 7000, hppg=18.0),
        _player("w8", "WR", 500, hppg=2.0, age=26),
    ]
    picks = [
        {
            "season": "2027",
            "round": 1,
            "slot_tier": "late",
            "is_own_slot": True,
            "trade_value": 4200,
            "label": "2027 1.12",
        }
    ]
    candidates = top_trade_candidates(
        players,
        picks=picks,
        surplus_positions={"WR"},
        contender_tier="contender",
    )
    types = {c["asset_type"] for c in candidates}
    assert "pick" in types


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
