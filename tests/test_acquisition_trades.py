"""Targeted stud-acquisition trade packages."""

from backend.services.advisor_tools import (
    ACQUISITION_OVERPAY_BAND,
    generate_acquisition_packages,
    generate_position_acquisition_packages,
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
        "label": kwargs.get("label", f"{season} {rnd}.{orig}"),
        "is_own_slot": orig == kwargs.get("owner_roster_id", orig),
    }


def test_acquire_stud_with_two_firsts_style_picks():
    roster_players = {
        "3": [
            _player("w1", "WR", 5000, hppg=12.0, projected_ppg=12.0, age=24),
            _player("w2", "WR", 2000, hppg=6.0, projected_ppg=6.0, age=26),
        ],
        "4": [
            _player("rb1", "RB", 6500, name="Stud RB", hppg=14.0, projected_ppg=14.0, age=22),
        ],
    }
    picks_by_roster = {
        "3": [
            _pick("2026", 1, "3", 10800, label="2026 1.01"),
            _pick("2026", 2, "3", 3200, label="2026 2.01"),
        ],
        "4": [_pick("2027", 1, "4", 5000, label="2027 1.05")],
    }
    packages = generate_acquisition_packages(
        my_roster_id="3",
        target_player_id="rb1",
        roster_players=roster_players,
        picks_by_roster=picks_by_roster,
        contender_tier_by_roster={"3": "contender", "4": "rebuild"},
        keep_current_first=False,
        lubricant_mode=False,
    )
    assert packages, "expected at least one acquisition package"
    top = packages[0]
    assert top["receive"]["players"][0]["player_id"] == "rb1"
    give_picks = top["give"]["picks"]
    assert len(give_picks) >= 1
    pct = float(top["net_delta_adjusted_pct"])
    assert pct <= ACQUISITION_OVERPAY_BAND * 100 + 1


def test_no_steal_when_target_is_core_without_first():
    roster_players = {
        "3": [_player("w1", "WR", 3000, hppg=10.0, projected_ppg=10.0)],
        "4": [
            _player(
                "rb1",
                "RB",
                9000,
                name="Elite RB",
                hppg=18.0,
                projected_ppg=18.0,
            ),
        ],
    }
    picks_by_roster = {
        "3": [_pick("2026", 3, "3", 1500)],
        "4": [],
    }
    packages = generate_acquisition_packages(
        my_roster_id="3",
        target_player_id="rb1",
        roster_players=roster_players,
        picks_by_roster=picks_by_roster,
        contender_tier_by_roster={"3": "contender", "4": "contender"},
    )
    assert packages == []


def test_league_rb_scan_returns_packages_per_target():
    roster_players = {
        "3": [_player("w1", "WR", 5000, hppg=12.0, projected_ppg=12.0)],
        "4": [
            _player("rb1", "RB", 6500, name="Stud A", hppg=14.0, projected_ppg=14.0, age=23),
        ],
        "5": [
            _player("rb2", "RB", 6000, name="Stud B", hppg=13.0, projected_ppg=13.0, age=24),
        ],
    }
    picks_by_roster = {
        "3": [
            _pick("2026", 1, "3", 10800, label="2026 1.01"),
            _pick("2026", 2, "3", 3200, label="2026 2.01"),
            _pick("2027", 1, "3", 6500, label="2027 1.10"),
        ],
        "4": [],
        "5": [],
    }
    packages = generate_position_acquisition_packages(
        my_roster_id="3",
        target_position="RB",
        roster_players=roster_players,
        picks_by_roster=picks_by_roster,
        contender_tier_by_roster={"3": "contender", "4": "rebuild", "5": "competitive"},
        team_names={"4": "Team A", "5": "Team B"},
        max_suggestions=5,
    )
    assert len(packages) >= 1
    names = {
        (p.get("counterparty") or {}).get("target_player_name") for p in packages
    }
    assert "Stud A" in names or "Stud B" in names
