"""Tests for trade tagging and package valuation."""

from backend.services.trade_engine import (
    STUD_PREMIUM_ELITE,
    STUD_PREMIUM_HIGH,
    annotate_players_with_trade_tags,
    asset_tv_for_trade,
    assign_pick_trade_tag,
    assign_player_trade_tag,
    effective_package_tv,
    evaluate_package_fairness,
    lineup_delta_ppg,
    pick_trade_tv_multiplier,
    production_ppg,
    top_trade_candidates,
    trade_fit_score,
)


def _player(pid: str, pos: str, tv: float, **kwargs) -> dict:
    return {"player_id": pid, "position": pos, "tv": tv, **kwargs}


def test_effective_package_tv_single_asset():
    assert effective_package_tv([{"tv": 8000}]) == 8000.0


def test_stud_value_adjustment_tiers():
    from backend.services.trade_engine import stud_value_adjustment

    elite = stud_value_adjustment([_player("1", "RB", 8000)])
    assert elite == round(8000 * STUD_PREMIUM_ELITE, 1)

    high = stud_value_adjustment([_player("2", "WR", 6500)])
    assert high == round(6500 * STUD_PREMIUM_HIGH, 1)

    depth_pkg = stud_value_adjustment(
        [_player("a", "WR", 3000), _player("b", "WR", 2500), _player("c", "WR", 2000)]
    )
    assert depth_pkg == round(-7500 * 0.12, 1)


def test_effective_package_tv_depth_discount():
    assets = [{"tv": 5000}, {"tv": 4000}, {"tv": 3000}]
    eff = effective_package_tv(assets)
    raw = 12000.0
    assert eff < raw
    expected = (5000 + 4000 * 0.70 + 3000 * 0.70) * (0.95**2)
    assert abs(eff - expected) < 0.01


def test_pick_trade_tv_discounts_later_rounds():
    r1 = {"label": "2026 1.06", "round": 1, "tv": 4684}
    r2 = {"label": "2026 2.06", "round": 2, "tv": 2000}
    r3 = {"label": "2027 3.04", "round": 3, "tv": 1200}
    assert asset_tv_for_trade(r1) == 4684.0
    assert asset_tv_for_trade(r2) == 1000.0
    assert asset_tv_for_trade(r3) == round(1200 * pick_trade_tv_multiplier(3), 2)


def test_late_picks_do_not_inflate_package_vs_stud():
    """Shough + dart picks should not look like fair value for an elite QB."""
    give = [
        _player("s", "QB", 2990, name="Tyler Shough"),
        {"label": "2026 2.05", "round": 2, "tv": 1800},
        {"label": "2027 3.02", "round": 3, "tv": 1100},
        {"label": "2027 3.08", "round": 3, "tv": 1000},
    ]
    recv = [_player("tl", "QB", 8500, name="Trevor Lawrence")]
    result = evaluate_package_fairness(give, recv)
    give_catalog = 2990 + 1800 + 1100 + 1000
    assert result["give_total_tv"] < give_catalog * 0.75
    assert result["fairness"] in ("favors_you", "fair")


def test_consolidation_premium_favors_stud_side():
    give = [_player("a", "WR", 5000), _player("b", "WR", 5000)]
    recv = [_player("c", "WR", 10000)]
    result = evaluate_package_fairness(give, recv)
    assert result["give_total_tv"] == 10000.0
    assert result["receive_total_tv"] == 10000.0
    assert result["receive_consolidating"] is True
    assert result["give_value_adjustment"] == 0.0
    assert result["receive_value_adjustment"] > 0
    assert result["consolidation_tax_tv"] > 0
    # KTC stud adjustment makes the consolidated side more expensive to acquire.
    assert result["fairness"] == "favors_you"


def test_stud_adjustment_only_on_one_side_1v1():
    """Two single studs — premium applies to consolidating side only, not both."""
    result = evaluate_package_fairness(
        [_player("1", "WR", 6500)],
        [_player("2", "RB", 6400)],
    )
    assert result["give_value_adjustment"] > 0
    assert result["receive_value_adjustment"] == 0.0


def test_egbuka_plus_pick_for_judkins_no_stud_adj_or_tax():
    give = [
        _player("e", "WR", 4279, name="Emeka Egbuka"),
        {"label": "2026 1.06", "tv": 4684},
    ]
    recv = [_player("j", "RB", 3698, name="Quinshon Judkins")]
    result = evaluate_package_fairness(give, recv)
    assert result["give_value_adjustment"] == 0.0
    assert result["receive_value_adjustment"] == 0.0
    assert result["consolidation_tax_tv"] == 0.0


def test_depth_for_stud_penalty_only_on_dispersing_side():
    give = [
        _player("a", "WR", 3000),
        _player("b", "WR", 2500),
        _player("c", "WR", 2000),
    ]
    recv = [_player("s", "WR", 4200)]
    result = evaluate_package_fairness(give, recv)
    assert result["give_value_adjustment"] < 0
    assert result["receive_value_adjustment"] == 0.0


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


def _lineup_player(
    pid: str, pos: str, ppg: float, tv: float = 5000, ovr: int = 80
) -> dict:
    return {
        "player_id": pid,
        "pos": pos,
        "dynasty_rating": ovr,
        "projected_ppg": ppg,
        "healthy_ppg": ppg,
        "trade_value": tv,
    }


def test_evaluate_trade_lineup_deltas_upgrades_starter():
    from backend.services.trade_engine import (
        evaluate_trade_lineup_deltas,
        starter_lineup_ppg,
    )

    roster_positions = ["QB", "RB", "WR", "TE", "FLEX"]
    side_a = [
        _lineup_player("qb1", "QB", 22.0, 9000, 92),
        _lineup_player("rb1", "RB", 17.0, 8000, 88),
        _lineup_player("wr1", "WR", 15.0, 7500, 85),
        _lineup_player("wr2", "WR", 11.0, 4500, 72),
    ]
    side_b = [
        _lineup_player("qb2", "QB", 20.0, 8500, 90),
        _lineup_player("wr3", "WR", 19.0, 8200, 87),
    ]

    before = starter_lineup_ppg(side_a, roster_positions)
    assert before is not None

    result = evaluate_trade_lineup_deltas(
        side_a,
        side_b,
        give_players=[_lineup_player("wr2", "WR", 11.0, 4500, 72)],
        receive_players=[_lineup_player("wr3", "WR", 19.0, 8200, 87)],
        roster_positions=roster_positions,
        side_a_incoming_player_ids={"wr3"},
        side_b_incoming_player_ids={"wr2"},
    )

    after_a = starter_lineup_ppg(
        [p for p in side_a if p["player_id"] != "wr2"]
        + [_lineup_player("wr3", "WR", 19.0, 8200, 87)],
        roster_positions,
    )

    assert result["side_a"]["before"] == before
    assert result["side_a"]["after"] == after_a
    assert result["side_a"]["delta"] == round((after_a or 0) - (before or 0), 1)
    assert result["side_a"]["delta"] > 0
    assert result["side_b"]["delta"] < 0

    a_starters = result["side_a"]["starters"]
    assert len(a_starters) > 0
    wr3_slot = next(s for s in a_starters if s["player_id"] == "wr3")
    assert wr3_slot["is_incoming"] is True
    assert wr3_slot["is_changed"] is True
    assert wr3_slot["ovr"] == 87
    wr2_slot = next((s for s in a_starters if s["player_id"] == "wr2"), None)
    assert wr2_slot is None
