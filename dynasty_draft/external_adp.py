from __future__ import annotations

import csv
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from dynasty_draft.sleeper_client import CACHE_DIR
from dynasty_draft.war_data import normalize_name

ADP_TTL_SECONDS = 12 * 60 * 60
USER_AGENT = "pickbook/0.3 (personal dynasty draft tool)"

BEATADP_SLEEPER_URL = "https://www.beatadp.com/platform-adp/sleeper"
DLF_SUPERFLEX_URL = "https://dynastyleaguefootball.com/adp/index.php?type=superflex"
SLEEPER_PROJECTIONS_URL = (
    "https://api.sleeper.com/projections/nfl/{season}"
    "?season_type=regular&position[]=QB&position[]=RB&position[]=TE&position[]=WR"
    "&order_by={order_by}"
)
# Sleeper uses 999 as a sentinel when a player has no ADP for a format.
_ADP_MISSING = 900.0

_BEATADP_ROW_RE = re.compile(
    r'\{"player":\{"id":\d+,"fullName":"([^"]+)","position":"([^"]*)"'
    r'(?:,"teamId":"[^"]*")?\},"adps":(\{[^}]*\}),"consensus":([0-9.]+|null)\}'
)
_DLF_ROW_RE = re.compile(r'\|(\d+)\|([0-9.]+)\|[^|]+\|\[([^\]]+)\]')


