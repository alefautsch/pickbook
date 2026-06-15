"""Tests for 2026 rookie pick projection in trade context."""

from backend.services.trade_rookie_context import (
    append_pick_context_to_reasoning,
    build_deal_rookie_context,
    build_trade_rookie_context,
    format_pick_projection_blurb,
    parse_pick_slot_from_label,
    pick_no_for_slot,
)


def test_parse_pick_slot_from_label():
    assert parse_pick_slot_from_label("2026 1.04") == (1, 4)
    assert parse_pick_slot_from_label("1.04") == (1, 4)
    assert parse_pick_slot_from_label("2026 1.01") == (1, 1)
    assert parse_pick_slot_from_label("2027 Early 1st") is None


def test_pick_no_for_slot_round_one():
    assert pick_no_for_slot(
        round_no=1, slot_in_round=4, teams=12, rounds=4, draft_type="snake"
    ) == 4
    assert pick_no_for_slot(
        round_no=1, slot_in_round=1, teams=12, rounds=4, draft_type="snake"
    ) == 1


def test_pick_no_for_slot_snake_round_two():
    # 12-team snake: 2.01 is pick 13, slot 12
    assert pick_no_for_slot(
        round_no=2, slot_in_round=12, teams=12, rounds=4, draft_type="snake"
    ) == 13


def test_build_trade_rookie_context_shapes_picks(monkeypatch):
    class FakeState:
        draft = {"season": "2026", "status": "pre_draft", "type": "snake"}

        def _teams(self):
            return 12

        def _rounds(self):
            return 4

        picks = []

        def _adp_index(self):
            class Adp:
                def pick_no(self, name: str) -> int | None:
                    mapping = {
                        "Jeremiyah Love": 1,
                        "Makai Lemon": 4,
                        "Kenyon Sadiq": 6,
                    }
                    return mapping.get(name)

            return Adp()

        def bpa_recommendations(self, limit: int = 15):
            return [
                {
                    "name": "Jeremiyah Love",
                    "pos": "RB",
                    "dynasty_rating": 88,
                    "adp_pick": 1,
                    "bpa_rank": 1,
                }
            ][:limit]

    class FakeLeague:
        season = "2026"
        scoring_json = {"bonus_rec_te": 0.5}

    monkeypatch.setattr(
        "backend.services.trade_rookie_context.load_rookie_draft_state_for_league",
        lambda db, league_id: (FakeState(), FakeLeague()),
    )

    ctx = build_trade_rookie_context(
        None,  # type: ignore[arg-type]
        "lg1",
        review_team={
            "team_name": "Buyer",
            "needs": [{"position": "RB"}],
            "starter_needs": {"RB": 1},
        },
        other_team={"team_name": "Seller", "needs": []},
        review_acquires_picks=[
            {"season": "2026", "round": 1, "label": "2026 1.01", "trade_value": 10800},
        ],
        review_gives_picks=[
            {"season": "2026", "round": 1, "label": "2026 1.04", "trade_value": 7200},
            {"season": "2026", "round": 1, "label": "2026 1.06", "trade_value": 6500},
        ],
    )

    assert ctx is not None
    assert ctx["season"] == "2026"
    assert ctx["te_premium"] == 0.5
    assert len(ctx["picks_in_trade"]) == 3

    acquired = next(row for row in ctx["picks_in_trade"] if row["label"] == "2026 1.01")
    assert acquired["acquired_by"] == "Buyer"
    assert acquired["projected_rookie"]["name"] == "Jeremiyah Love"
    assert acquired.get("consensus_note")
    assert acquired["fills_need_for_acquirer"] is True

    gave_up = next(row for row in ctx["picks_in_trade"] if row["label"] == "2026 1.06")
    assert gave_up["acquired_by"] == "Seller"
    range_names = [r["name"] for r in gave_up.get("likely_range") or []]
    assert "Kenyon Sadiq" in range_names
    assert "Ty Simpson" not in range_names
    assert gave_up.get("tep_note")


