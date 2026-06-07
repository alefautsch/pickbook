from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.db.session import get_db
from backend.schemas.portfolio import PortfolioSummary
from backend.services.portfolio_service import get_portfolio

router = APIRouter(tags=["portfolio"])


@router.get("/portfolio", response_model=PortfolioSummary)
def read_portfolio(db: Session = Depends(get_db)) -> PortfolioSummary:
    return get_portfolio(db)
