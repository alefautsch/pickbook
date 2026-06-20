from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from backend.schemas.trade import TradeAssetPick, TradeAssetPlayer, TradeSideValidation


class TradeActivitySide(BaseModel):
    roster_id: str
    team_name: str | None = None
    gives: dict[str, list[Any]] = Field(default_factory=dict)
    receives: dict[str, list[Any]] = Field(default_factory=dict)


class TradeActivityAnalysis(BaseModel):
    side_a: TradeSideValidation | None = None
    side_b: TradeSideValidation | None = None
    overall_grade: str | None = None
    summary: str | None = None
    tv_fairness_grade: str | None = None
    favors_roster_id: str | None = None
    skipped: bool = False
    error: str | None = None
    multi_party: bool = False


class RecentTrade(BaseModel):
    transaction_id: str
    created_ms: int
    leg: int | None = None
    roster_ids: list[str] = Field(default_factory=list)
    sides: list[TradeActivitySide] = Field(default_factory=list)
    waiver_budget: list[dict[str, Any]] = Field(default_factory=list)
    analysis: TradeActivityAnalysis | None = None


class RecentTradesResponse(BaseModel):
    trades: list[RecentTrade] = Field(default_factory=list)
    total_stored: int = 0
    unanalyzed_count: int = 0


class TradeAnalysisResponse(BaseModel):
    trades_analyzed: int = 0
    trades_failed: int = 0
    trades_pending: int = 0
    error: str | None = None
