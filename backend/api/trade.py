from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.db.session import get_db
from backend.schemas.trade import (
    TradeEvaluateRequest,
    TradeEvaluateResponse,
    TradeSuggestRequest,
    TradeSuggestResponse,
    TradeValidateRequest,
    TradeValidationResult,
)
from backend.services.trade_calculator_service import evaluate_trade, suggest_trade_packages, validate_trade_dual

router = APIRouter(prefix="/leagues", tags=["trade"])


@router.post("/{league_id}/trade/evaluate", response_model=TradeEvaluateResponse)
def post_trade_evaluate(
    league_id: str,
    body: TradeEvaluateRequest,
    db: Session = Depends(get_db),
) -> TradeEvaluateResponse:
    if body.side_a_roster_id == body.side_b_roster_id:
        raise HTTPException(status_code=400, detail="Trade sides must be different teams")
    result = evaluate_trade(db, league_id, body)
    if result is None:
        raise HTTPException(status_code=404, detail="League or team not found")
    return result


@router.post("/{league_id}/trade/validate", response_model=TradeValidationResult)
def post_trade_validate(
    league_id: str,
    body: TradeValidateRequest,
    db: Session = Depends(get_db),
) -> TradeValidationResult:
    if body.side_a_roster_id == body.side_b_roster_id:
        raise HTTPException(status_code=400, detail="Trade sides must be different teams")
    result = validate_trade_dual(db, league_id, body)
    if result is None:
        raise HTTPException(status_code=404, detail="League or team not found")
    return result


@router.post("/{league_id}/trade/suggest", response_model=TradeSuggestResponse)
def post_trade_suggest(
    league_id: str,
    body: TradeSuggestRequest,
    db: Session = Depends(get_db),
) -> TradeSuggestResponse:
    if body.mode == "acquire" and not body.counterparty_roster_id:
        raise HTTPException(
            status_code=400,
            detail="counterparty_roster_id is required for acquire mode",
        )
    if (
        body.counterparty_roster_id
        and body.proposer_roster_id == body.counterparty_roster_id
    ):
        raise HTTPException(status_code=400, detail="Proposer and counterparty must differ")
    result = suggest_trade_packages(db, league_id, body)
    if result is None:
        raise HTTPException(status_code=404, detail="League or team not found")
    return result
