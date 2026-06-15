"""Haiku intent router for free-form advisor questions — DAG + single prose call."""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from typing import Any

import anthropic

from backend.config import get_settings
from backend.services.advisor_preset_harness import run_intent_harness, stream_harness_advisor
from backend.services.advisor_tools import AdvisorTools
from backend.services.llm_usage import DEFAULT_VALIDATION_MODEL, create_message
from dynasty_draft.llm_advisor import build_inseason_advisor_context

ROUTER_INTENTS = frozenset(
    {
        "suggest_trade",
        "trade_targets",
        "drop_candidates",
        "rookie_pick_prep",
        "waiver",
        "player_lookup",
        "team_review",
        "news",
        "general",
    }
)

_COMPLEX_INTENTS = frozenset(
    {
        "suggest_trade",
        "trade_targets",
        "drop_candidates",
        "rookie_pick_prep",
        "team_review",
        "waiver",
        "news",
    }
)

_ROUTER_SYSTEM = """You classify dynasty fantasy football in-season advisor questions.
Return ONLY valid JSON (no markdown):
{
  "intent": "<intent>",
  "prose_tier": "simple" | "complex",
  "player_query": "<player name substring or null>",
  "position": "<QB|RB|WR|TE or null>",
  "web_query": "<web search query or null>"
}

Intents (pick the best match):
- suggest_trade — trade package ideas, "who should I trade for"
- trade_targets — buy-low/sell-high managers to target this week
- drop_candidates — bench drops, who to cut
- rookie_pick_prep — rookie draft prep, pick strategy
- waiver — waiver adds, free agents, wire pickups
- player_lookup — one player's dynasty grade, TV, outlook, injury
- team_review — my roster outlook, depth, contender/rebuild lens
- news — breaking injury/news/practice report (time-sensitive)
- general — broad advice when nothing else fits

Rules:
- prose_tier=complex for trades, roster strategy, drop decisions, rookie prep, team_review
- prose_tier=simple for player_lookup, news, narrow waiver ("best TE on waivers")
- Extract player_query when a specific player is named
- Set position filter for position-specific waiver questions
- web_query only for news intent"""


def _parse_router_json(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {"intent": "general", "prose_tier": "complex"}
    if not isinstance(parsed, dict):
        return {"intent": "general", "prose_tier": "complex"}
    intent = str(parsed.get("intent") or "general").strip()
    if intent not in ROUTER_INTENTS:
        intent = "general"
    tier = str(parsed.get("prose_tier") or "complex").lower()
    if tier not in ("simple", "complex"):
        tier = "complex" if intent in _COMPLEX_INTENTS else "simple"
    return {
        "intent": intent,
        "prose_tier": tier,
        "player_query": parsed.get("player_query"),
        "position": parsed.get("position"),
        "web_query": parsed.get("web_query"),
    }


def classify_advisor_intent(
    user_question: str,
    context: dict[str, Any],
    *,
    api_key: str,
) -> dict[str, Any]:
    """Single Haiku call to pick intent + extraction params."""
    advisor_context = build_inseason_advisor_context(context)
    compact_ctx = {
        "league_name": advisor_context.get("league_name"),
        "focused_team": advisor_context.get("focused_team"),
        "my_team": advisor_context.get("my_team"),
        "page_context": advisor_context.get("page_context"),
    }
    client = anthropic.Anthropic(api_key=api_key.strip())
    response = create_message(
        client,
        feature="advisor_intent_router",
        model=get_settings().llm_validation_model or DEFAULT_VALIDATION_MODEL,
        max_tokens=220,
        system=_ROUTER_SYSTEM,
        messages=[
            {
                "role": "user",
                "content": (
                    f"Context:\n{json.dumps(compact_ctx, indent=2, default=str)}\n\n"
                    f"Question:\n{user_question.strip()}"
                ),
            }
        ],
    )
    text_parts = [
        block.text for block in response.content if getattr(block, "type", None) == "text"
    ]
    route = _parse_router_json("".join(text_parts))
    route["router"] = "haiku_v1"
    return route


def prose_model_for_route(route: dict[str, Any], *, default_model: str) -> str:
    intent = str(route.get("intent") or "")
    if intent in _COMPLEX_INTENTS or route.get("prose_tier") == "complex":
        return default_model
    return get_settings().llm_validation_model or DEFAULT_VALIDATION_MODEL


def stream_routed_advisor(
    context: dict[str, Any],
    tools: AdvisorTools,
    api_key: str,
    *,
    user_question: str,
    model: str,
    my_roster_id: str,
    focus_id: str,
) -> Iterator[str]:
    """Classify intent → run tool DAG → stream one prose response."""
    yield "⏳ Understanding your question…\n\n"
    route = classify_advisor_intent(user_question, context, api_key=api_key)
    intent = route["intent"]
    harness_payload = run_intent_harness(
        intent,
        tools,
        context,
        my_roster_id=my_roster_id,
        focus_id=focus_id,
        params=route,
    )
    prose_model = prose_model_for_route(route, default_model=model)
    yield f"_Route: {intent} ({prose_model})…_\n\n"
    yield from stream_harness_advisor(
        context,
        harness_payload,
        api_key,
        user_question=user_question,
        model=prose_model,
        feature="advisor_router",
    )
