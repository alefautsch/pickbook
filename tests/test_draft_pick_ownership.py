"""Tests for traded-pick ownership in rookie draft simulation."""

from __future__ import annotations

from dynasty_draft.draft_context import build_draft_timeline
from dynasty_draft.draft_pick_ownership import build_pick_owner_index, resolve_pick_owner
from dynasty_draft.recommender import DraftState
from dynasty_draft.war_data import WarData


class _WarEmpty(WarData):
    def __init__(self) -> None:
        self.csv_path = None  # type: ignore[assignment]
        self.players = []
        self.by_name = {}
        self.value_inputs_by_name = {}


def _draft_state(
  *,
  user_id: str = "user_40",
  my_roster_id: int = 40,
  pick_owner_index: dict | None = None,
  picks: list | None = None,
) -> DraftState:
    return DraftState(
        draft={
            "season": "2026",
            "type": "snake",
            "settings": {"teams": 4, "rounds": 2},
            "draft_order": {
                "user_10": 1,
                "user_20": 2,
                "user_30": 3,
                "user_40": 4,
            },
            "slot_to_roster_id": {
                "1": "10",
                "2": "20",
                "3": "30",
                "4": "40",
            },
        },
        picks=picks or [],
        league={"league_id": "lg1", "season": "2026", "roster_positions": ["QB", "RB", "WR", "TE"]},
        user_id=user_id,
        war=_WarEmpty(),
        sleeper_players={},
        league_users=[
            {"user_id": "user_10", "display_name": "Team Ten", "metadata": {"team_name": "Team Ten"}},
            {"user_id": "user_20", "display_name": "Team Twenty", "metadata": {"team_name": "Team Twenty"}},
            {"user_id": "user_30", "display_name": "Team Thirty", "metadata": {"team_name": "Team Thirty"}},
            {"user_id": "user_40", "display_name": "Team Forty", "metadata": {"team_name": "Team Forty"}},
        ],
        pick_owner_index=pick_owner_index or {},
    )


def test_resolve_pick_owner_defaults_to_original():
    index = build_pick_owner_index(
        [{"season": "2026", "round": 1, "roster_id": "30", "owner_id": "40"}]
    )
    assert resolve_pick_owner(index, season="2026", round_no=1, original_roster_id=10) == 10
    assert resolve_pick_owner(index, season="2026", round_no=1, original_roster_id=30) == 40


def test_owner_roster_for_pick_applies_trade():
    index = build_pick_owner_index(
        [{"season": "2026", "round": 1, "roster_id": "30", "owner_id": "40"}]
    )
    state = _draft_state(pick_owner_index=index)
    assert state.owner_roster_for_pick(3) == 40
    assert state.owner_roster_for_pick(4) == 40


def test_is_my_pick_uses_owner_not_franchise_slot():
    index = build_pick_owner_index(
        [{"season": "2026", "round": 1, "roster_id": "30", "owner_id": "40"}]
    )
    state = _draft_state(pick_owner_index=index)
    assert state.my_roster_id == 40
    assert state.is_my_pick_number(3) is True
    assert state.is_my_pick_number(1) is False


def test_next_pick_info_counts_until_acquired_pick():
    index = build_pick_owner_index(
        [{"season": "2026", "round": 1, "roster_id": "30", "owner_id": "40"}]
    )
    state = _draft_state(pick_owner_index=index)
    info = state.next_pick_info()
    assert info["pick_no"] == 1
    assert info["is_my_pick"] is False
    assert info["picks_until_mine"] == 2


def test_timeline_upcoming_pick_shows_traded_owner_team():
    index = build_pick_owner_index(
        [{"season": "2026", "round": 1, "roster_id": "30", "owner_id": "40"}]
    )
    state = _draft_state(pick_owner_index=index)
    rows = build_draft_timeline(state, past=None, upcoming=None)
    pick_three = next(row for row in rows if row["pick_no"] == 3)
    assert pick_three["team"] == "Team Forty"
    assert pick_three["is_me"] is True
