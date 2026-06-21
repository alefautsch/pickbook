from __future__ import annotations

import hashlib
import json
import re
import time
import unicodedata
from dataclasses import dataclass
from typing import Any

import requests

from dynasty_draft.sleeper_client import CACHE_DIR
from dynasty_draft.war_data import POSITIONS, PlayerValue, WarData, normalize_name

PLAYER_VALUES_URL = "https://dynasty-daddy.com/api/v1/player/all/today"
LEAGUE_FORMAT_URL = "https://dynasty-daddy.com/api/v1/league/format"
USER_AGENT = "pickbook/0.3 (personal dynasty draft tool)"
TTL_SECONDS = 12 * 60 * 60


def _float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int | None:
    parsed = _float(value)
    return int(parsed) if parsed is not None else None


def _compact_text(value: str) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _player_name(row: dict[str, Any]) -> str:
    if row.get("full_name"):
        return str(row["full_name"]).strip()
    return " ".join(
        str(part).strip()
        for part in (row.get("first_name"), row.get("last_name"))
        if part
    ).strip()


def _metric_keys(name: str, pos: str, name_id: Any = None) -> list[str]:
    suffix = (pos or "").lower()
    keys = [
        f"{_compact_text(name)}{suffix}",
        f"{normalize_name(name).replace(' ', '')}{suffix}",
    ]
    if name_id:
        keys.append(f"{_compact_text(str(name_id))}{suffix}")
    return [key for key in dict.fromkeys(keys) if key]


def _format_hash(payload: dict[str, Any]) -> str:
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]


def _player_cache_path(market: int):
    return CACHE_DIR / f"dynasty_daddy_player_values_market_{market}.json"


def _format_cache_path(payload: dict[str, Any]):
    return CACHE_DIR / f"dynasty_daddy_league_format_{_format_hash(payload)}.json"


def _request_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        }
    )
    return session


def _read_cache(path, *, ttl_seconds: int, force_refresh: bool) -> Any | None:
    if force_refresh or not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        fetched_at = float(payload.get("fetched_at", 0))
        if time.time() - fetched_at > ttl_seconds:
            return None
        return payload.get("data")
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return None


def _write_cache(path, data: Any) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"fetched_at": time.time(), "data": data}, indent=2),
        encoding="utf-8",
    )


def _fetch_player_values(
    *,
    market: int,
    force_refresh: bool,
    ttl_seconds: int,
) -> list[dict[str, Any]]:
    path = _player_cache_path(market)
    cached = _read_cache(path, ttl_seconds=ttl_seconds, force_refresh=force_refresh)
    if isinstance(cached, list):
        return cached

    response = _request_session().get(
        PLAYER_VALUES_URL,
        params={"market": market},
        timeout=45,
    )
    response.raise_for_status()
    rows = response.json()
    if not isinstance(rows, list):
        raise ValueError("Unexpected Dynasty Daddy player values response")
    _write_cache(path, rows)
    return rows


def _fetch_league_format(
    payload: dict[str, Any],
    *,
    force_refresh: bool,
    ttl_seconds: int,
) -> dict[str, Any]:
    path = _format_cache_path(payload)
    cached = _read_cache(path, ttl_seconds=ttl_seconds, force_refresh=force_refresh)
    if isinstance(cached, dict):
        return cached

    session = _request_session()
    session.headers["Content-Type"] = "application/json"
    response = session.post(LEAGUE_FORMAT_URL, json=payload, timeout=90)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise ValueError("Unexpected Dynasty Daddy league-format response")
    _write_cache(path, data)
    return data


def _count_positions(roster_positions: list[str], *slots: str) -> int:
    accepted = {slot.upper() for slot in slots}
    return sum(1 for pos in roster_positions if str(pos).upper() in accepted)