def test_build_trade_rookie_context_falls_back_to_numbered_rookie_board(monkeypatch):
    class FakeLeague:
        season = "2026"
        total_rosters = 12
        scoring_json = {"bonus_rec_te": 0.5}

    class FakeDb:
        def get(self, model, league_id):
            return FakeLeague()

    board = [
        {"name": "Jeremiyah Love", "pos": "RB", "trade_value": 7655, "bpa_rank": 1},
        {"name": "Carnell Tate", "pos": "WR", "trade_value": 4397, "bpa_rank": 2},
        {"name": "Fernando Mendoza", "pos": "QB", "trade_value": 3638, "bpa_rank": 3},
        {"name": "Makai Lemon", "pos": "WR", "trade_value": 3222, "bpa_rank": 4},
        {"name": "Jordyn Tyson", "pos": "WR", "trade_value": 3177, "bpa_rank": 5},
        {"name": "Kenyon Sadiq", "pos": "TE", "trade_value": 2468, "bpa_rank": 6},
    ]

    monkeypatch.setattr(
        "backend.services.trade_rookie_context.load_rookie_draft_state_for_league",
        lambda db, league_id: None,
    )
    monkeypatch.setattr(
        "backend.services.trade_rookie_context._build_consensus_rookie_board",
        lambda **kwargs: [
            {
                **row,
                "adp_pick": idx,
            }
            for idx, row in enumerate(board, start=1)
        ],
    )

    ctx = build_trade_rookie_context(
        FakeDb(),  # type: ignore[arg-type]
        "lg1",
        review_team={"team_name": "Buyer", "needs": [{"position": "RB"}]},
        other_team={"team_name": "Seller", "needs": []},
        review_acquires_picks=[
            {"season": "2026", "round": 1, "label": "2026 1.01", "trade_value": 10800},
        ],
        review_gives_picks=[
            {"season": "2026", "round": 1, "label": "2026 1.04", "trade_value": 7200},
            {"season": "2026", "round": 1, "label": "2026 1.06", "trade_value": 6500},
        ],
    )

    assert ctx is not None
    assert ctx["draft_status"] is None
    one_one = next(row for row in ctx["picks_in_trade"] if row["label"] == "2026 1.01")
    assert one_one["projected_rookie"]["name"] == "Jeremiyah Love"
    one_four = next(row for row in ctx["picks_in_trade"] if row["label"] == "2026 1.04")
    assert one_four["projected_rookie"]["name"] == "Makai Lemon"
    range_names = [r["name"] for r in one_four.get("likely_range") or []]
    assert "Makai Lemon" in range_names
    assert "Fernando Mendoza" in range_names


def test_build_deal_rookie_context_neutral_sides(monkeypatch):
    class FakeState:
        draft = {"season": "2026", "status": "pre_draft", "type": "snake"}

        def _teams(self):
            return 12

        def _rounds(self):
            return 4

        picks = []

        def _adp_index(self):
            return type("Adp", (), {"pick_no": lambda self, name: None})()

        def bpa_recommendations(self, limit: int = 15):
            return []

    class FakeLeague:
        season = "2026"
        scoring_json = {}

    monkeypatch.setattr(
        "backend.services.trade_rookie_context.load_rookie_draft_state_for_league",
        lambda db, league_id: (FakeState(), FakeLeague()),
    )

    ctx = build_deal_rookie_context(
        None,  # type: ignore[arg-type]
        "lg1",
        side_a_team={"team_name": "Team A"},
        side_b_team={"team_name": "Team B"},
        side_a_gives_picks=[{"season": "2026", "round": 1, "label": "2026 1.01"}],
        side_b_gives_picks=[{"season": "2026", "round": 1, "label": "2026 1.04"}],
    )

    assert ctx is not None
    assert len(ctx["picks_in_trade"]) == 2
    one_one = next(r for r in ctx["picks_in_trade"] if r["label"] == "2026 1.01")
    assert one_one["given_by"] == "Team A"
    assert one_one["acquired_by"] == "Team B"
    assert one_one["projected_rookie"]["name"] == "Jeremiyah Love"


def test_append_pick_context_to_reasoning():
    ctx = {
        "picks_in_trade": [
            {
                "label": "2026 1.01",
                "projected_rookie": {"name": "Jeremiyah Love", "pos": "RB"},
            }
        ]
    }
    assert append_pick_context_to_reasoning("Team wants win-now RB.", ctx) == (
        "Team wants win-now RB. Pick ranges: 2026 1.01 → Jeremiyah Love (RB)."
    )
    assert append_pick_context_to_reasoning(
        "Moving up for Jeremiyah Love at 1.01.", ctx
    ) == "Moving up for Jeremiyah Love at 1.01."
    assert format_pick_projection_blurb(ctx) == (
        "Pick ranges: 2026 1.01 → Jeremiyah Love (RB)."
    )
