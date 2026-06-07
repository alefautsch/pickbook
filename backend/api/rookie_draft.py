from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.db.session import get_db
from backend.schemas.rookie_draft import RookieDraftView
from backend.services.rookie_draft_service import get_rookie_draft_view

router = APIRouter(prefix="/leagues", tags=["rookie-draft"])


@router.get("/{league_id}/rookie-draft", response_model=RookieDraftView)
def read_rookie_draft(
    league_id: str,
    draft_id: str | None = Query(default=None, description="Override auto-resolved rookie draft"),
    roster_id: str | None = Query(
        default=None,
        description="Roster whose positional needs to show (default: my team)",
    ),
    db: Session = Depends(get_db),
) -> RookieDraftView:
    try:
        view = get_rookie_draft_view(
            db,
            league_id,
            draft_id=draft_id,
            roster_id=roster_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if view is None:
        raise HTTPException(
            status_code=404,
            detail="No rookie draft found for this league. Pass draft_id if needed.",
        )
    return view
