"""Tests for Sleeper league sync helpers."""

from backend.services.sync_service import _unique_player_ids


def test_unique_player_ids_dedupes_while_preserving_order():
    assert _unique_player_ids(["10219", "11655", "10219", "12510"]) == [
        "10219",
        "11655",
        "12510",
    ]
