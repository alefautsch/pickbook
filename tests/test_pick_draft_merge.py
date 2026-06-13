"""Test draft-level traded pick merge."""

from backend.services.pick_service import collect_league_traded_picks, build_league_pick_inventory


class _FakeClient:
    def get_traded_picks(self, league_id: str):
        return [{"season": "2027", "round": 1, "roster_id": "1", "owner_id": "2"}]

    def get_league_drafts(self, league_id: str):
        return [{"draft_id": "draft1"}]

    def _get(self, path: str):
        if path.endswith("/traded_picks"):
            return [
                {"season": "2026", "round": 1, "roster_id": "3", "owner_id": "3"},
            ]
        return []


def test_collect_league_traded_picks_merges_draft_level():
    rows = collect_league_traded_picks(_FakeClient(), "league1")
    keys = {(r["season"], r["round"], r["roster_id"]) for r in rows}
    assert ("2027", 1, "1") in keys
    assert ("2026", 1, "3") in keys


def test_pick_label_projected_future_own():
    from dynasty_draft.inseason_pick_values import pick_label

    assert (
        pick_label(
            season="2028",
            round_no=1,
            slot_tier="late",
            slot_in_round_no=10,
            slot_certainty="projected",
        )
        == "2028 1st (proj)"
    )
