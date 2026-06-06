from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from html import unescape
from typing import Any

import requests

from dynasty_draft.sleeper_client import CACHE_DIR
from dynasty_draft.war_data import normalize_name

KTC_TTL_SECONDS = 12 * 60 * 60
KTC_URL = (
    "https://keeptradecut.com/dynasty-rankings"
    "?page={page}&filters=QB|WR|RB|TE|RDP&format={format}"
)
USER_AGENT = "pickbook/0.3 (personal dynasty draft tool)"


def _cache_path(superflex: bool) -> Any:
    tag = "sf" if superflex else "1qb"
    return CACHE_DIR / f"ktc_dynasty_{tag}.json"


def _parse_page(html: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for block in html.split('class="onePlayer"')[1:]:
        name_m = re.search(r'class="player-name".*?<a[^>]*>([^<]+)</a>', block, re.S)
        team_m = re.search(r'class="player-team">([^<]+)</span>', block)
        pos_m = re.search(r'class="position-team".*?class="position">([^<]+)</p>', block, re.S)
        val_m = re.search(r'class="value">\s*<p>([^<]+)</p>', block)
        if not (name_m and val_m):
            continue
        pos_rank = unescape(pos_m.group(1).strip()) if pos_m else ""
        rows.append(
            {
                "name": unescape(name_m.group(1).strip()),
                "pos": pos_rank[:2] if pos_rank else "",
                "team": unescape(team_m.group(1).strip()) if team_m else "",
                "value": int(re.sub(r"[^0-9]", "", val_m.group(1))),
            }
        )
    return rows


def _fetch_dynasty(*, superflex: bool, max_pages: int = 10) -> list[dict[str, Any]]:
    """Scrape KTC dynasty rankings (format=0 SF, format=1 1QB)."""
    fmt = 0 if superflex else 1
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    by_name: dict[str, dict[str, Any]] = {}
    for page in range(max_pages):
        response = session.get(KTC_URL.format(page=page, format=fmt), timeout=45)
        response.raise_for_status()
        page_rows = _parse_page(response.text)
        if not page_rows:
            break
        for row in page_rows:
            by_name[row["name"]] = row
        if len(page_rows) < 50:
            break
        time.sleep(0.25)
    return list(by_name.values())


@dataclass
class KtcStore:
    superflex: bool
    by_name: dict[str, int]
    fetched_at: float

    def lookup(self, name: str) -> int | None:
        return self.by_name.get(normalize_name(name))

    @classmethod
    def from_rows(cls, rows: list[dict[str, Any]], *, superflex: bool, fetched_at: float) -> KtcStore:
        by_name: dict[str, int] = {}
        for row in rows:
            key = normalize_name(row["name"])
            if key and key not in by_name:
                by_name[key] = int(row["value"])
        return cls(superflex=superflex, by_name=by_name, fetched_at=fetched_at)

    @classmethod
    def load(
        cls,
        *,
        superflex: bool = True,
        force_refresh: bool = False,
        ttl_seconds: int = KTC_TTL_SECONDS,
    ) -> KtcStore:
        path = _cache_path(superflex)
        now = time.time()
        if not force_refresh and path.exists():
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                fetched_at = float(payload.get("fetched_at", 0))
                if now - fetched_at < ttl_seconds:
                    return cls.from_rows(
                        payload.get("players") or [],
                        superflex=superflex,
                        fetched_at=fetched_at,
                    )
            except (json.JSONDecodeError, OSError, TypeError, ValueError):
                pass

        rows = _fetch_dynasty(superflex=superflex)
        fetched_at = time.time()
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "fetched_at": fetched_at,
                    "superflex": superflex,
                    "players": rows,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return cls.from_rows(rows, superflex=superflex, fetched_at=fetched_at)
