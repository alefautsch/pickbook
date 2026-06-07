from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class FreeAgentRow(BaseModel):
    player_id: str
    player_name: str | None = None
    position: str | None = None
    nfl_team: str | None = None
    age: int | None = None
    ovr: int | None = None
    tier: str | None = None
    hppg: float | None = None
    worp_ppg: float | None = None
    trade_value: float | None = None
    hppg_expected: bool = False
    headshot_url: str
    league_id: str
    league_name: str
    computed_at: datetime | None = None


class FreeAgentBoard(BaseModel):
    league_id: str
    league_name: str
    superflex: bool
    position_filter: str | None = None
    fa_pool_size: int
    total_available: int
    players: list[FreeAgentRow] = Field(default_factory=list)
