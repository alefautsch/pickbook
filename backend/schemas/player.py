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


class PeakWindow(BaseModel):
    years_to_peak: int | None = None
    peak_window_end: int | None = None


class StatisticalPercentiles(BaseModel):
    hppg_pct: float | None = None
    worp_ppg_pct: float | None = None
    tv_pct: float | None = None


class PlayerOutlook(BaseModel):
    archetype: str | None = None
    peak_window: PeakWindow = Field(default_factory=PeakWindow)
    opportunity_score: float | None = None
    percentiles: StatisticalPercentiles = Field(default_factory=StatisticalPercentiles)


class PlayerLenses(BaseModel):
    flex_rating: int | None = None
    win_now_rating: int | None = None


class PlayerBio(BaseModel):
    height: str | None = None
    weight: str | None = None
    college: str | None = None
    years_exp: int | None = None


class PlayerRanks(BaseModel):
    position_rank: int | None = None
    overall_rank: int | None = None


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
    bio: PlayerBio = Field(default_factory=PlayerBio)
    ranks: PlayerRanks = Field(default_factory=PlayerRanks)

    hppg: float | None = None
    worp_ppg: float | None = None
    availability: float | None = None
    healthy_games: int | None = None
    total_games: int | None = None
    hppg_expected: bool = False
    trade_value: float | None = None
    season_worp: float | None = None
    porp: float | None = None
    injury_status: str | None = None
    injury_body_part: str | None = None
    projected_ppg: float | None = None
    projection_source: str | None = None
    outlook: PlayerOutlook = Field(default_factory=PlayerOutlook)

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
