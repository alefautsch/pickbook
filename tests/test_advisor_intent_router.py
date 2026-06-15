"""Tests for Haiku advisor intent router."""

import json
from unittest.mock import MagicMock, patch

from backend.services.advisor_intent_router import (
    ROUTER_INTENTS,
    _parse_router_json,
    classify_advisor_intent,
    prose_model_for_route,
)


def test_parse_router_json_strips_markdown():
    raw = '```json\n{"intent": "waiver", "prose_tier": "simple"}\n```'
    parsed = _parse_router_json(raw)
    assert parsed["intent"] == "waiver"
    assert parsed["prose_tier"] == "simple"


def test_parse_router_json_fallback_on_garbage():
    parsed = _parse_router_json("not json")
    assert parsed["intent"] == "general"


@patch("backend.services.advisor_intent_router.create_message")
def test_classify_advisor_intent(mock_create):
    mock_response = MagicMock()
    mock_response.content = [
        MagicMock(
            type="text",
            text=json.dumps(
                {
                    "intent": "player_lookup",
                    "prose_tier": "simple",
                    "player_query": "Trevor Lawrence",
                    "position": None,
                    "web_query": None,
                }
            ),
        )
    ]
    mock_create.return_value = mock_response

    route = classify_advisor_intent(
        "What's Trevor Lawrence worth in dynasty?",
        {"league_name": "Test League", "my_team": {"team_name": "Mine"}},
        api_key="test-key",
    )
    assert route["intent"] == "player_lookup"
    assert route["player_query"] == "Trevor Lawrence"
    assert route["router"] == "haiku_v1"


def test_prose_model_for_route_simple_uses_haiku():
    model = prose_model_for_route(
        {"intent": "player_lookup", "prose_tier": "simple"},
        default_model="claude-sonnet-4-6",
    )
    assert "haiku" in model


def test_prose_model_for_route_waiver_uses_sonnet():
    model = prose_model_for_route(
        {"intent": "waiver", "prose_tier": "simple"},
        default_model="claude-sonnet-4-6",
    )
    assert model == "claude-sonnet-4-6"


def test_prose_model_for_route_complex_uses_sonnet():
    model = prose_model_for_route(
        {"intent": "suggest_trade", "prose_tier": "complex"},
        default_model="claude-sonnet-4-6",
    )
    assert model == "claude-sonnet-4-6"


def test_router_intents_include_presets():
    from backend.services.advisor_preset_harness import HARNESS_PRESET_IDS

    assert HARNESS_PRESET_IDS.issubset(ROUTER_INTENTS)
