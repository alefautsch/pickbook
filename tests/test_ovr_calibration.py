"""Tests for OVR calibration divergence reporting."""

from backend.services.ovr_calibration import build_calibration_report


def _row(player_id: str, name: str, tv: float, ovr: int, hppg: float = 10.0) -> dict:
    return {
        "player_id": player_id,
        "player_name": name,
        "position": "WR",
        "trade_value": tv,
        "dynasty_rating": ovr,
        "hppg": hppg,
        "components_json": {
            "production": 0.4,
            "per_game": 0.45,
            "production_detail": {"season_worp": 0.3, "per_game": 0.45},
        },
        "value_inputs_json": {"dynasty_daddy": {"source": "api"}},
    }


def test_calibration_flags_market_ahead_of_ovr():
    rows = [
        _row("1", "Market Darling", tv=7000, ovr=72),
        _row("2", "Balanced", tv=5000, ovr=80),
        _row("3", "Producer", tv=3000, ovr=88),
    ]
    report = build_calibration_report(rows, divergence_threshold=1, top_n=5)
    darling = next(d for d in report["divergences"] if d["player_name"] == "Market Darling")
    assert darling["pattern"] == "market_ahead"
    assert darling["rank_gap"] < 0


def test_calibration_sniff_test_mcmillan_pattern():
    """Higher TV + HPPG should not rank far below a lower-TV peer."""
    rows = [
        {
            "player_id": "burden",
            "player_name": "Luther Burden",
            "position": "WR",
            "trade_value": 5228,
            "dynasty_rating": 84,
            "hppg": 8.28,
            "components_json": {"production": 0.406, "per_game": 0.406},
            "value_inputs_json": {"dynasty_daddy": {"source": "api"}},
        },
        {
            "player_id": "mcmillan",
            "player_name": "Tetairoa McMillan",
            "position": "WR",
            "trade_value": 6506,
            "dynasty_rating": 87,
            "hppg": 10.46,
            "components_json": {"production": 0.518, "per_game": 0.518},
            "value_inputs_json": {"dynasty_daddy": {"source": "api"}},
        },
    ]
    report = build_calibration_report(rows, divergence_threshold=25)
    mcmillan_flags = [d for d in report["divergences"] if d["player_name"] == "Tetairoa McMillan"]
    assert not mcmillan_flags
