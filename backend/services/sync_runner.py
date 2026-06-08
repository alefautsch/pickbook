"""Full league sync orchestration — shared by API and CLI (§9.1)."""

from __future__ import annotations

import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models import League
from backend.schemas.sync import SyncAllResponse, SyncLeagueResult
from backend.services.analysis_service import compute_league_rankings
from backend.services.metrics_service import compute_player_snapshots
from backend.services.sync_service import sync_league_from_sleeper
from dynasty_draft.sleeper_client import SleeperClient


def run_full_league_sync(
    db: Session,
    league_id: str,
    *,
    client: SleeperClient | None = None,
    force_refresh: bool = False,
) -> SyncLeagueResult:
    client = client or SleeperClient()
    started = time.perf_counter()

    try:
        ingest = sync_league_from_sleeper(db, league_id, client=client)
        metrics = compute_player_snapshots(
            db,
            league_id,
            client=client,
            sync_run_id=ingest.get("sync_run_id"),
            force_refresh=force_refresh,
        )
        rankings = compute_league_rankings(db, league_id)
        duration_ms = int((time.perf_counter() - started) * 1000)
        return SyncLeagueResult(
            league_id=league_id,
            league_name=ingest.get("league_name"),
            status="success",
            counts=ingest.get("counts") or {},
            duration_ms=duration_ms,
            sync_run_id=ingest.get("sync_run_id"),
            metrics=metrics,
            rankings=rankings,
        )
    except Exception as exc:
        duration_ms = int((time.perf_counter() - started) * 1000)
        return SyncLeagueResult(
            league_id=league_id,
            status="failed",
            duration_ms=duration_ms,
            errors=[str(exc)],
        )


def run_sync_all(
    db: Session,
    *,
    client: SleeperClient | None = None,
    force_refresh: bool = False,
) -> SyncAllResponse:
    client = client or SleeperClient()
    started = time.perf_counter()

    league_ids = list(db.scalars(select(League.sleeper_league_id).order_by(League.name)).all())
    results: list[SyncLeagueResult] = []
    for league_id in league_ids:
        results.append(run_full_league_sync(db, league_id, client=client, force_refresh=force_refresh))

    return SyncAllResponse(
        results=results,
        total_duration_ms=int((time.perf_counter() - started) * 1000),
    )