@dataclass(frozen=True)
class AdpStore:
    """External average draft position keyed by normalized player name."""

    source: str
    label: str
    by_name: dict[str, int]
    raw_by_name: dict[str, float]
    fetched_at: float
    max_pick: int

    def lookup(self, name: str) -> int | None:
        return self.by_name.get(normalize_name(name))

    def raw(self, name: str) -> float | None:
        return self.raw_by_name.get(normalize_name(name))

    @classmethod
    def from_rows(
        cls,
        rows: list[dict[str, Any]],
        *,
        source: str,
        label: str,
        fetched_at: float | None = None,
    ) -> AdpStore:
        by_name: dict[str, int] = {}
        raw_by_name: dict[str, float] = {}
        for row in rows:
            name = (row.get("name") or "").strip()
            if not name or name.startswith("!"):
                continue
            adp = row.get("adp")
            if adp is None:
                continue
            raw = float(adp)
            key = normalize_name(name)
            if key and key not in by_name:
                by_name[key] = int(row.get("pick") or max(1, round(raw)))
                raw_by_name[key] = raw
        max_pick = max(by_name.values(), default=0)
        return cls(
            source=source,
            label=label,
            by_name=by_name,
            raw_by_name=raw_by_name,
            fetched_at=fetched_at or time.time(),
            max_pick=max_pick,
        )

    @classmethod
    def load(
        cls,
        config: dict[str, Any],
        *,
        superflex: bool,
        force_refresh: bool = False,
        ttl_seconds: int = ADP_TTL_SECONDS,
    ) -> AdpStore | None:
        adp_cfg = config.get("adp") or {}
        source = str(adp_cfg.get("source", "auto")).strip().lower()
        if source in {"", "trade_value", "none", "off"}:
            return None

        resolved = _resolve_source(source, superflex=superflex)
        season = str(adp_cfg.get("season") or config.get("season") or "2026")
        cache_suffix = f"_{season}" if resolved.startswith("sleeper_") else ""
        cache_path = CACHE_DIR / f"adp_{resolved}{cache_suffix}.json"
        now = time.time()
        if not force_refresh and cache_path.exists():
            try:
                payload = json.loads(cache_path.read_text(encoding="utf-8"))
                fetched_at = float(payload.get("fetched_at", 0))
                if now - fetched_at < ttl_seconds:
                    return cls.from_rows(
                        payload.get("players") or [],
                        source=str(payload.get("source", resolved)),
                        label=str(payload.get("label", resolved)),
                        fetched_at=fetched_at,
                    )
            except (json.JSONDecodeError, OSError, TypeError, ValueError):
                pass

        rows, label = _fetch(
            resolved,
            adp_cfg=adp_cfg,
            config=config,
            superflex=superflex,
        )
        if not rows:
            return None

        fetched_at = time.time()
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(
            json.dumps(
                {
                    "fetched_at": fetched_at,
                    "source": resolved,
                    "label": label,
                    "players": rows,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return cls.from_rows(rows, source=resolved, label=label, fetched_at=fetched_at)


def _resolve_source(source: str, *, superflex: bool) -> str:
    if source in {"dynastyprocess_2qb", "dynastyprocess_1qb"}:
        return "sleeper_dynasty_2qb" if superflex else "sleeper_dynasty_1qb"
    if source != "auto":
        return source
    return "sleeper_dynasty_2qb" if superflex else "sleeper_redraft_half_ppr"


def _fetch(
    source: str,
    *,
    adp_cfg: dict[str, Any],
    config: dict[str, Any],
    superflex: bool,
) -> tuple[list[dict[str, Any]], str]:
    if source == "csv":
        path = Path(str(adp_cfg.get("csv_path") or ""))
        if not path.exists():
            raise FileNotFoundError(f"ADP csv not found: {path}")
        return _load_csv(path), f"CSV ({path.name})"

    season = str(adp_cfg.get("season") or config.get("season") or "2026")
    fetchers = {
        "sleeper_dynasty_2qb": lambda: _fetch_sleeper_adp(
            season=season,
            stat_key="adp_dynasty_2qb",
            order_by="adp_dynasty_2qb",
            label=f"Sleeper dynasty 2QB ADP ({season})",
        ),
        "sleeper_dynasty_1qb": lambda: _fetch_sleeper_adp(
            season=season,
            stat_key="adp_dynasty_half_ppr",
            order_by="adp_dynasty_half_ppr",
            label=f"Sleeper dynasty 1QB ADP ({season})",
        ),
        "sleeper_redraft_half_ppr": lambda: _fetch_sleeper_adp(
            season=season,
            stat_key="adp_half_ppr",
            order_by="adp_half_ppr",
            label=f"Sleeper redraft half-PPR ADP ({season})",
        ),
        "beatadp_sleeper": _fetch_beatadp_sleeper,
        "dlf_superflex": _fetch_dlf_superflex,
    }
    if source not in fetchers:
        resolved = _resolve_source("auto", superflex=superflex)
        source = resolved
    rows, label = fetchers[source]()
    return rows, label


def _session() -> requests.Session:
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    return session


def _fetch_sleeper_adp(
    *,
    season: str,
    stat_key: str,
    order_by: str,
    label: str,
) -> tuple[list[dict[str, Any]], str]:
    url = SLEEPER_PROJECTIONS_URL.format(season=season, order_by=order_by)
    response = _session().get(url, timeout=60)
    response.raise_for_status()
    rows: list[dict[str, Any]] = []
    for row in response.json():
        stats = row.get("stats") or {}
        adp = stats.get(stat_key)
        if adp is None or float(adp) >= _ADP_MISSING:
            continue
        player = row.get("player") or {}
        name = f"{player.get('first_name', '')} {player.get('last_name', '')}".strip()
        if not name:
            continue
        adp_f = float(adp)
        rows.append(
            {
                "name": name,
                "pos": player.get("position") or "",
                "adp": adp_f,
                "pick": max(1, round(adp_f)),
            }
        )
    if not rows:
        raise RuntimeError(f"Sleeper ADP fetch returned no rows for {stat_key}")
    return rows, label


def _fetch_beatadp_sleeper() -> tuple[list[dict[str, Any]], str]:
    response = _session().get(BEATADP_SLEEPER_URL, timeout=45)
    response.raise_for_status()
    rows: list[dict[str, Any]] = []
    for chunk in re.findall(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)', response.text):
        text = bytes(chunk, "utf-8").decode("unicode_escape", errors="replace")
        for match in _BEATADP_ROW_RE.finditer(text):
            name, pos, adps_raw, _consensus = match.groups()
            adps = json.loads(adps_raw.replace('\\"', '"'))
            sleeper = adps.get("SLEEPER")
            if sleeper is None:
                continue
            adp = float(sleeper)
            rows.append(
                {
                    "name": name,
                    "pos": pos,
                    "adp": adp,
                    "pick": max(1, round(adp)),
                }
            )
    return rows, "BeatADP Sleeper redraft ADP"


def _fetch_dlf_superflex() -> tuple[list[dict[str, Any]], str]:
    response = _session().get(
        DLF_SUPERFLEX_URL,
        timeout=45,
        headers={
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    response.raise_for_status()
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for rank, adp_raw, name in _DLF_ROW_RE.findall(response.text):
        name = name.strip()
        if not name or name.startswith("!") or "http" in name.lower():
            continue
        key = normalize_name(name)
        if key in seen:
            continue
        seen.add(key)
        adp = float(adp_raw)
        rows.append(
            {
                "name": name,
                "rank": int(rank),
                "adp": adp,
                "pick": max(1, round(adp)),
            }
        )
    if len(rows) < 50:
        raise RuntimeError(f"DLF superflex parse returned only {len(rows)} rows")
    return rows, "DLF superflex startup mock ADP"


def _load_csv(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            return rows
        fields = {name.strip().lower(): name for name in reader.fieldnames}
        name_key = fields.get("player") or fields.get("name")
        adp_key = fields.get("adp") or fields.get("pick") or fields.get("avg") or fields.get("average")
        if not name_key or not adp_key:
            raise ValueError("ADP CSV needs Player/name and ADP/pick columns")
        pos_key = fields.get("pos") or fields.get("position")
        for row in reader:
            name = (row.get(name_key) or "").strip()
            adp_raw = (row.get(adp_key) or "").strip()
            if not name or not adp_raw:
                continue
            adp = float(re.sub(r"[^0-9.]", "", adp_raw) or adp_raw)
            entry: dict[str, Any] = {
                "name": name,
                "adp": adp,
                "pick": max(1, round(adp)),
            }
            if pos_key:
                entry["pos"] = (row.get(pos_key) or "").strip()
            rows.append(entry)
    return rows
