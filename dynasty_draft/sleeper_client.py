from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import requests

BASE_URL = "https://api.sleeper.app/v1"
CACHE_DIR = Path(".cache")
PLAYERS_CACHE = CACHE_DIR / "sleeper_players.json"
PLAYERS_TTL_SECONDS = 24 * 60 * 60


class SleeperClient:
    def __init__(self, session: requests.Session | None = None):
        self.session = session or requests.Session()
        self.session.headers.setdefault("User-Agent", "dynasty-draft-tool/0.1")

    def _get(self, path: str) -> Any:
        response = self.session.get(f"{BASE_URL}{path}", timeout=30)
        response.raise_for_status()
        return response.json()

    def get_user(self, username_or_id: str) -> dict[str, Any]:
        return self._get(f"/user/{username_or_id}")

    def get_user_leagues(self, user_id: str, season: str = "2025") -> list[dict[str, Any]]:
        return self._get(f"/user/{user_id}/leagues/nfl/{season}")

    def get_league(self, league_id: str) -> dict[str, Any]:
        return self._get(f"/league/{league_id}")

    def get_league_users(self, league_id: str) -> list[dict[str, Any]]:
        return self._get(f"/league/{league_id}/users")

    def get_draft(self, draft_id: str) -> dict[str, Any]:
        return self._get(f"/draft/{draft_id}")

    def get_draft_picks(self, draft_id: str) -> list[dict[str, Any]]:
        return self._get(f"/draft/{draft_id}/picks")

    def get_players(self, force_refresh: bool = False) -> dict[str, dict[str, Any]]:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        if (
            not force_refresh
            and PLAYERS_CACHE.exists()
            and (time.time() - PLAYERS_CACHE.stat().st_mtime) < PLAYERS_TTL_SECONDS
        ):
            return json.loads(PLAYERS_CACHE.read_text(encoding="utf-8"))
        players = self._get("/players/nfl")
        PLAYERS_CACHE.write_text(json.dumps(players), encoding="utf-8")
        return players
