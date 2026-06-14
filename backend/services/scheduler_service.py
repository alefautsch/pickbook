"""In-process scheduled sync for the Blackbook API."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from croniter import croniter
from sqlalchemy.engine import Connection
from sqlalchemy import text

from backend.config import Settings
from backend.db.session import SessionLocal, engine
from backend.services.sync_runner import run_sync_all

LOGGER = logging.getLogger(__name__)
SYNC_ADVISORY_LOCK_ID = 2026060801
MAX_SLEEP_SECONDS = 60 * 60


def next_scheduled_run(cron_expr: str, *, now: datetime | None = None) -> datetime:
    """Return the next UTC run time for a five-field cron expression."""
    base = now or datetime.now(timezone.utc)
    if base.tzinfo is None:
        base = base.replace(tzinfo=timezone.utc)
    return croniter(cron_expr, base).get_next(datetime).astimezone(timezone.utc)


def _try_sync_lock(connection: Connection) -> bool:
    locked = connection.execute(
        text("SELECT pg_try_advisory_lock(:lock_id)"),
        {"lock_id": SYNC_ADVISORY_LOCK_ID},
    ).scalar_one()
    return bool(locked)


def _release_sync_lock(connection: Connection) -> None:
    connection.execute(
        text("SELECT pg_advisory_unlock(:lock_id)"),
        {"lock_id": SYNC_ADVISORY_LOCK_ID},
    )


def run_scheduled_sync_once() -> None:
    """Run all-league sync if this process wins the Postgres advisory lock."""
    lock_connection = engine.connect()
    lock_acquired = False
    try:
        lock_acquired = _try_sync_lock(lock_connection)
        if not lock_acquired:
            LOGGER.info("scheduled sync skipped; advisory lock held elsewhere")
            return

        db = SessionLocal()
        try:
            result = run_sync_all(db, force_refresh=True)
            failures = [row for row in result.results if row.status != "success"]
            if failures:
                LOGGER.warning("scheduled sync completed with %d failures", len(failures))
            else:
                LOGGER.info("scheduled sync completed successfully")
        finally:
            db.close()
    except Exception:
        LOGGER.exception("scheduled sync crashed")
    finally:
        if lock_acquired:
            try:
                _release_sync_lock(lock_connection)
            except Exception:
                LOGGER.exception("failed to release scheduled sync advisory lock")
        lock_connection.close()


async def _sleep_until(target: datetime, stop_event: asyncio.Event) -> bool:
    """Sleep until target; return False if stopped before target."""
    while True:
        remaining = (target - datetime.now(timezone.utc)).total_seconds()
        if remaining <= 0:
            return True
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=min(remaining, MAX_SLEEP_SECONDS))
            return False
        except TimeoutError:
            continue


async def scheduled_sync_loop(settings: Settings, stop_event: asyncio.Event) -> None:
    if not settings.sync_enabled:
        LOGGER.info("scheduled sync disabled")
        return

    cron_expr = settings.sync_cron.strip()
    if not cron_expr:
        LOGGER.info("scheduled sync disabled; no cron expression configured")
        return

    try:
        next_run = next_scheduled_run(cron_expr)
    except Exception:
        LOGGER.exception("invalid SYNC_CRON expression: %s", cron_expr)
        return

    LOGGER.info("scheduled sync enabled: %s; next run %s", cron_expr, next_run.isoformat())
    while not stop_event.is_set():
        should_run = await _sleep_until(next_run, stop_event)
        if not should_run:
            break

        await asyncio.to_thread(run_scheduled_sync_once)

        try:
            next_run = next_scheduled_run(cron_expr)
            LOGGER.info("next scheduled sync run %s", next_run.isoformat())
        except Exception:
            LOGGER.exception("invalid SYNC_CRON expression after scheduled run: %s", cron_expr)
            break
