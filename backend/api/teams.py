from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.db.session import get_db
from backend.schemas.team import TeamDetail
from backend.services.read_service import get_team_detail

router = APIRouter(tags=["teams"])


@router.get("/leagues/{league_id}/teams/{roster_id}", response_model=TeamDetail)
def read_team(league_id: str, roster_id: str, db: Session = Depends(get_db)) -> TeamDetail:
    detail = get_team_detail(db, league_id, roster_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Team not found")
    return detail
