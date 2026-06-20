"""Tests for league trade activity sync and parsing."""

from unittest.mock import MagicMock, patch

from backend.services.trade_activity_service import (
    INITIAL_TRADE_BACKFILL,
    MAX_BACKFILL_WEEKS,
    parse_trade_sides,
    _transaction_context_hash,
    _current_nfl_week,
)


def test_parse_trade_sides_two_team_player_trade():
    txn = {
        "roster_ids": [1, 2],
        "adds": {"p1": 1, "p2": 2},
        "drops": None,
        "draft_picks": [],
    }
    sides = parse_trade_sides(txn)
    assert sides["1"]["receives"]["players"] == ["p1"]
    assert sides["2"]["gives"]["players"] == ["p1"]
    assert sides["2"]["receives"]["players"] == ["p2"]
    assert sides["1"]["gives"]["players"] == ["p2"]


def test_parse_trade_sides_uses_drops_when_present():
    txn = {
        "roster_ids": [3, 4],
        "adds": {"p9": 3},
        "drops": {"p9": 4},
        "draft_picks": [],
    }
    sides = parse_trade_sides(txn)
    assert sides["4"]["gives"]["players"] == ["p9"]
    assert sides["3"]["receives"]["players"] == ["p9"]


def test_parse_trade_sides_pick_only_trade():
    txn = {
        "roster_ids": [1, 2],
        "adds": None,
        "drops": None,
        "draft_picks": [
            {
                "season": "2027",
                "round": 1,
                "roster_id": 1,
                "previous_owner_id": 1,
                "owner_id": 2,
            }
        ],
    }
    sides = parse_trade_sides(txn)
    assert sides["1"]["gives"]["picks"] == [
        {"season": "2027", "round": 1, "original_roster_id": "1"}
    ]
    assert sides["2"]["receives"]["picks"] == [
        {"season": "2027", "round": 1, "original_roster_id": "1"}
    ]


def test_transaction_context_hash_changes_with_sides():
    sides_a = {
        "1": {
            "gives": {"players": ["a"], "picks": []},
            "receives": {"players": [], "picks": []},
        }
    }
    sides_b = {
        "1": {
            "gives": {"players": ["b"], "picks": []},
            "receives": {"players": [], "picks": []},
        }
    }
    h1 = _transaction_context_hash({"transaction_id": "tx1"}, sides_a)
    h2 = _transaction_context_hash({"transaction_id": "tx1"}, sides_b)
    assert h1 != h2


@patch("backend.services.trade_activity_service._fetch_trades_from_sleeper")
def test_sync_backfill_requests_initial_limit(mock_fetch):
    from backend.services.trade_activity_service import sync_league_trades

    db = MagicMock()
    db.scalar.side_effect = lambda *a, **k: 0
    mock_fetch.return_value = [
        {"transaction_id": str(i), "type": "trade", "status": "complete", "created": i, "roster_ids": [1, 2]}
        for i in range(INITIAL_TRADE_BACKFILL)
    ]

    with patch("backend.services.trade_activity_service._upsert_transaction") as mock_upsert:
        mock_upsert.return_value = MagicMock()
        sync_league_trades(db, "league1", client=MagicMock())

    assert mock_fetch.call_args.kwargs["stop_when"] == INITIAL_TRADE_BACKFILL
    db.commit.assert_called_once()


def test_enrich_asset_picks_includes_trade_value():
    from backend.services.trade_activity_service import _enrich_asset_picks

    pick_rows = {
        ("2026", 1, "4"): type(
            "PickRow",
            (),
            {"label": "2026 1.09", "trade_value": 4200.0, "slot_tier": "mid"},
        )(),
    }
    enriched = _enrich_asset_picks(
        [{"season": "2026", "round": 1, "original_roster_id": "4"}],
        pick_rows,
    )
    assert enriched[0]["label"] == "2026 1.09"
    assert enriched[0]["tv"] == 4200.0


def test_current_nfl_week_offseason_uses_full_scan_window():
    from backend.services.trade_activity_service import _current_nfl_week

    client = MagicMock()
    client.get_nfl_state.return_value = {"week": 0, "season_type": "off"}
    assert _current_nfl_week(client) == MAX_BACKFILL_WEEKS
