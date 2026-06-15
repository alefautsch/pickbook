"""Tests for multi-source trade value blending."""

from dynasty_draft.trade_value_blend import TradeValueBlend
from dynasty_draft.war_data import PlayerValue


def _player(tv: float) -> PlayerValue:
    return PlayerValue(
        name="Test Player",
        pos="WR",
        team="DAL",
        worp_tier=1,
        worp=1.0,
        porp=1.0,
        trade_value=tv,
        spike_high_p=None,
        spike_mid_p=None,
        spike_low_p=None,
    )


def test_blend_three_way_market_sources():
    blend = TradeValueBlend(dd_weight=0.25, ktc_weight=0.25, dealer_weight=0.5)
    result = blend.blend(8000, 9000, dealer=10000)
    assert result == 9250.0


def test_blend_falls_back_without_dealer():
    blend = TradeValueBlend(dd_weight=0.25, ktc_weight=0.25, dealer_weight=0.5)
    result = blend.blend(8000, 9000, dealer=None)
    assert result == 8500.0


def test_from_config_defaults_include_dealer():
    blend = TradeValueBlend.from_config({"dynasty_dealer": {"enabled": True}}, ktc_available=True)
    assert blend.dealer_weight == 0.5
    assert blend.dd_weight == 0.25
    assert blend.ktc_weight == 0.25


def test_from_config_disables_dealer():
    blend = TradeValueBlend.from_config(
        {
            "dynasty_dealer": {"enabled": False},
            "trade_value_blend": {"dealer_weight": 0.5, "dd_weight": 0.25, "ktc_weight": 0.25},
        },
        ktc_available=True,
    )
    assert blend.dealer_weight == 0.0


def test_from_config_migrates_legacy_fifty_fifty():
    blend = TradeValueBlend.from_config(
        {
            "dynasty_dealer": {"enabled": True},
            "trade_value_blend": {"dd_weight": 0.5, "ktc_weight": 0.5},
        },
        ktc_available=True,
    )
    assert blend.dealer_weight == 0.5
    assert blend.dd_weight == 0.25
    assert blend.ktc_weight == 0.25


def test_apply_updates_player_trade_value():
    blend = TradeValueBlend(dd_weight=0.25, ktc_weight=0.25, dealer_weight=0.5)
    player = _player(8000)
    updated = blend.apply(player, 9000, dealer=10000)
    assert updated.trade_value == 9250.0
