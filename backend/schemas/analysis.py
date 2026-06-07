from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ContenderInputs(BaseModel):
    starter_avg_ovr: int | None = None
    starter_total_ppg: float | None = None
    age_depth_score: float | None = None
    starter_ovr_norm: float | None = None
    starter_ppg_norm: float | None = None
    age_depth_norm: float | None = None


class ContenderTeam(BaseModel):
    roster_id: str
    team_name: str | None = None
    is_me: bool = False
    tier: str
    composite_score: float
    contender_rank: int
    inputs: ContenderInputs


class ContenderIndex(BaseModel):
    weights: dict[str, float]
    teams: list[ContenderTeam] = Field(default_factory=list)


class PositionStrengthTeam(BaseModel):
    roster_id: str
    team_name: str | None = None
    is_me: bool = False
    by_position: dict[str, float | None] = Field(default_factory=dict)


class PositionStrengthMap(BaseModel):
    positions: list[str] = Field(default_factory=list)
    teams: list[PositionStrengthTeam] = Field(default_factory=list)


class AgeProfile(BaseModel):
    roster_id: str
    team_name: str | None = None
    is_me: bool = False
    starter_avg_age: float | None = None
    bench_avg_age: float | None = None
    league_avg_starter_age: float | None = None
    age_delta: float | None = None
    window: str | None = None
    starter_ages: list[dict[str, Any]] = Field(default_factory=list)


class TradeSurplusItem(BaseModel):
    position: str
    avg_ovr: float | None = None
    league_rank: int
    league_size: int


class TradeCounterparty(BaseModel):
    position: str
    direction: str
    roster_id: str
    team_name: str | None = None
    my_rank: int
    their_rank: int
    their_avg_ovr: float | None = None


class TradeSurplus(BaseModel):
    roster_id: str
    team_name: str | None = None
    surplus: list[TradeSurplusItem] = Field(default_factory=list)
    needs: list[TradeSurplusItem] = Field(default_factory=list)
    counterparties: list[TradeCounterparty] = Field(default_factory=list)


class LeagueAnalysis(BaseModel):
    league_id: str
    league_name: str
    computed_at: datetime | None = None
    contender_index: ContenderIndex | None = None
    position_strength: PositionStrengthMap | None = None
    age_profiles: list[AgeProfile] = Field(default_factory=list)
    trade_surplus: TradeSurplus | None = None
