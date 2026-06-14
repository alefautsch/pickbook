"""Tests for KTC slot-specific pick expansion."""

from dynasty_draft.ktc_pick_slots import (
    _calc_simple_single_mode,
    expand_slot_values,
    parse_tier_pick_name,
)


def test_parse_tier_pick_name():
    assert parse_tier_pick_name("2026 Early 1st") == ("2026", 1, "early")
    assert parse_tier_pick_name("2027 Mid 2nd") == ("2027", 2, "mid")
    assert parse_tier_pick_name("Jaxon Smith-Njigba") is None


def test_simple_slot_expansion_monotonic_round_one():
    tiers = [5573, 4547, 3878, 3304, 2977, 2825, 2300, 2156, 2073, 1709, 1637, 1565]
    slots = expand_slot_values(tiers, season="2026", league_size=12, rounds=1)
    round_one = [slots[(1, i)] for i in range(1, 13)]
    assert round_one[0] > round_one[1] > round_one[2] > round_one[3]
    assert round_one[0] == _calc_simple_single_mode(tiers)[0]


def test_rookie_mode_anchors_top_pick_to_class():
    tiers = [5573, 4547, 3878, 3304, 2977, 2825, 2300, 2156, 2073, 1709, 1637, 1565]
    rookies = [7655, 5200, 4600, 4300]
    slots = expand_slot_values(
        tiers,
        season="2026",
        league_size=12,
        rounds=1,
        rookie_values=rookies,
        use_rookie_mode=True,
    )
    assert slots[(1, 1)] == round(7655 * 1.03, 1)
    assert slots[(1, 1)] > slots[(1, 2)] > slots[(1, 3)]
