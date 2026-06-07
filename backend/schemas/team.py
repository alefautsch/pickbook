from __future__ import annotations

from pydantic import BaseModel, Field

from backend.schemas.player import PlayerCard


class LineupSlot(BaseModel):
    slot: str
    player: PlayerCard | None = None


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
    dynasty_rank: int | None = None
    starters: list[LineupSlot] = Field(default_factory=list)
    bench: list[PlayerCard] = Field(default_factory=list)
