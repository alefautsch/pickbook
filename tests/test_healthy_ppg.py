"""Tests for healthy-game filtering from nflverse snap data."""

import pandas as pd

from dynasty_draft.healthy_ppg import _with_health_flags


def test_relative_snap_share_excludes_mid_game_injury_outlier():
    rows = [
        {
            "player_id": "wr1",
            "player_display_name": "Full Time WR",
            "position": "WR",
            "half_ppr": 10.0,
            "offense_snaps": 64,
            "offense_pct": 0.94,
        },
        {
            "player_id": "wr1",
            "player_display_name": "Full Time WR",
            "position": "WR",
            "half_ppr": 20.0,
            "offense_snaps": 66,
            "offense_pct": 0.99,
        },
        {
            "player_id": "wr1",
            "player_display_name": "Full Time WR",
            "position": "WR",
            "half_ppr": 8.0,
            "offense_snaps": 61,
            "offense_pct": 0.92,
        },
        {
            "player_id": "wr1",
            "player_display_name": "Full Time WR",
            "position": "WR",
            "half_ppr": 3.0,
            "offense_snaps": 25,
            "offense_pct": 0.33,
        },
    ]

    flagged = _with_health_flags(
        pd.DataFrame(rows),
        ["player_id", "player_display_name", "position"],
    )

    assert flagged["healthy"].tolist() == [True, True, True, False]


def test_relative_snap_share_keeps_normal_rotational_role():
    rows = [
        {
            "player_id": "rb1",
            "player_display_name": "Rotational RB",
            "position": "RB",
            "half_ppr": 9.0,
            "offense_snaps": 24,
            "offense_pct": 0.42,
        },
        {
            "player_id": "rb1",
            "player_display_name": "Rotational RB",
            "position": "RB",
            "half_ppr": 11.0,
            "offense_snaps": 27,
            "offense_pct": 0.45,
        },
        {
            "player_id": "rb1",
            "player_display_name": "Rotational RB",
            "position": "RB",
            "half_ppr": 7.0,
            "offense_snaps": 20,
            "offense_pct": 0.34,
        },
    ]

    flagged = _with_health_flags(
        pd.DataFrame(rows),
        ["player_id", "player_display_name", "position"],
    )

    assert flagged["healthy"].tolist() == [True, True, True]
