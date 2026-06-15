"""Tests for dynasty OVR scoring helpers."""

from dynasty_draft.dynasty_score import (
    _ovr_tv_norm,
    _per_game_production_norm,
    _trajectory_signal,
)


def test_per_game_norm_treats_zero_worp_ppg_as_missing():
    """worp_ppg=0 should not take a different branch than a tiny positive value."""
    max_worp_ppg = 0.2452
    max_hppg = 20.21

    breece = _per_game_production_norm(
        {
            "healthy_ppg": 12.34,
            "worp_ppg": 0.0048,
            "availability": 0.941,
        },
        max_worp_ppg=max_worp_ppg,
        max_hppg=max_hppg,
    )
    zero_worp = _per_game_production_norm(
        {
            "healthy_ppg": 12.34,
            "worp_ppg": 0.0,
            "availability": 0.941,
        },
        max_worp_ppg=max_worp_ppg,
        max_hppg=max_hppg,
    )
    javonte = _per_game_production_norm(
        {
            "healthy_ppg": 11.74,
            "worp_ppg": 0.0,
            "availability": 0.824,
        },
        max_worp_ppg=max_worp_ppg,
        max_hppg=max_hppg,
    )

    assert abs(breece - zero_worp) < 0.02
    assert breece > javonte


def test_qb_per_game_norm_uses_replacement_not_max_ppg():
    """12 PPG backup QB should not score ~50% of max just because Allen exists."""
    max_hppg = 23.0
    replacement = 16.0
    backup = _per_game_production_norm(
        {"healthy_ppg": 12.0, "worp_ppg": 0.0, "availability": 1.0},
        max_worp_ppg=0.2,
        max_hppg=max_hppg,
        position="QB",
        replacement_ppg=replacement,
    )
    starter = _per_game_production_norm(
        {"healthy_ppg": 20.0, "worp_ppg": 0.05, "availability": 1.0},
        max_worp_ppg=0.2,
        max_hppg=max_hppg,
        position="QB",
        replacement_ppg=replacement,
    )
    assert backup < 0.25
    assert starter > 0.35
    assert starter > backup


def test_trajectory_requires_production_floor():
    full = _trajectory_signal(0.80, 0.20, years_exp=1, pg_norm=0.55)
    none = _trajectory_signal(0.80, 0.20, years_exp=1, pg_norm=0.25)
    partial = _trajectory_signal(0.80, 0.20, years_exp=1, pg_norm=0.42)
    assert full > 0.5
    assert none == 0.0
    assert 0.0 < partial < full


def test_flex_tv_dampens_low_per_game_hype():
    raw = 0.65
    damped = _ovr_tv_norm("WR", raw, pg_norm=0.26)
    clear = _ovr_tv_norm("WR", raw, pg_norm=0.50)
    assert damped < raw
    assert clear == raw
