"""Dynasty Dealer trade-derived values — free public API (dynastydealer.com)."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

import requests

from dynasty_draft.sleeper_client import CACHE_DIR
from dynasty_draft.war_data import normalize_name

PLAYER_VALUES_URL = "https://www.dynastydealer.com/api/player-values"
USER_AGENT = "pickbook/0.3 (personal dynasty draft tool)"
TTL_SECONDS = 12 * 60 * 60
ATTRIBUTION_URL = "https://www.dynastydealer.com"
ATTRIBUTION_LABEL = "Values by Dynasty Dealer"


def _cache_path(*, superflex: bool, per_slot: bool) -> Any:
    tag = "sf" if superflex else "1qb"
    mode = "perslot" if per_slot else "flat"
    return CACHE_DIR / f"dynasty_dealer_{tag}_{mode}.json"


def _float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _request_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        }
    )
    return session


def _read_cache(path: Any, *, ttl_seconds: int, force_refresh: bool) -> dict[str, Any] | None:
    if force_refresh or not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        fetched_at = float(payload.get("fetched_at", 0))
        if time.time() - fetched_at > ttl_seconds:
            return None
        data = payload.get("data")
        return data if isinstance(data, dict) else None
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return None


def _read_stale_cache(path: Any) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        data = payload.get("data")
        return data if isinstance(data, dict) else None
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return None


def _write_cache(path: Any, data: dict[str, Any]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"fetched_at": time.time(), "data": data}, indent=2),
        encoding="utf-8",
    )


def _fetch_player_values(*, superflex: bool, per_slot: bool) -> dict[str, Any]:
    params: dict[str, str] = {}
    if per_slot:
        params["perSlot"] = "true"
    if superflex:
        params["sf"] = "true"
    response = _request_session().get(PLAYER_VALUES_URL, params=params, timeout=45)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise ValueError("Unexpected Dynasty Dealer player-values response")
    return data


@dataclass
class DynastyDealerStore:
    superflex: bool
    by_name: dict[str, float]
    by_sleeper_id: dict[str, float]
    by_slot: dict[tuple[str, int, int], float]
    fetched_at: float

    @classmethod
    def from_payload(cls, payload: dict[str, Any], *, superflex: bool, fetched_at: float) -> DynastyDealerStore:
        by_name: dict[str, float] = {}
        by_sleeper_id: dict[str, float] = {}
        by_slot: dict[tuple[str, int, int], float] = {}
        rows = payload.get("players") or []
        if not isinstance(rows, list):
            rows = []

        for row in rows:
            if not isinstance(row, dict):
                continue
            name = str(row.get("name") or "").strip()
            # Trade-engine value first; current_value adds community votes.
            value = _float(row.get("base_value")) or _float(row.get("current_value"))
            if not name or value is None or value <= 0:
                continue
            key = normalize_name(name)
            if key and key not in by_name:
                by_name[key] = float(value)

            sleeper_id = str(row.get("sleeper_id") or "")
            if sleeper_id.startswith("pick_") and "_slot_" in sleeper_id:
                parts = sleeper_id.split("_")
                # pick_2026_1_slot_01
                if len(parts) >= 5:
                    season = parts[1]
                    round_no = int(parts[2])
                    slot_no = int(parts[4])
                    by_slot[(season, round_no, slot_no)] = float(value)
                continue

            if sleeper_id and not sleeper_id.startswith("pick_"):
                by_sleeper_id[sleeper_id] = float(value)

            if name.startswith("20") and " Pick " in name:
                # "2026 Pick 1.01"
                try:
                    season_part, rest = name.split(" Pick ", 1)
                    round_part, slot_part = rest.split(".", 1)
                    by_slot[(season_part, int(round_part), int(slot_part))] = float(value)
                except (TypeError, ValueError):
                    pass

        return cls(
            superflex=superflex,
            by_name=by_name,
            by_sleeper_id=by_sleeper_id,
            by_slot=by_slot,
            fetched_at=fetched_at,
        )

    @classmethod
    def load(
        cls,
        *,
        superflex: bool = True,
        force_refresh: bool = False,
        ttl_seconds: int = TTL_SECONDS,
    ) -> DynastyDealerStore | None:
        path = _cache_path(superflex=superflex, per_slot=True)
        cached = _read_cache(path, ttl_seconds=ttl_seconds, force_refresh=force_refresh)
        if cached is not None:
            return cls.from_payload(cached, superflex=superflex, fetched_at=time.time())

        try:
            payload = _fetch_player_values(superflex=superflex, per_slot=True)
            _write_cache(path, payload)
            return cls.from_payload(payload, superflex=superflex, fetched_at=time.time())
        except requests.RequestException:
            stale = _read_stale_cache(path)
            if stale is not None:
                return cls.from_payload(stale, superflex=superflex, fetched_at=0.0)
            return None

    def lookup_player(self, name: str) -> float | None:
        return self.by_name.get(normalize_name(name))

    def lookup_sleeper_id(self, player_id: str) -> float | None:
        return self.by_sleeper_id.get(str(player_id))

    def lookup_player_value(self, *, name: str, player_id: str | None = None) -> float | None:
        if player_id:
            by_id = self.lookup_sleeper_id(player_id)
            if by_id is not None:
                return by_id
        return self.lookup_player(name)

    def lookup_slot(
        self,
        season: str | int,
        round_no: int,
        slot_in_round: int,
    ) -> float | None:
        return self.by_slot.get((str(season), int(round_no), int(slot_in_round)))


def load_dynasty_dealer_store(
    config: dict[str, Any],
    *,
    superflex: bool,
    force_refresh: bool = False,
) -> DynastyDealerStore | None:
    dealer_cfg = config.get("dynasty_dealer") or {}
    if not bool(dealer_cfg.get("enabled", True)):
        return None
    return DynastyDealerStore.load(
        superflex=superflex,
        force_refresh=force_refresh,
    )