def _format_from_league(league_row: Any) -> dict[str, int]:
    roster_positions = list(league_row.roster_positions_json or [])
    return {
        "teamCount": int(league_row.total_rosters or 0),
        "QB": _count_positions(roster_positions, "QB"),
        "RB": _count_positions(roster_positions, "RB"),
        "WR": _count_positions(roster_positions, "WR"),
        "TE": _count_positions(roster_positions, "TE"),
        "FLEX": _count_positions(roster_positions, "FLEX"),
        "REC_FLEX": _count_positions(roster_positions, "REC_FLEX"),
        "WRRB_FLEX": _count_positions(roster_positions, "WRRB_FLEX"),
        "SUPER_FLEX": _count_positions(roster_positions, "SUPER_FLEX", "SUPERFLEX", "QB_WR_RB_TE"),
        "K": _count_positions(roster_positions, "K"),
        "DF": _count_positions(roster_positions, "DEF", "DF"),
        "LB": _count_positions(roster_positions, "LB"),
        "DB": _count_positions(roster_positions, "DB"),
        "DL": _count_positions(roster_positions, "DL"),
        "IDP_FLEX": _count_positions(roster_positions, "IDP_FLEX"),
    }


def _default_war_season(league_row: Any) -> int:
    try:
        return max(2000, int(league_row.season) - 1)
    except (TypeError, ValueError):
        return 2025


def _league_format_payload(league_row: Any, config: dict[str, Any]) -> dict[str, Any]:
    seasons = config.get("seasons")
    if not seasons:
        seasons = [_default_war_season(league_row)]
    return {
        "seasons": [int(season) for season in seasons],
        "startWeek": int(config.get("start_week", 1)),
        "endWeek": int(config.get("end_week", 18)),
        "format": _format_from_league(league_row),
        "settings": league_row.scoring_json or {},
    }


@dataclass(frozen=True)
class DynastyDaddyMetric:
    worp: float | None
    porp: float | None
    percent: float | None
    c_worp: float | None
    pos: str | None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> DynastyDaddyMetric:
        values = row.get("w") or {}
        return cls(
            worp=_float(values.get("worp")),
            porp=_float(values.get("porp")),
            percent=_float(values.get("percent")),
            c_worp=_float(values.get("cWorp")),
            pos=str(values.get("pos") or "").upper() or None,
        )


def _upside_from_metric(metric: DynastyDaddyMetric | None) -> float:
    """Derive 0–1 upside from Dynasty Daddy league-format metrics."""
    if metric is None:
        return 0.45
    if metric.percent is not None:
        return max(0.0, min(1.0, float(metric.percent)))
    if metric.porp is not None and metric.porp > 0:
        return max(0.0, min(1.0, float(metric.porp) / 120.0))
    return 0.45


