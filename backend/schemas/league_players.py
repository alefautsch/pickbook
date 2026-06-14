from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class LeaguePlayerRow(BaseModel):
    player_id: str
    player_name: str | None = None
    position: str | None = None
    nfl_team: str | None = None
    age: int | None = None
    ovr: int | None = None
    tier: str | None = None
    dynasty_rookie: bool = False
    hppg: float | None = None
    projected_ppg: float | None = None
    worp_ppg: float | None = None
    trade_value: float | None = None
    hppg_expected: bool = False
    availability: float | None = None
    healthy_games: int | None = None
    total_games: int | None = None
    season_worp: float | None = None
    flex_rating: int | None = None
    porp: float | None = None
    projection_source: str | None = None
    headshot_url: str
    is_free_agent: bool = False
    roster_team_name: str | None = None
    roster_id: str | None = None


class LeaguePlayerDirectory(BaseModel):
    league_id: str
    league_name: str
    total_players: int
    computed_at: datetime | None = None
    players: list[LeaguePlayerRow] = Field(default_factory=list)
