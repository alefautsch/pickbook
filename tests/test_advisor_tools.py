"""Tests for advisor tool math and trade suggestion generation."""

from backend.services.advisor_tools import (
    evaluate_trade_package,
    generate_trade_suggestions,
    safe_calculate,
)


def _player(pid: str, name: str, pos: str, tv: float, **kwargs) -> dict:
    return {
        "player_id": pid,
        "name": name,
        "position": pos,
        "tv": tv,
        **kwargs,
    }


def _pick(season: str, round_no: int, original: str, tv: float, **kwargs) -> dict:
    return {
        "season": season,
        "round": round_no,
        "original_roster_id": original,
        "trade_value": tv,
        "label": f"{season} {round_no}",
        "is_own_slot": kwargs.get("is_own_slot", True),
        "slot_tier": kwargs.get("slot_tier", "late"),
        **kwargs,
    }


def test_safe_calculate_basic():
    assert safe_calculate("1200 + 800") == 2000.0
    assert safe_calculate("(4500 * 2) / 3") == 3000.0


def test_evaluate_trade_players_and_picks():
    players = {
        "p1": _player("p1", "Alpha WR", "WR", 5000),
        "p2": _player("p2", "Beta RB", "RB", 4800),
        "p3": _player("p3", "Gamma TE", "TE", 3200),
    }
    picks = {
        ("2027", 1, "9"): _pick("2027", 1, "9", 6200),
        ("2028", 2, "3"): _pick("2028", 2, "3", 2000),
    }

    def resolve_player(pid: str):
        return players.get(pid)

    def resolve_pick(pick: dict):
        return picks.get((pick["season"], pick["round"], pick["original_roster_id"]))

    result = evaluate_trade_package(
        {
            "players": ["p1"],
            "picks": [{"season": "2027", "round": 1, "original_roster_id": "9"}],
        },
        {"players": ["p2", "p3"]},
        resolve_player=resolve_player,
        resolve_pick=resolve_pick,
    )

    assert result["give_total_tv"] == 11200.0
    assert result["receive_total_tv"] == 8000.0
    assert result["net_delta_tv"] == -3200.0
    assert result["give_effective_tv"] < result["give_total_tv"]
    assert result["receive_effective_tv"] < result["receive_total_tv"]
    assert result["fairness"] == "favors_counterparty"
    assert result["within_band"] is False
    assert result["missing_assets"] == []
    assert any("WR" in note for note in result["positional_notes"])


def test_evaluate_trade_missing_assets():
    result = evaluate_trade_package(
        {"players": ["missing"], "picks": []},
        {"players": [], "picks": []},
        resolve_player=lambda _pid: None,
        resolve_pick=lambda _pick: None,
    )
    assert "player:missing" in result["missing_assets"]


def test_generate_trade_suggestions_from_surplus():
    trade_surplus = {
        "surplus": [{"position": "WR", "league_rank": 1}],
        "needs": [{"position": "RB", "league_rank": 10}],
        "counterparties": [
            {
                "roster_id": "2",
                "team_name": "Rival FC",
                "position": "WR",
                "direction": "sell",
                "my_rank": 1,
                "their_rank": 10,
            },
            {
                "roster_id": "3",
                "team_name": "Rebuilders",
                "position": "RB",
                "direction": "buy",
                "my_rank": 10,
                "their_rank": 2,
            },
        ],
    }
    roster_players = {
        "1": [
            _player("w1", "Stud WR", "WR", 7000, hppg=16.0),
            _player("w2", "Depth WR", "WR", 4200, hppg=5.0, age=27),
            _player("r1", "Slim RB", "RB", 3000, hppg=4.0, age=28),
        ],
        "2": [
            _player("r2", "Needy RB", "RB", 5500),
            _player("r3", "Bench RB", "RB", 3800),
            _player("t1", "Block TE", "TE", 2500),
        ],
        "3": [
            _player("r4", "Elite RB", "RB", 6800),
            _player("r5", "RB2", "RB", 4500),
            _player("w3", "Need WR", "WR", 3600),
        ],
    }
    picks_by_roster = {
        "1": [_pick("2027", 2, "1", 2400)],
        "2": [],
        "3": [_pick("2027", 1, "3", 4200)],
    }

    packages = generate_trade_suggestions(
        my_roster_id="1",
        trade_surplus=trade_surplus,
        roster_players=roster_players,
        picks_by_roster=picks_by_roster,
    )

    assert 1 <= len(packages) <= 5
    assert packages[0]["counterparty"]["team_name"] in {"Rival FC", "Rebuilders"}
    assert packages[0]["give"]["players"] or packages[0]["give"]["picks"]
    assert packages[0]["receive"]["players"] or packages[0]["receive"]["picks"]
    assert "give_total_tv" in packages[0]
    assert "give_effective_tv" in packages[0]
    assert "package_quality" in packages[0]
    assert "fairness" in packages[0]


def test_generate_trade_suggestions_target_roster_filter():
    trade_surplus = {
        "surplus": [{"position": "WR", "league_rank": 1}],
        "needs": [{"position": "RB", "league_rank": 10}],
        "counterparties": [
            {
                "roster_id": "2",
                "team_name": "Target",
                "position": "WR",
                "direction": "sell",
                "my_rank": 1,
                "their_rank": 9,
            },
            {
                "roster_id": "9",
                "team_name": "Other",
                "position": "WR",
                "direction": "sell",
                "my_rank": 1,
                "their_rank": 8,
            },
        ],
    }
    roster_players = {
        "1": [
            _player("w1", "Stud WR", "WR", 7000, hppg=16.0),
            _player("w2", "Depth WR", "WR", 4200, hppg=5.5, age=27),
            _player("w3", "Bench WR", "WR", 1200, hppg=5.0, age=28),
            _player("w4", "Deep WR", "WR", 900, hppg=4.5, age=29),
        ],
        "2": [
            _player("r2a", "Stud RB", "RB", 6200, hppg=14.0, age=25),
            _player("r2", "Needy RB", "RB", 5000, hppg=8.0, age=26),
        ],
        "9": [
            _player("r9a", "Stud RB9", "RB", 6400, hppg=14.0, age=25),
            _player("r9", "RB9", "RB", 5100, hppg=8.0, age=26),
        ],
    }

    packages = generate_trade_suggestions(
        my_roster_id="1",
        trade_surplus=trade_surplus,
        roster_players=roster_players,
        picks_by_roster={"1": [], "2": [], "9": []},
        target_roster_id="2",
        contender_tier_by_roster={"1": "contender", "2": "rebuild", "9": "rebuild"},
    )

    assert packages
    assert all(p["counterparty"]["roster_id"] == "2" for p in packages)
