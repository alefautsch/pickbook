from __future__ import annotations

from pydantic import BaseModel, Field


class PortfolioLeagueHolding(BaseModel):
    league_id: str
    league_name: str
    ovr: int | None = None
    tier: str | None = None
    team_name: str | None = None


class PortfolioPlayer(BaseModel):
    player_id: str
    player_name: str | None = None
    position: str | None = None
    nfl_team: str | None = None
    age: int | None = None
    headshot_url: str
    league_count: int
    leagues: list[PortfolioLeagueHolding] = Field(default_factory=list)
    exposure_flag: str | None = None


class PositionExposure(BaseModel):
    position: str
    holding_count: int
    unique_players: int


class PortfolioSummary(BaseModel):
    total_leagues: int
    unique_players: int
    multi_league_count: int
    holdings: list[PortfolioPlayer] = Field(default_factory=list)
    by_position: list[PositionExposure] = Field(default_factory=list)


class PlayerSearchLeagueMatch(BaseModel):
    league_id: str
    league_name: str
    ovr: int | None = None
    tier: str | None = None
    is_owned: bool = False


class PlayerSearchHit(BaseModel):
    player_id: str
    player_name: str | None = None
    position: str | None = None
    nfl_team: str | None = None
    headshot_url: str
    leagues: list[PlayerSearchLeagueMatch] = Field(default_factory=list)


class PlayerSearchResults(BaseModel):
    query: str
    hits: list[PlayerSearchHit] = Field(default_factory=list)


class PlayerHoldings(BaseModel):
    player_id: str
    player_name: str | None = None
    position: str | None = None
    leagues: list[PortfolioLeagueHolding] = Field(default_factory=list)
