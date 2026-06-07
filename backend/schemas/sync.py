from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SyncLeagueResult(BaseModel):
    league_id: str
    league_name: str | None = None
    status: str
    counts: dict[str, int] = Field(default_factory=dict)
    duration_ms: int | None = None
    sync_run_id: int | None = None
    metrics: dict[str, Any] | None = None
    rankings: dict[str, Any] | None = None
    errors: list[str] = Field(default_factory=list)


class SyncAllResponse(BaseModel):
    results: list[SyncLeagueResult]
    total_duration_ms: int | None = None
