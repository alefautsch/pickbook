"""Tests for Sleeper ↔ war.csv player matching."""

from __future__ import annotations

from dynasty_draft.player_identity import sleeper_identity_score, snapshot_identity_score
from dynasty_draft.recommender import DraftState
from dynasty_draft.war_data import PlayerValue, WarData, normalize_name


class _WarStub(WarData):
    def __init__(self, players: dict[str, PlayerValue]) -> None:
        self.csv_path = None  # type: ignore[assignment]
        self.players = list(players.values())
        self.by_name = players
        self.value_inputs_by_name = {}


def _state(sleeper_players: dict[str, dict], war_players: dict[str, PlayerValue]) -> DraftState:
    return DraftState(
        draft={
            "settings": {"teams": 12, "rounds": 1},
            "type": "snake",
            "draft_order": {},
            "slot_to_roster_id": {},
        },
        picks=[],
        league={"league_id": "1", "roster_positions": ["QB", "RB", "WR", "TE", "FLEX"]},
        user_id="u1",
        war=_WarStub(war_players),
        sleeper_players=sleeper_players,
    )


def test_match_war_requires_position_alignment():
    key = normalize_name("Kenneth Walker")
    state = _state(
        {
            "8151": {"full_name": "Kenneth Walker III", "position": "RB"},
            "4634": {"full_name": "Kenneth Walker", "position": "WR"},
        },
        {
            key: PlayerValue(
                name="Kenneth Walker",
                pos="RB",
                team="KC",
                worp_tier=3,
                worp=0.36,
                porp=0.25,
                trade_value=3782.0,
                spike_high_p=None,
                spike_mid_p=None,
                spike_low_p=None,
            )
        },
    )

    assert state._match_war("8151") is not None
    assert state._match_war("4634") is None


def test_antonio_williams_rookie_scores_higher_than_veteran_duplicate():
    key = normalize_name("Antonio Williams")
    state = _state(
        {
            "13301": {
                "full_name": "Antonio Williams",
                "position": "WR",
                "team": "WAS",
                "years_exp": 0,
                "age": 21,
            },
            "7203": {
                "full_name": "Antonio Williams",
                "position": "RB",
                "team": None,
                "years_exp": 2,
                "age": 24,
            },
        },
        {
            key: PlayerValue(
                name="Antonio Williams",
                pos="WR",
                team="WAS",
                worp_tier=None,
                worp=None,
                porp=None,
                trade_value=1560.0,
                spike_high_p=None,
                spike_mid_p=None,
                spike_low_p=None,
            )
        },
    )

    assert state._match_war("13301") is not None
    assert state._match_war("7203") is None
    assert sleeper_identity_score(state, "13301") > sleeper_identity_score(state, "7203")


def test_snapshot_identity_prefers_rookie_profile():
    rookie = snapshot_identity_score(
        dynasty_rookie=True,
        years_exp=0,
        position="WR",
        nfl_team="WAS",
    )
    veteran = snapshot_identity_score(
        dynasty_rookie=False,
        years_exp=2,
        position="WR",
        nfl_team="WAS",
    )
    assert rookie > veteran
