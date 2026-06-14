"""Tests for league-scoring adjustments."""

from dynasty_draft.scoring_adjustments import tep_adjusted_trade_value


def test_tep_adjusted_trade_value_scales_with_reception_premium():
    adjusted = tep_adjusted_trade_value(
        8000.0,
        position="TE",
        te_premium=0.5,
        hppg=15.0,
        receptions_per_game=6.0,
    )
    # Base HPPG 12.0 → 25% boost on TV
    assert adjusted == 10000.0


def test_tep_adjusted_trade_value_ignores_non_te_positions():
    assert tep_adjusted_trade_value(
        8000.0,
        position="WR",
        te_premium=0.5,
        hppg=15.0,
        receptions_per_game=6.0,
    ) == 8000.0
