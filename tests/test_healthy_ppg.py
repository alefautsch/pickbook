"""Tests for healthy-game filtering from nflverse snap data."""

import pandas as pd

from dynasty_draft.healthy_ppg import _half_ppr_points, _with_health_flags


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


def test_half_ppr_points_adds_te_premium_for_tight_ends():
    row = pd.Series(
        {
            "position": "TE",
            "fantasy_points": 8.0,
            "fantasy_points_ppr": 12.0,
            "receptions": 4.0,
        }
    )
    base = _half_ppr_points(row, ppr=0.5)
    tep = _half_ppr_points(row, ppr=0.5, te_premium=0.5)
    assert base == 10.0
    assert tep == 12.0


def test_half_ppr_points_te_premium_does_not_apply_to_wr():
    row = pd.Series(
        {
            "position": "WR",
            "fantasy_points": 8.0,
            "fantasy_points_ppr": 12.0,
            "receptions": 4.0,
        }
    )
    assert _half_ppr_points(row, ppr=0.5, te_premium=0.5) == 10.0
