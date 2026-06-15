"""Snapshot OVR overlay — rookie draft must match player_snapshots (§5.7)."""

from backend.services.read_service import apply_snapshot_dynasty


def test_apply_snapshot_dynasty_overlays_rating_and_rookie_flag():
    by_id = {"123": (88, True)}
    row = {"player_id": "123", "dynasty_rating": 72, "dynasty_rookie": False}
    apply_snapshot_dynasty(row, by_id)
    assert row["dynasty_rating"] == 88
    assert row["dynasty_rookie"] is True


def test_apply_snapshot_dynasty_skips_unknown_players():
    row = {"player_id": "999", "dynasty_rating": 72}
    apply_snapshot_dynasty(row, {"123": (88, True)})
    assert row["dynasty_rating"] == 72


def test_apply_snapshot_dynasty_skips_rows_without_player_id():
    row = {"dynasty_rating": 72}
    apply_snapshot_dynasty(row, {"123": (88, True)})
    assert row["dynasty_rating"] == 72
