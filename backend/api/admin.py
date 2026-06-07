from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.db.session import get_db
from backend.services.history_service import recompute_history

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/recompute-history")
def recompute_history_endpoint(
    league_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
) -> dict:
    settings = get_settings()
    expected = getattr(settings, "admin_token", None)
    if expected and x_admin_token != expected:
        raise HTTPException(status_code=403, detail="Invalid admin token")
    return recompute_history(db, league_id=league_id)
