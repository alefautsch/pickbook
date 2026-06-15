from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class TradePickRef(BaseModel):
    season: str
    round: int
    original_roster_id: str


class TradeSideInput(BaseModel):
    players: list[str] = Field(default_factory=list)
    picks: list[TradePickRef] = Field(default_factory=list)


class TradeEvaluateRequest(BaseModel):
    side_a_roster_id: str
    side_b_roster_id: str
    side_a_gives: TradeSideInput
    side_b_gives: TradeSideInput


class TradeValidateRequest(TradeEvaluateRequest):
    pass


class TradeAssetPlayer(BaseModel):
    player_id: str
    name: str | None = None
    position: str | None = None
    ovr: int | None = None
    tv: float | None = None
    hppg: float | None = None
    injury: str | None = None


class TradeAssetPick(BaseModel):
    season: str
    round: int
    original_roster_id: str
    owner_roster_id: str | None = None
    slot_tier: str | None = None
    trade_value: float | None = None
    label: str | None = None


class TradeResolvedSide(BaseModel):
    players: list[TradeAssetPlayer] = Field(default_factory=list)
    picks: list[TradeAssetPick] = Field(default_factory=list)


class TradeLineupStarterSlot(BaseModel):
    slot: str
    player_id: str | None = None
    name: str | None = None
    position: str | None = None
    ppg: float | None = None
    ovr: int | None = None
    is_incoming: bool = False
    is_changed: bool = False


class TradeLineupSide(BaseModel):
    before: float | None = None
    after: float | None = None
    delta: float | None = None
    starters: list[TradeLineupStarterSlot] = Field(default_factory=list)
    incoming_picks: list[TradeAssetPick] = Field(default_factory=list)


class TradeLineupImpact(BaseModel):
    side_a: TradeLineupSide
    side_b: TradeLineupSide


class TradeEvaluation(BaseModel):
    give_total_tv: float
    receive_total_tv: float
    give_value_adjustment: float
    receive_value_adjustment: float
    give_adjusted_tv: float
    receive_adjusted_tv: float
    give_effective_tv: float
    receive_effective_tv: float
    consolidation_tax_tv: float
    consolidation_premium_pct: int
    give_consolidating: bool
    receive_consolidating: bool
    net_delta_tv: float
    net_delta_adjusted_tv: float
    net_delta_effective_tv: float
    net_delta_adjusted_total_tv: float
    net_delta_pct: float
    net_delta_adjusted_pct: float
    fairness_band: str
    within_band: bool
    fairness: Literal["fair", "favors_you", "favors_counterparty"]
    positional_notes: list[str] = Field(default_factory=list)
    missing_assets: list[str] = Field(default_factory=list)
    give: TradeResolvedSide
    receive: TradeResolvedSide
    tv_fairness_grade: str
    favors_roster_id: str | None = None
    lineup: TradeLineupImpact | None = None


class TradeSideValidation(BaseModel):
    roster_id: str
    team_name: str | None = None
    accept_likelihood: Literal["low", "medium", "high"] | None = None
    fairness_view: Literal["favors_them", "fair", "favors_you"] | None = None
    fairness_label: str | None = None
    would_improve_roster: bool | None = None
    reasoning: str | None = None
    blockers: list[str] = Field(default_factory=list)
    suggested_tweak: str | None = None
    grade: str | None = None
    skipped: bool = False
    error: str | None = None


class TradeRookieProjection(BaseModel):
    name: str | None = None
    pos: str | None = None
    ovr: int | None = None
    adp_pick: int | None = None
    trade_value: float | None = None


class TradePickRookieContext(BaseModel):
    label: str
    pick_no: int | None = None
    given_by: str
    acquired_by: str
    projected_rookie: TradeRookieProjection | None = None
    nearby_rookies: list[TradeRookieProjection] = Field(default_factory=list)
    likely_range: list[TradeRookieProjection] = Field(default_factory=list)
    consensus_note: str | None = None
    fills_need_for_acquirer: bool | None = None
    tep_note: str | None = None


class TradeRookieDraftContext(BaseModel):
    season: str
    te_premium: float = 0.0
    picks_in_trade: list[TradePickRookieContext] = Field(default_factory=list)
    board_top: list[dict[str, Any]] = Field(default_factory=list)


class TradeFixSuggestion(BaseModel):
    headline: str | None = None
    reasoning: str | None = None
    adjustments: list[str] = Field(default_factory=list)
    both_sides_likely_accept: bool | None = None
    skipped: bool = False
    error: str | None = None


class TradeValidationResult(BaseModel):
    evaluation: TradeEvaluation
    side_a: TradeSideValidation
    side_b: TradeSideValidation
    overall_grade: str
    summary: str | None = None
    rookie_draft_context: TradeRookieDraftContext | None = None
    trade_fix: TradeFixSuggestion | None = None


class TradeEvaluateResponse(BaseModel):
    side_a_roster_id: str
    side_b_roster_id: str
    side_a_team_name: str | None = None
    side_b_team_name: str | None = None
    evaluation: TradeEvaluation
    rookie_draft_context: TradeRookieDraftContext | None = None


class TradeSuggestRequest(BaseModel):
    mode: Literal["acquire", "sell"]
    proposer_roster_id: str
    counterparty_roster_id: str | None = None
    player_ids: list[str] = Field(default_factory=list)
    picks: list[TradePickRef] = Field(default_factory=list)
    rank_by_validation: bool = True
    lubricant_mode: bool = True
    keep_current_first: bool = True


class TradeSuggestPackageSide(BaseModel):
    players: list[TradeAssetPlayer] = Field(default_factory=list)
    picks: list[TradeAssetPick] = Field(default_factory=list)


class TradeSuggestCounterparty(BaseModel):
    roster_id: str
    team_name: str | None = None
    direction: str | None = None
    contender_tier: str | None = None
    trade_pattern: str | None = None


class TradeSuggestPackage(BaseModel):
    counterparty: TradeSuggestCounterparty
    give: TradeSuggestPackageSide
    receive: TradeSuggestPackageSide
    net_delta_adjusted_pct: float | None = None
    package_quality: float | None = None
    acquisition_score: float | None = None
    disposal_score: float | None = None
    rationale: str | None = None
    validation_accept_score: float | None = None
    counterparty_validation: dict[str, Any] | None = None


class TradeSuggestResponse(BaseModel):
    mode: str
    proposer_roster_id: str
    counterparty_roster_id: str | None = None
    validation_ranked: bool = False
    packages: list[TradeSuggestPackage] = Field(default_factory=list)
