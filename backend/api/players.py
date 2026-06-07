from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.db.session import get_db
from backend.schemas.player import PlayerCard, PlayerHistorySeries
from backend.schemas.portfolio import PlayerHoldings, PlayerSearchResults
from backend.services.history_service import get_player_history
from backend.services.portfolio_service import get_player_holdings, search_players
from backend.services.read_service import get_player_card

router = APIRouter(prefix="/players", tags=["players"])


@router.get("/search", response_model=PlayerSearchResults)
def read_player_search(
    q: str = Query(..., min_length=1, description="Player name search"),
    limit: int = Query(default=25, ge=1, le=50),
    db: Session = Depends(get_db),
) -> PlayerSearchResults:
    return search_players(db, q, limit=limit)


@router.get("/{player_id}/holdings", response_model=PlayerHoldings)
def read_player_holdings(
    player_id: str,
    db: Session = Depends(get_db),
) -> PlayerHoldings:
    holdings = get_player_holdings(db, player_id)
    if holdings is None:
        raise HTTPException(status_code=404, detail="Player not in portfolio")
    return holdings


@router.get("/{player_id}", response_model=PlayerCard)
def read_player(
    player_id: str,
    league_id: str = Query(..., description="League context for this grade"),
    db: Session = Depends(get_db),
) -> PlayerCard:
    card = get_player_card(db, player_id, league_id)
    if card is None:
        raise HTTPException(status_code=404, detail="Player not found in league snapshots")
    return card


@router.get("/{player_id}/history", response_model=PlayerHistorySeries)
def read_player_history(
    player_id: str,
    league_id: str = Query(..., description="League context for this grade series"),
    limit: int = Query(default=90, ge=1, le=365),
    db: Session = Depends(get_db),
) -> PlayerHistorySeries:
    series = get_player_history(db, player_id, league_id, limit=limit)
    if series is None:
        raise HTTPException(status_code=404, detail="No history for player in league")
    return series
