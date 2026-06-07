from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.admin import router as admin_router
from backend.api.leagues import router as leagues_router
from backend.api.players import router as players_router
from backend.api.settings import router as settings_router
from backend.api.sync import router as sync_router
from backend.api.teams import router as teams_router
from backend.config import get_settings
from backend.schemas.settings import HealthResponse

app = FastAPI(title="Dynasty Blackbook API", version="0.1.0")

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(settings_router)
app.include_router(sync_router)
app.include_router(admin_router)
app.include_router(leagues_router)
app.include_router(players_router)
app.include_router(teams_router)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse()