@dataclass
class DynastyDaddyStore:
    market: int
    superflex: bool
    player_values: list[dict[str, Any]]
    league_metrics: dict[str, dict[str, Any]]
    league_format_payload: dict[str, Any]
    fetched_at: float

    @classmethod
    def load_values_only(
        cls,
        *,
        superflex: bool,
        config: dict[str, Any] | None = None,
        force_refresh: bool = False,
        ttl_seconds: int = TTL_SECONDS,
    ) -> DynastyDaddyStore:
        """Trade values without league-format WORP (pick/trade paths without league row)."""
        config = config or {}
        market = int(config.get("market", 14))
        player_values = _fetch_player_values(
            market=market,
            force_refresh=force_refresh,
            ttl_seconds=ttl_seconds,
        )
        return cls(
            market=market,
            superflex=superflex,
            player_values=player_values,
            league_metrics={},
            league_format_payload={},
            fetched_at=time.time(),
        )

    @classmethod
    def load(
        cls,
        *,
        league_row: Any,
        superflex: bool,
        config: dict[str, Any] | None = None,
        force_refresh: bool = False,
        ttl_seconds: int = TTL_SECONDS,
    ) -> DynastyDaddyStore:
        config = config or {}
        market = int(config.get("market", 14))
        player_values = _fetch_player_values(
            market=market,
            force_refresh=force_refresh,
            ttl_seconds=ttl_seconds,
        )
        payload = _league_format_payload(league_row, config)
        try:
            league_metrics = _fetch_league_format(
                payload,
                force_refresh=force_refresh,
                ttl_seconds=ttl_seconds,
            )
        except requests.RequestException:
            league_metrics = {}
        return cls(
            market=market,
            superflex=superflex,
            player_values=player_values,
            league_metrics=league_metrics,
            league_format_payload=payload,
            fetched_at=time.time(),
        )

    def selected_trade_value(self, row: dict[str, Any]) -> float | None:
        primary = "sf_trade_value" if self.superflex else "trade_value"
        fallback = "trade_value" if self.superflex else "sf_trade_value"
        return _float(row.get(primary)) or _float(row.get(fallback))

    def metric_for(self, name: str, pos: str, *, name_id: Any = None) -> DynastyDaddyMetric | None:
        for key in _metric_keys(name, pos, name_id):
            row = self.league_metrics.get(key)
            if isinstance(row, dict):
                return DynastyDaddyMetric.from_row(row)
        return None

    def to_war_data(self, war: WarData | None = None) -> WarData:
        """Build WarData from API values, optionally merging an existing store."""
        return self.overlay_war_data(war if war is not None else WarData.empty())

    def overlay_war_data(self, war: WarData) -> WarData:
        by_name = dict(war.by_name)
        players_by_name: dict[str, PlayerValue] = {}
        value_inputs: dict[str, dict[str, Any]] = {}

        for row in self.player_values:
            name = _player_name(row)
            pos = str(row.get("position") or "").upper()
            if not name or pos not in POSITIONS:
                continue
            trade_value = self.selected_trade_value(row)
            if trade_value is None or trade_value <= 0:
                continue

            key = normalize_name(name)
            existing = by_name.get(key)
            metric = self.metric_for(name, pos, name_id=row.get("name_id"))
            player = PlayerValue(
                name=name,
                pos=pos,
                team=str(row.get("team") or (existing.team if existing else "")).upper(),
                worp_tier=existing.worp_tier if existing else None,
                worp=metric.worp if metric and metric.worp is not None else (existing.worp if existing else None),
                porp=metric.porp if metric and metric.porp is not None else (existing.porp if existing else None),
                trade_value=trade_value,
                spike_high_p=None,
                spike_mid_p=None,
                spike_low_p=None,
                dynasty_upside=_upside_from_metric(metric),
            )
            players_by_name[key] = player
            value_inputs[key] = {
                "dynasty_daddy": {
                    "source": "api",
                    "market": self.market,
                    "superflex": self.superflex,
                    "trade_value": _float(row.get("trade_value")),
                    "sf_trade_value": _float(row.get("sf_trade_value")),
                    "selected_trade_value": trade_value,
                    "selected_format": "superflex" if self.superflex else "standard",
                    "overall_rank": _int(row.get("sf_overall_rank" if self.superflex else "overall_rank")),
                    "position_rank": _int(row.get("sf_position_rank" if self.superflex else "position_rank")),
                    "date": row.get("date"),
                    "sleeper_id": row.get("sleeper_id"),
                },
                "league_format": {
                    "source": "api" if metric else None,
                    "worp": metric.worp if metric else None,
                    "porp": metric.porp if metric else None,
                    "percent": metric.percent if metric else None,
                    "c_worp": metric.c_worp if metric else None,
                    "seasons": self.league_format_payload.get("seasons"),
                    "start_week": self.league_format_payload.get("startWeek"),
                    "end_week": self.league_format_payload.get("endWeek"),
                },
                "war_csv_fallback": war.lookup_value_inputs(existing.name) if existing else {},
            }

        for key, existing in by_name.items():
            if key in players_by_name:
                continue
            players_by_name[key] = existing
            value_inputs[key] = war.lookup_value_inputs(existing.name)

        players = sorted(players_by_name.values(), key=lambda player: player.trade_value, reverse=True)
        war.replace_players(players, value_inputs_by_name=value_inputs)
        return war
