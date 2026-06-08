from __future__ import annotations

from pydantic import BaseModel, Field

from backend.schemas.player import DynastyComponents, PlayerCard


class LineupSlot(BaseModel):
    slot: str
    player: PlayerCard | None = None


class TeamTrait(BaseModel):
    label: str
    value: str


class DepthChartPlayer(BaseModel):
    player_id: str
    player_name: str | None = None
    ovr: int | None = None
    depth_rank: int


class DepthChartGroup(BaseModel):
    position: str
    players: list[DepthChartPlayer] = Field(default_factory=list)


class InjuryWatchItem(BaseModel):
    player_id: str
    player_name: str | None = None
    position: str | None = None
    injury_status: str | None = None
    injury_body_part: str | None = None


class DraftPickAsset(BaseModel):
    season: str
    round: int
    original_roster_id: str
    owner_roster_id: str
    slot_tier: str
    trade_value: float | None = None
    label: str | None = None
    is_own_slot: bool = False


class TeamDetail(BaseModel):
    league_id: str
    league_name: str
    roster_id: str
    team_name: str | None = None
    owner: str | None = None
    is_me: bool = False
    avg_dynasty_rating: int | None = None
    starter_avg_dynasty_rating: int | None = None
    starter_total_ppg: float | None = None
    total_trade_value: float | None = None
    draft_pick_value: float | None = None
    dynasty_rank: int | None = None
    starter_ppg_rank: int | None = None
    tv_rank: int | None = None
    win_rank: int | None = None
    contender_tier: str | None = None
    contender_score: float | None = None
    component_breakdown: DynastyComponents = Field(default_factory=DynastyComponents)
    traits: list[TeamTrait] = Field(default_factory=list)
    starters: list[LineupSlot] = Field(default_factory=list)
    bench: list[PlayerCard] = Field(default_factory=list)
    roster: list[PlayerCard] = Field(default_factory=list)
    depth_chart: list[DepthChartGroup] = Field(default_factory=list)
    injuries: list[InjuryWatchItem] = Field(default_factory=list)
    draft_picks: list[DraftPickAsset] = Field(default_factory=list)
