from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class LeagueTile(BaseModel):
    league_id: str
    name: str
    season: str
    total_rosters: int
    superflex: bool
    my_roster_id: str | None = None
    my_team_name: str | None = None
    my_dynasty_rank: int | None = None
    my_roster_ovr: int | None = None
    my_starter_ppg: float | None = None
    my_total_trade_value: float | None = None
    my_starter_ppg_rank: int | None = None
    my_tv_rank: int | None = None
    my_contender_tier: str | None = None
    my_contender_score: float | None = None
    my_roster_ovr_delta: int | None = None
    last_synced: datetime | None = None


class LeagueTeamSummary(BaseModel):
    roster_id: str
    team_name: str | None = None
    owner: str | None = None
    is_me: bool = False
    avg_dynasty_rating: int | None = None
    starter_total_ppg: float | None = None
    total_trade_value: float | None = None
    dynasty_rank: int | None = None
    starter_ppg_rank: int | None = None
    tv_rank: int | None = None
    win_rank: int | None = None
    contender_tier: str | None = None
    contender_rank: int | None = None
    contender_score: float | None = None


class LeagueDetail(BaseModel):
    league_id: str
    name: str
    season: str
    total_rosters: int
    superflex: bool
    last_synced: datetime | None = None
    teams: list[LeagueTeamSummary] = Field(default_factory=list)


class LeagueRankings(BaseModel):
    league_id: str
    league_name: str
    computed_at: datetime | None = None
    by_dynasty: list[dict[str, Any]] = Field(default_factory=list)
    by_starter_ppg: list[dict[str, Any]] = Field(default_factory=list)
    by_tv: list[dict[str, Any]] = Field(default_factory=list)
    by_win_now: list[dict[str, Any]] = Field(default_factory=list)
