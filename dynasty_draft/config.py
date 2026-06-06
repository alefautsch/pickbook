from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

CONFIG_PATH = Path("config.json")
EXAMPLE_PATH = Path("config.example.json")

DEFAULT_CONFIG: dict[str, Any] = {
    "sleeper_username": "alefautsch",
    "league_id": "1314731206859853824",
    "draft_id": "1314734674332880896",
    "season": "2026",
    "trade_weight": 0.65,
    "worp_weight": 0.35,
    "dynasty_weights": {
        "tv": 0.45,
        "worp": 0.25,
        "upside": 0.15,
        "age": 0.10,
        "trajectory": 0.05,
    },
    "poll_seconds": 20,
    "war_csv": "war.csv",
    "strategy": {
        "draft_phase": "vets",
        "teams": 10,
        "startup_slot": 10,
        "rookie_draft_slot": 1,
        "reserved_rookies": ["Jeremiyah Love"],
        "rookie_draft_reversed": True,
    },
}


def _apply_env(config: dict[str, Any]) -> dict[str, Any]:
    """Railway / production overrides from environment variables."""
    scalar_map = {
        "SLEEPER_USERNAME": "sleeper_username",
        "LEAGUE_ID": "league_id",
        "DRAFT_ID": "draft_id",
        "SEASON": "season",
        "WAR_CSV": "war_csv",
    }
    for env_key, config_key in scalar_map.items():
        value = os.environ.get(env_key, "").strip()
        if value:
            config[config_key] = value

    if os.environ.get("TRADE_WEIGHT"):
        config["trade_weight"] = float(os.environ["TRADE_WEIGHT"])
    if os.environ.get("WORP_WEIGHT"):
        config["worp_weight"] = float(os.environ["WORP_WEIGHT"])
    if os.environ.get("POLL_SECONDS"):
        config["poll_seconds"] = int(os.environ["POLL_SECONDS"])

    strategy = config.setdefault("strategy", {})
    if os.environ.get("DRAFT_PHASE"):
        strategy["draft_phase"] = os.environ["DRAFT_PHASE"].strip().lower()
    if os.environ.get("STARTUP_SLOT"):
        strategy["startup_slot"] = int(os.environ["STARTUP_SLOT"])
    if os.environ.get("ROOKIE_DRAFT_SLOT"):
        strategy["rookie_draft_slot"] = int(os.environ["ROOKIE_DRAFT_SLOT"])
    if os.environ.get("RESERVED_ROOKIES"):
        strategy["reserved_rookies"] = [
            name.strip() for name in os.environ["RESERVED_ROOKIES"].split(",") if name.strip()
        ]
    return config


def load_config() -> dict[str, Any]:
    if CONFIG_PATH.exists():
        config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    elif EXAMPLE_PATH.exists():
        config = json.loads(EXAMPLE_PATH.read_text(encoding="utf-8"))
    else:
        config = {}
    merged = DEFAULT_CONFIG.copy()
    merged.update({k: v for k, v in config.items() if k != "strategy"})
    merged["strategy"] = {**DEFAULT_CONFIG["strategy"], **(config.get("strategy") or {})}
    return _apply_env(merged)


def save_config(config: dict[str, Any]) -> None:
    CONFIG_PATH.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
