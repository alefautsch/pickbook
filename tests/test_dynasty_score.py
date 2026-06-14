"""Tests for dynasty OVR scoring helpers."""

from dynasty_draft.dynasty_score import _per_game_production_norm


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
