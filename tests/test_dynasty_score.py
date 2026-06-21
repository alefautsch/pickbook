"""Tests for dynasty OVR scoring helpers."""

from dynasty_draft.dynasty_score import (
    DynastyScorer,
    DynastyWeights,
    _ovr_tv_norm,
    _per_game_production_norm,
    _smoothstep,
    _trajectory_signal,
)
from dynasty_draft.war_data import PlayerValue


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


def test_per_game_norm_ignores_sub_noise_worp_when_hppg_is_strong():
    """Deep-league replacement noise must not crush a strong HPPG signal."""
    max_worp_ppg = 0.2605
    max_hppg = 20.21
    hppg_only = _per_game_production_norm(
        {"healthy_ppg": 10.46, "worp_ppg": 0.0, "availability": 1.0},
        max_worp_ppg=max_worp_ppg,
        max_hppg=max_hppg,
    )
    noise_worp = _per_game_production_norm(
        {"healthy_ppg": 10.46, "worp_ppg": 0.0065, "availability": 1.0},
        max_worp_ppg=max_worp_ppg,
        max_hppg=max_hppg,
    )
    assert abs(hppg_only - noise_worp) < 0.02


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


def test_trajectory_ramps_smoothly_with_production():
    low = _trajectory_signal(0.80, 0.20, years_exp=1, pg_norm=0.20)
    mid = _trajectory_signal(0.80, 0.20, years_exp=1, pg_norm=0.40)
    full = _trajectory_signal(0.80, 0.20, years_exp=1, pg_norm=0.55)
    assert low < mid < full
    assert full > 0.5
    assert low < 0.15


def test_smoothstep_is_monotonic():
    assert _smoothstep(0.3, 0.5, 0.2) == 0.0
    assert _smoothstep(0.3, 0.5, 0.6) == 1.0
    assert 0.0 < _smoothstep(0.3, 0.5, 0.4) < 1.0


def test_flex_tv_dampens_low_per_game_hype_smoothly():
    raw = 0.65
    damped_low = _ovr_tv_norm("WR", raw, pg_norm=0.20)
    damped_mid = _ovr_tv_norm("WR", raw, pg_norm=0.38)
    clear = _ovr_tv_norm("WR", raw, pg_norm=0.50)
    assert damped_low < damped_mid < clear
    assert clear == raw


def test_score_pool_exposes_production_component():
    scorer = DynastyScorer(DynastyWeights())
    players = [
        (
            "p1",
            PlayerValue(
                name="Test Player",
                pos="WR",
                team="KC",
                worp_tier=2,
                worp=0.8,
                porp=8.0,
                trade_value=5000,
                spike_high_p=0.5,
                spike_mid_p=0.5,
                spike_low_p=0.5,
            ),
        )
    ]

    def _eff(_pid: str, _player: PlayerValue):
        return (0.8, False)

    result = scorer.score_pool(
        players,
        age_by_id={"p1": 24},
        years_exp_by_id={"p1": 2},
        effective_worp=_eff,
        per_game_by_id={"p1": {"healthy_ppg": 12.0, "worp_ppg": 0.05, "availability": 1.0}},
        per_game_max=(0.2, 20.0),
        pos_by_id={"p1": "WR"},
    )["p1"]

    components = result["dynasty_components"]
    assert components["production"] == components["worp"]
    assert "production_detail" in components
    assert components["production_detail"]["season_worp"] is not None


def test_trajectory_requires_production_floor():
    full = _trajectory_signal(0.80, 0.20, years_exp=1, pg_norm=0.55)
    none = _trajectory_signal(0.80, 0.20, years_exp=1, pg_norm=0.20)
    partial = _trajectory_signal(0.80, 0.20, years_exp=1, pg_norm=0.42)
    assert full > 0.5
    assert none < partial
    assert 0.0 < partial < full
