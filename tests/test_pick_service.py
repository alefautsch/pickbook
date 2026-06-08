"""Tests for in-season draft pick inventory and valuation."""

from backend.services.pick_service import build_league_pick_inventory
from dynasty_draft.inseason_pick_values import infer_slot_tier, pick_label, value_pick


def test_infer_slot_tier_worst_team_is_early():
    assert infer_slot_tier(12, league_size=12) == "early"
    assert infer_slot_tier(1, league_size=12) == "late"
    assert infer_slot_tier(6, league_size=12) == "mid"


def test_value_pick_discounts_future_seasons():
    y1 = value_pick(round_no=1, slot_tier="mid", seasons_out=1)
    y2 = value_pick(round_no=1, slot_tier="mid", seasons_out=2)
    assert y1 > y2


def test_pick_label_includes_tier():
    assert "early" in pick_label(season="2027", round_no=1, slot_tier="early")


def test_build_inventory_applies_traded_picks():
    league = {"season": "2026", "settings": {"draft_rounds": 2}}
    rosters = [{"roster_id": 1}, {"roster_id": 2}]
    traded = [
        {
            "season": "2027",
            "round": 1,
            "roster_id": 1,
            "owner_id": 2,
        }
    ]
    inventory = build_league_pick_inventory(
        league_remote=league,
        rosters=rosters,
        traded_picks=traded,
    )
    owned = {
        (row["season"], row["round"], row["original_roster_id"]): row["owner_roster_id"]
        for row in inventory
    }
    assert owned[("2027", 1, "1")] == "2"
    assert owned[("2027", 1, "2")] == "2"
