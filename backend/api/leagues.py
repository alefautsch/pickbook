from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.db.session import get_db
from backend.schemas.league import LeagueDetail, LeagueRankings, LeagueTile
from backend.services.read_service import get_league_detail, get_league_rankings, list_league_tiles

router = APIRouter(prefix="/leagues", tags=["leagues"])


@router.get("", response_model=list[LeagueTile])
def read_leagues(db: Session = Depends(get_db)) -> list[LeagueTile]:
    return list_league_tiles(db)


@router.get("/{league_id}", response_model=LeagueDetail)
def read_league(league_id: str, db: Session = Depends(get_db)) -> LeagueDetail:
    detail = get_league_detail(db, league_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="League not found")
    return detail


@router.get("/{league_id}/rankings", response_model=LeagueRankings)
def read_league_rankings(league_id: str, db: Session = Depends(get_db)) -> LeagueRankings:
    rankings = get_league_rankings(db, league_id)
    if rankings is None:
        raise HTTPException(status_code=404, detail="League not found")
    return rankings
