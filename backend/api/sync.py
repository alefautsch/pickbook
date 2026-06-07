from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.db.models import League, SyncRun
from backend.db.session import get_db
from backend.schemas.sync import SyncAllResponse, SyncLeagueResult
from backend.schemas.sync_status import LeagueSyncStatus, SyncStatusResponse
from backend.services.sync_runner import run_full_league_sync, run_sync_all

router = APIRouter(prefix="/sync", tags=["sync"])


@router.get("/status", response_model=SyncStatusResponse)
def sync_status(db: Session = Depends(get_db)) -> SyncStatusResponse:
    settings = get_settings()
    leagues = db.scalars(select(League).order_by(League.name)).all()

    last_success = db.scalar(
        select(SyncRun.finished_at)
        .where(SyncRun.status == "success", SyncRun.finished_at.is_not(None))
        .order_by(desc(SyncRun.finished_at))
        .limit(1)
    )
    last_failure = db.scalar(
        select(SyncRun.finished_at)
        .where(SyncRun.status == "failed", SyncRun.finished_at.is_not(None))
        .order_by(desc(SyncRun.finished_at))
        .limit(1)
    )
    has_recent_failure = bool(
        last_failure and (last_success is None or last_failure > last_success)
    )

    league_statuses: list[LeagueSyncStatus] = []
    for league in leagues:
        run = db.scalar(
            select(SyncRun)
            .where(SyncRun.league_id == league.sleeper_league_id)
            .order_by(desc(SyncRun.started_at))
            .limit(1)
        )
        last_error = None
        if run and run.status == "failed" and run.errors_json:
            last_error = str(run.errors_json[0]) if run.errors_json else None
        league_statuses.append(
            LeagueSyncStatus(
                league_id=league.sleeper_league_id,
                league_name=league.name,
                last_synced=run.finished_at if run and run.status == "success" else None,
                last_status=run.status if run else None,
                last_error=last_error,
            )
        )

    return SyncStatusResponse(
        last_success_at=last_success,
        last_failure_at=last_failure,
        has_recent_failure=has_recent_failure,
        sync_cron=settings.sync_cron if settings.sync_enabled else None,
        leagues=league_statuses,
    )


@router.post("/{league_id}", response_model=SyncLeagueResult)
def sync_one_league(league_id: str, db: Session = Depends(get_db)) -> SyncLeagueResult:
    result = run_full_league_sync(db, league_id)
    if result.status == "failed":
        raise HTTPException(status_code=500, detail=result.errors)
    return result


@router.post("", response_model=SyncAllResponse)
def sync_all(db: Session = Depends(get_db)) -> SyncAllResponse:
    return run_sync_all(db)
