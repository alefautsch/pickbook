"""Brave Search API for advisor injury and roster news lookup."""

from __future__ import annotations

import logging
from typing import Any

import requests

logger = logging.getLogger(__name__)

BRAVE_WEB_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"
MAX_HITS = 5
REQUEST_TIMEOUT = 10


def is_web_search_configured(api_key: str | None) -> bool:
    return bool(api_key and api_key.strip())


def parse_brave_web_results(
    payload: dict[str, Any],
    *,
    limit: int = MAX_HITS,
) -> list[dict[str, Any]]:
    """Normalize Brave web search JSON into title/url/snippet/published_at hits."""
    results: list[dict[str, Any]] = []
    for row in (payload.get("web") or {}).get("results") or []:
        if not isinstance(row, dict):
            continue
        title = row.get("title")
        url = row.get("url")
        if not title or not url:
            continue
        hit: dict[str, Any] = {
            "title": str(title),
            "url": str(url),
            "snippet": str(row.get("description") or ""),
        }
        published_at = row.get("page_age") or row.get("age")
        if published_at:
            hit["published_at"] = str(published_at)
        results.append(hit)
        if len(results) >= limit:
            break
    return results


def search_web(
    query: str,
    *,
    api_key: str | None,
    limit: int = MAX_HITS,
    session: requests.Session | None = None,
) -> dict[str, Any]:
    """Run a Brave web search; degrades gracefully when unconfigured or on HTTP errors."""
    q = query.strip()
    base: dict[str, Any] = {"query": q, "results": []}

    if not is_web_search_configured(api_key):
        return {
            **base,
            "configured": False,
            "note": (
                "Web search is not configured. Set BRAVE_API_KEY to enable "
                "injury and roster news search."
            ),
        }

    if len(q) < 2:
        return {
            **base,
            "configured": True,
            "note": "query must be at least 2 characters",
        }

    http = session or requests.Session()
    try:
        response = http.get(
            BRAVE_WEB_SEARCH_URL,
            params={"q": q, "count": limit, "freshness": "pm"},
            headers={
                "Accept": "application/json",
                "Accept-Encoding": "gzip",
                "X-Subscription-Token": api_key.strip(),  # type: ignore[union-attr]
            },
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        hits = parse_brave_web_results(response.json(), limit=limit)
        return {"query": q, "configured": True, "results": hits}
    except requests.RequestException as exc:
        logger.warning("Brave web search failed: %s", exc)
        return {
            **base,
            "configured": True,
            "error": str(exc),
            "note": "Web search request failed; answer from league data only.",
        }
