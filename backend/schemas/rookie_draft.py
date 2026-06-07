from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class RookieDraftOnClock(BaseModel):
    roster_id: str | None = None
    team_name: str | None = None
    draft_slot: int | None = None
    is_me: bool = False


class RookieDraftNextPickInfo(BaseModel):
    pick_no: int | None = None
    round: int | None = None
    slot: int | None = None
    is_my_pick: bool = False
    picks_until_mine: int | None = None
    total_picks: int | None = None
    back_to_back: bool = False
    consecutive_picks: list[int] = Field(default_factory=list)


class StarterNeeds(BaseModel):
    QB: int = 0
    RB: int = 0
    WR: int = 0
    TE: int = 0
    FLEX: int = 0


class RookieBoardRow(BaseModel):
    bpa_rank: int
    player_id: str
    player_name: str | None = None
    position: str | None = None
    nfl_team: str | None = None
    age: int | None = None
    ovr: int | None = None
    tier: str | None = None
    dynasty_rookie: bool = False
    trade_value: float | None = None
    projected_ppg: float | None = None
    hppg: float | None = None
    worp_ppg: float | None = None
    hppg_expected: bool = False
    flex_rating: int | None = None
    adp_pick: int | None = None
    adp_delta: int | None = None
    adp_class: str | None = None
    bpa_score: float | None = None
    vor: float | None = None
    headshot_url: str


class RookieDraftTimelineRow(BaseModel):
    pick_no: int
    round: int | None = None
    team_name: str | None = None
    player_id: str | None = None
    player_name: str | None = None
    position: str | None = None
    ovr: int | None = None
    dynasty_rookie: bool = False
    status: str
    is_me: bool = False


class RookieDraftView(BaseModel):
    league_id: str
    league_name: str
    draft_id: str
    draft_status: str | None = None
    picks_made: int = 0
    total_picks: int = 0
    next_pick_no: int | None = None
    on_clock: RookieDraftOnClock
    my_roster_id: str | None = None
    drafting_roster_id: str | None = None
    drafting_team_name: str | None = None
    is_my_pick: bool = False
    next_pick_info: RookieDraftNextPickInfo
    starter_needs: StarterNeeds
    board: list[RookieBoardRow]
    bpa_top: list[RookieBoardRow]
    timeline: list[RookieDraftTimelineRow]
    strategy_notes: list[str] = Field(default_factory=list)
    adp_source: str | None = None
    fetched_at: datetime
    poll_seconds: int = 20
