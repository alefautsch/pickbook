from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models import UserSetting
from backend.db.session import get_db
from backend.schemas.settings import UserSettingsResponse, UserSettingsUpdate
from dynasty_draft.config import DEFAULT_CONFIG, load_config

router = APIRouter(prefix="/settings", tags=["settings"])

SETTING_KEYS = (
    "sleeper_username",
    "dynasty_weights",
    "dynasty_rating_curve",
    "trade_value_blend",
    "worp_blend",
    "dynasty_daddy",
    "ktc_enabled",
    "war_csv",
    "trade_weight",
    "worp_weight",
    "season",
)


def _defaults() -> dict[str, Any]:
    return {
        "sleeper_username": DEFAULT_CONFIG["sleeper_username"],
        "dynasty_weights": DEFAULT_CONFIG["dynasty_weights"],
        "dynasty_rating_curve": DEFAULT_CONFIG["dynasty_rating_curve"],
        "trade_value_blend": DEFAULT_CONFIG["trade_value_blend"],
        "worp_blend": DEFAULT_CONFIG["worp_blend"],
        "dynasty_daddy": DEFAULT_CONFIG["dynasty_daddy"],
        "ktc_enabled": DEFAULT_CONFIG["ktc_enabled"],
        "war_csv": DEFAULT_CONFIG["war_csv"],
        "trade_weight": DEFAULT_CONFIG["trade_weight"],
        "worp_weight": DEFAULT_CONFIG["worp_weight"],
        "season": DEFAULT_CONFIG["season"],
    }


def _read_settings(db: Session) -> dict[str, Any]:
    rows = db.scalars(select(UserSetting)).all()
    merged = _defaults()
    for row in rows:
        if row.key in merged:
            merged[row.key] = row.value_json
    return merged


def _upsert_setting(db: Session, key: str, value: Any) -> None:
    row = db.get(UserSetting, key)
    if row is None:
        row = UserSetting(key=key, value_json=value)
        db.add(row)
    else:
        row.value_json = value


@router.get("", response_model=UserSettingsResponse)
def get_settings(db: Session = Depends(get_db)) -> UserSettingsResponse:
    return UserSettingsResponse(**_read_settings(db))


@router.put("", response_model=UserSettingsResponse)
def put_settings(
    payload: UserSettingsUpdate,
    db: Session = Depends(get_db),
) -> UserSettingsResponse:
    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        if key in SETTING_KEYS:
            _upsert_setting(db, key, value)
    db.commit()
    return UserSettingsResponse(**_read_settings(db))


def seed_settings_from_config(db: Session) -> int:
    """One-off migration: load config.json into user_settings rows."""
    config = load_config()
    count = 0
    for key in SETTING_KEYS:
        if key in config:
            _upsert_setting(db, key, config[key])
            count += 1
    db.commit()
    return count
