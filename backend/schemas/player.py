from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class DynastyComponents(BaseModel):
    tv: float | None = None
    worp: float | None = None
    per_game: float | None = None
    upside: float | None = None
    age: float | None = None
    trajectory: float | None = None


class PlayerLenses(BaseModel):
    flex_rating: int | None = None
    win_now_rating: int | None = None


class PlayerCard(BaseModel):
    """Pre-shaped player DTO for cards and detail views (§11)."""

    player_id: str
    player_name: str | None = None
    position: str | None = None
    nfl_team: str | None = None
    age: int | None = None

    ovr: int | None = None
    tier: str | None = None
    dynasty_rookie: bool = False
    components: DynastyComponents = Field(default_factory=DynastyComponents)
    lenses: PlayerLenses = Field(default_factory=PlayerLenses)

    hppg: float | None = None
    worp_ppg: float | None = None
    availability: float | None = None
    hppg_expected: bool = False
    trade_value: float | None = None

    headshot_url: str
    league_id: str
    league_name: str
    computed_at: datetime | None = None


class PlayerHistoryPoint(BaseModel):
    computed_at: datetime
    ovr: int | None = None
    ovr_original: int | None = None
    ovr_recomputed: int | None = None
    formula_version: str
    recomputed_formula_version: str | None = None
    dynasty_score: float | None = None
    hppg: float | None = None
    worp_ppg: float | None = None
    availability: float | None = None
    trade_value: float | None = None
    components: DynastyComponents = Field(default_factory=DynastyComponents)


class PlayerHistorySeries(BaseModel):
    player_id: str
    league_id: str
    current_formula_version: str
    points: list[PlayerHistoryPoint] = Field(default_factory=list)
