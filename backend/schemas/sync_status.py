from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class LeagueSyncStatus(BaseModel):
    league_id: str
    league_name: str | None = None
    last_synced: datetime | None = None
    last_status: str | None = None
    last_error: str | None = None


class SyncStatusResponse(BaseModel):
    last_success_at: datetime | None = None
    last_failure_at: datetime | None = None
    has_recent_failure: bool = False
    sync_cron: str | None = None
    leagues: list[LeagueSyncStatus] = Field(default_factory=list)
