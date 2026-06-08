from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.advisor import router as advisor_router
from backend.api.admin import router as admin_router
from backend.api.leagues import router as leagues_router
from backend.api.rookie_draft import router as rookie_draft_router
from backend.api.players import router as players_router
from backend.api.portfolio import router as portfolio_router
from backend.api.settings import router as settings_router
from backend.api.sync import router as sync_router
from backend.api.teams import router as teams_router
from backend.config import get_settings
from backend.schemas.settings import HealthResponse
from backend.services.scheduler_service import scheduled_sync_loop


settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    stop_event = asyncio.Event()
    sync_task = asyncio.create_task(scheduled_sync_loop(settings, stop_event))
    try:
        yield
    finally:
        stop_event.set()
        sync_task.cancel()
        try:
            await sync_task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="Dynasty Blackbook API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(settings_router)
app.include_router(advisor_router)
app.include_router(sync_router)
app.include_router(admin_router)
app.include_router(leagues_router)
app.include_router(rookie_draft_router)
app.include_router(players_router)
app.include_router(portfolio_router)
app.include_router(teams_router)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse()
