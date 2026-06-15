"""Targeted acquire/sell packages for the trade calculator."""

from backend.services.advisor_tools import (
    generate_disposal_packages,
    generate_trade_calc_packages,
)


def _player(pid: str, pos: str, tv: float, **kwargs) -> dict:
    return {"player_id": pid, "name": kwargs.pop("name", pid), "position": pos, "tv": tv, **kwargs}


def _pick(season: str, rnd: int, orig: str, tv: float, **kwargs) -> dict:
    return {
        "season": season,
        "round": rnd,
        "original_roster_id": orig,
        "owner_roster_id": kwargs.get("owner_roster_id", orig),
        "slot_tier": kwargs.get("slot_tier", "early"),
        "trade_value": tv,
        "label": kwargs.get("label", f"{season} {rnd}"),
        "is_own_slot": True,
    }


def test_acquire_selected_player_from_counterparty():
    roster_players = {
        "1": [_player("w1", "WR", 5000, hppg=12.0, projected_ppg=12.0)],
        "2": [_player("rb1", "RB", 6500, name="Stud RB", hppg=14.0, projected_ppg=14.0, age=23)],
    }
    picks_by_roster = {
        "1": [_pick("2027", 1, "1", 7000, label="2027 1.10")],
        "2": [],
    }
    packages = generate_trade_calc_packages(
        mode="acquire",
        proposer_roster_id="1",
        counterparty_roster_id="2",
        player_ids=["rb1"],
        pick_refs=[],
        roster_players=roster_players,
        picks_by_roster=picks_by_roster,
        contender_tier_by_roster={"1": "contender", "2": "rebuild"},
        team_names={"1": "Buyer", "2": "Seller"},
    )
    assert packages
    assert packages[0]["receive"]["players"][0]["player_id"] == "rb1"
    assert packages[0]["counterparty"]["roster_id"] == "2"


def test_sell_player_generates_league_offers():
    roster_players = {
        "1": [_player("rb1", "RB", 6500, name="Stud RB", hppg=14.0, projected_ppg=14.0, age=23)],
        "2": [_player("w1", "WR", 5000, hppg=12.0, projected_ppg=12.0)],
        "3": [_player("w2", "WR", 4800, hppg=11.0, projected_ppg=11.0)],
    }
    picks_by_roster = {
        "1": [],
        "2": [_pick("2027", 1, "2", 7000, label="2027 1.05")],
        "3": [_pick("2026", 2, "3", 2800, label="2026 2.08")],
    }
    packages = generate_disposal_packages(
        seller_roster_id="1",
        asset_player_ids=["rb1"],
        asset_pick_refs=[],
        roster_players=roster_players,
        picks_by_roster=picks_by_roster,
        contender_tier_by_roster={"1": "contender", "2": "contender", "3": "rebuild"},
        team_names={"2": "Team B", "3": "Team C"},
    )
    assert packages
    assert all(p["give"]["players"][0]["player_id"] == "rb1" for p in packages)
    counterparties = {p["counterparty"]["roster_id"] for p in packages}
    assert counterparties.issubset({"2", "3"})


def test_sell_pick_generates_offer():
    roster_players = {
        "1": [],
        "2": [
            _player("w1", "WR", 5200, hppg=12.0, projected_ppg=12.0, age=25),
            _player("w2", "WR", 3200, hppg=7.0, projected_ppg=7.0, age=27),
        ],
    }
    picks_by_roster = {
        "1": [_pick("2027", 1, "1", 7200, label="2027 1.03")],
        "2": [_pick("2028", 2, "2", 2200, label="2028 2.06")],
    }
    packages = generate_disposal_packages(
        seller_roster_id="1",
        asset_player_ids=[],
        asset_pick_refs=[{"season": "2027", "round": 1, "original_roster_id": "1"}],
        roster_players=roster_players,
        picks_by_roster=picks_by_roster,
        contender_tier_by_roster={"1": "rebuild", "2": "contender"},
        team_names={"2": "Buyer"},
    )
    assert packages
    assert packages[0]["give"]["picks"]
    assert packages[0]["receive"]["players"] or packages[0]["receive"]["picks"]
