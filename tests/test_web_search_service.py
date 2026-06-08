"""Tests for Brave-backed advisor web search (mocked HTTP — no live API)."""

from unittest.mock import MagicMock

import requests

from backend.services.web_search_service import (
    MAX_HITS,
    parse_brave_web_results,
    search_web,
)


BRAVE_FIXTURE = {
    "web": {
        "results": [
            {
                "title": "Chiefs WR injury update",
                "url": "https://example.com/chiefs-injury",
                "description": "Rashee Rice limited in practice Wednesday.",
                "page_age": "2025-06-05T14:00:00",
            },
            {
                "title": "No URL row",
                "description": "should skip",
            },
            {
                "title": "Beat report",
                "url": "https://example.com/beat",
                "description": "Expected return Week 1.",
                "age": "2 days ago",
            },
        ]
    }
}


def test_parse_brave_web_results_maps_fields_and_caps():
    hits = parse_brave_web_results(BRAVE_FIXTURE, limit=2)
    assert len(hits) == 2
    assert hits[0] == {
        "title": "Chiefs WR injury update",
        "url": "https://example.com/chiefs-injury",
        "snippet": "Rashee Rice limited in practice Wednesday.",
        "published_at": "2025-06-05T14:00:00",
    }
    assert hits[1]["published_at"] == "2 days ago"
    assert hits[1]["snippet"] == "Expected return Week 1."


def test_search_web_not_configured():
    result = search_web("Ja'Marr Chase injury", api_key=None)
    assert result["configured"] is False
    assert result["query"] == "Ja'Marr Chase injury"
    assert result["results"] == []
    assert "BRAVE_API_KEY" in result["note"]


def test_search_web_short_query_when_configured():
    result = search_web("x", api_key="test-key")
    assert result["configured"] is True
    assert result["results"] == []
    assert "2 characters" in result["note"]


def test_search_web_success_mocked():
    session = MagicMock()
    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.return_value = BRAVE_FIXTURE
    session.get.return_value = response

    result = search_web(
        "Rashee Rice injury",
        api_key="test-key",
        session=session,
    )

    assert result["configured"] is True
    assert len(result["results"]) == 2
    session.get.assert_called_once()
    call_kwargs = session.get.call_args
    assert call_kwargs.args[0].endswith("/web/search")
    assert call_kwargs.kwargs["params"]["q"] == "Rashee Rice injury"
    assert call_kwargs.kwargs["params"]["count"] == MAX_HITS
    assert call_kwargs.kwargs["headers"]["X-Subscription-Token"] == "test-key"


def test_search_web_http_error_mocked():
    session = MagicMock()
    session.get.side_effect = requests.HTTPError("429 Too Many Requests")

    result = search_web("player news", api_key="test-key", session=session)

    assert result["configured"] is True
    assert result["results"] == []
    assert "error" in result
    assert "failed" in result["note"].lower()
