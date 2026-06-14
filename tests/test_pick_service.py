"""Tests for in-season draft pick inventory and valuation."""

from backend.services.pick_service import build_league_pick_inventory
from dynasty_draft.inseason_pick_values import (
    infer_slot_tier,
    pick_label,
    slot_in_round,
    value_pick,
)


def test_infer_slot_tier_worst_team_is_early():
    assert infer_slot_tier(12, league_size=12) == "early"
    assert infer_slot_tier(1, league_size=12) == "late"
    assert infer_slot_tier(6, league_size=12) == "mid"


def test_value_pick_discounts_future_seasons():
    y1 = value_pick(round_no=1, slot_tier="mid", seasons_out=1)
    y2 = value_pick(round_no=1, slot_tier="mid", seasons_out=2)
    assert y1 > y2


def test_value_pick_premium_for_top_slot():
    generic = value_pick(round_no=1, slot_tier="early", seasons_out=1)
    top = value_pick(
        round_no=1,
        slot_tier="early",
        seasons_out=1,
        slot_in_round_no=1,
    )
    assert top > generic
    assert generic == 5600
    assert top == round(5600 * 1.08, 1)


def test_value_pick_uses_ktc_with_slot_spread():
    def ktc_lookup(season: str, round_no: int, slot_tier: str) -> float | None:
        table = {
            ("2026", 1, "early"): 5573.0,
            ("2026", 1, "mid"): 4550.0,
            ("2026", 1, "late"): 3878.0,
        }
        return table.get((season, round_no, slot_tier))

    def ktc_slot_lookup(season: str, round_no: int, slot_in_round: int) -> float | None:
        table = {
            ("2026", 1, 1): 6471.0,
            ("2026", 1, 2): 5958.0,
            ("2026", 1, 3): 5445.0,
        }
        return table.get((season, round_no, slot_in_round))

    top = value_pick(
        round_no=1,
        slot_tier="early",
        seasons_out=1,
        slot_in_round_no=1,
        pick_season="2026",
        ktc_lookup=ktc_lookup,
        ktc_slot_lookup=ktc_slot_lookup,
        league_size=12,
    )
    third = value_pick(
        round_no=1,
        slot_tier="early",
        seasons_out=1,
        slot_in_round_no=3,
        pick_season="2026",
        ktc_lookup=ktc_lookup,
        ktc_slot_lookup=ktc_slot_lookup,
        league_size=12,
    )
    assert top == 6471.0
    assert third == 5445.0
    assert third < top


def test_slot_in_round_worst_team_is_first_pick():
    assert slot_in_round(12, league_size=12) == 1
    assert slot_in_round(1, league_size=12) == 12


def test_pick_label_uses_slot_notation():
    assert pick_label(
        season="2026",
        round_no=1,
        slot_tier="early",
        slot_in_round_no=1,
    ) == "2026 1.01"


def test_pick_label_includes_tier():
    label = pick_label(
        season="2027",
        round_no=1,
        slot_tier="late",
        slot_certainty="projected",
    )
    assert label == "2027 1st (proj)"


def test_build_inventory_includes_current_season():
    from backend.services.pick_service import _future_seasons

    assert _future_seasons("2026") == ["2026", "2027", "2028"]


def test_slot_in_round_startup_rookie_order_is_direct():
    assert slot_in_round(12, league_size=12, startup_draft_slot=4, startup_is_rookie_order=True) == 4
    assert slot_in_round(12, league_size=12, startup_draft_slot=4, startup_is_rookie_order=False) == 9


def test_infer_slot_tier_startup_rookie_order():
    assert infer_slot_tier(None, league_size=10, startup_draft_slot=4, startup_is_rookie_order=True) == "mid"
    assert infer_slot_tier(None, league_size=10, startup_draft_slot=1, startup_is_rookie_order=True) == "early"
    assert infer_slot_tier(None, league_size=10, startup_draft_slot=10, startup_is_rookie_order=True) == "late"


def test_pick_slot_certainty_pre_draft_future_is_projected():
    from dynasty_draft.inseason_pick_values import pick_slot_certainty

    assert pick_slot_certainty(is_own_slot=True, seasons_out=1, league_pre_draft=True) == "projected"
    assert pick_slot_certainty(is_own_slot=False, seasons_out=1, league_pre_draft=True) == "projected"
    assert pick_slot_certainty(is_own_slot=False, seasons_out=1, league_pre_draft=False) == "known"


def test_university_terrace_startup_pick_labels():
    """Pre-draft startup: 2026 slots from draft order; 2027+ projected."""
    from backend.services.pick_service import (
        build_league_pick_inventory,
        _use_startup_slots_for_season,
        _league_is_pre_draft,
    )
    from dynasty_draft.inseason_pick_values import (
        infer_slot_tier,
        pick_label,
        pick_slot_certainty,
        seasons_until,
        slot_in_round,
    )

    league = {"season": "2026", "status": "pre_draft", "settings": {"draft_rounds": 3}}
    rosters = [{"roster_id": i, "owner_id": f"u{i}"} for i in range(1, 11)]
    rosters[2] = {"roster_id": 3, "owner_id": "205966933634326528"}
    rosters[9] = {"roster_id": 10, "owner_id": "520790963966283776"}

    startup_slots = {"3": 4, "10": 6}
    traded = [
        {"season": "2026", "round": 1, "roster_id": 10, "owner_id": 3},
    ]
    inventory = build_league_pick_inventory(
        league_remote=league,
        rosters=rosters,
        traded_picks=traded,
    )
    my_picks = [p for p in inventory if p["owner_roster_id"] == "3" and p["round"] == 1]

    labels = []
    for row in my_picks:
        use_startup = _use_startup_slots_for_season(league, row["season"])
        startup_slot = startup_slots.get(row["original_roster_id"]) if use_startup else None
        slot_no = slot_in_round(
            None,
            league_size=10,
            startup_draft_slot=startup_slot,
            startup_is_rookie_order=use_startup,
        )
        certainty = pick_slot_certainty(
            is_own_slot=row["original_roster_id"] == row["owner_roster_id"],
            seasons_out=seasons_until("2026", row["season"]),
            league_pre_draft=_league_is_pre_draft(league),
        )
        if use_startup and slot_no is not None:
            certainty = "known"
        tier = infer_slot_tier(
            None,
            league_size=10,
            startup_draft_slot=startup_slot,
            startup_is_rookie_order=use_startup,
        )
        labels.append(
            pick_label(
                season=row["season"],
                round_no=row["round"],
                slot_tier=tier,
                slot_in_round_no=slot_no,
                slot_certainty=certainty,
            )
        )

    assert "2026 1.04" in labels
    assert "2026 1.06" in labels

    y2027 = pick_label(
        season="2027",
        round_no=1,
        slot_tier="mid",
        slot_in_round_no=3,
        slot_certainty=pick_slot_certainty(
            is_own_slot=False,
            seasons_out=1,
            league_pre_draft=True,
        ),
    )
    assert y2027 == "2027 1st (proj)"


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
