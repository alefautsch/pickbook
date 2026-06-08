from datetime import datetime, timezone

from backend.services.scheduler_service import next_scheduled_run


def test_next_scheduled_run_uses_utc_daily_schedule():
    now = datetime(2026, 6, 8, 4, 30, tzinfo=timezone.utc)

    next_run = next_scheduled_run("0 11 * * *", now=now)

    assert next_run == datetime(2026, 6, 8, 11, 0, tzinfo=timezone.utc)


def test_next_scheduled_run_supports_comma_hour_list():
    now = datetime(2026, 6, 8, 12, 0, tzinfo=timezone.utc)

    next_run = next_scheduled_run("0 11,23 * * *", now=now)

    assert next_run == datetime(2026, 6, 8, 23, 0, tzinfo=timezone.utc)
