from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class UserSettingsResponse(BaseModel):
    sleeper_username: str
    dynasty_weights: dict[str, float]
    dynasty_rating_curve: dict[str, float]
    trade_value_blend: dict[str, float]
    worp_blend: dict[str, Any]
    dynasty_daddy: dict[str, Any]
    ktc_enabled: bool = True
    war_csv: str = "war.csv"
    trade_weight: float = 0.65
    worp_weight: float = 0.35
    season: str = "2026"


class UserSettingsUpdate(BaseModel):
    sleeper_username: str | None = None
    dynasty_weights: dict[str, float] | None = None
    dynasty_rating_curve: dict[str, float] | None = None
    trade_value_blend: dict[str, float] | None = None
    worp_blend: dict[str, Any] | None = None
    dynasty_daddy: dict[str, Any] | None = None
    ktc_enabled: bool | None = None
    war_csv: str | None = None
    trade_weight: float | None = None
    worp_weight: float | None = None
    season: str | None = None


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str = Field(default="blackbook-api")
