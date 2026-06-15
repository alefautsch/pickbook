"""Team OVR should keep float precision before league-relative adjustment."""

from __future__ import annotations

from backend.services.analysis_service import _league_adjust_team_ovrs, _weighted_rating


def test_weighted_rating_keeps_fractional_average() -> None:
    players = [
        ({"dynasty_rating": 82}, 1.0),
        ({"dynasty_rating": 81}, 1.0),
        ({"dynasty_rating": 81}, 0.15),
    ]
    assert _weighted_rating(players) == 81.46511627906978


def test_league_adjust_spreads_tight_balanced_league() -> None:
    teams = [
        {"roster_id": "1", "avg_dynasty_rating": 82.45},
        {"roster_id": "2", "avg_dynasty_rating": 82.17},
        {"roster_id": "3", "avg_dynasty_rating": 81.85},
        {"roster_id": "4", "avg_dynasty_rating": 81.70},
        {"roster_id": "5", "avg_dynasty_rating": 81.36},
        {"roster_id": "6", "avg_dynasty_rating": 81.25},
        {"roster_id": "7", "avg_dynasty_rating": 81.19},
        {"roster_id": "8", "avg_dynasty_rating": 81.17},
        {"roster_id": "9", "avg_dynasty_rating": 80.93},
        {"roster_id": "10", "avg_dynasty_rating": 80.80},
    ]
    _league_adjust_team_ovrs(teams)

    ovrs = [team["avg_dynasty_rating"] for team in teams]
    assert max(ovrs) - min(ovrs) >= 8
    assert len(set(ovrs)) == len(teams)


def test_league_adjust_breaks_rounding_ties() -> None:
    teams = [
        {"roster_id": "1", "avg_dynasty_rating": 80.12},
        {"roster_id": "2", "avg_dynasty_rating": 80.08},
        {"roster_id": "3", "avg_dynasty_rating": 79.99},
        {"roster_id": "4", "avg_dynasty_rating": 79.50},
        {"roster_id": "5", "avg_dynasty_rating": 79.10},
    ]
    _league_adjust_team_ovrs(teams)
    ovrs = [team["avg_dynasty_rating"] for team in teams]
    assert len(set(ovrs)) == len(teams)
