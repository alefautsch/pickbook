"""Counterparty-perspective trade validation via a focused LLM call."""

from __future__ import annotations

import json
import re
from typing import Any, Literal

import anthropic

from dynasty_draft.llm_advisor import DEFAULT_MODEL

AcceptLikelihood = Literal["low", "medium", "high"]
FairnessView = Literal["favors_them", "fair", "favors_you"]

_VALIDATION_SYSTEM = """You are a dynasty fantasy football trade analyst.
Evaluate whether a proposed trade would be ACCEPTED from the COUNTERPARTY manager's perspective.

You receive:
- Counterparty roster context (their team, needs, surplus, picks, contender window)
- Proposer context (the other manager)
- The trade package from the proposer's view (what proposer gives / receives)
- Deterministic TV fairness math (helpful but not decisive)

Rules:
- Counterparty GIVES what proposer RECEIVES and GETS what proposer GIVES.
- Rebuilders hoard early picks; contenders ship own late picks for win-now production.
- A trade can be TV-fair but still rejected if it doesn't fix their needs or hurts their window.
- Be specific: name positions, pick slots, and roster holes.

Respond with ONLY valid JSON (no markdown):
{
  "accept_likelihood": "low" | "medium" | "high",
  "fairness_from_counterparty_view": "favors_them" | "fair" | "favors_you",
  "would_improve_their_roster": true | false,
  "reasoning": "2-4 sentences",
  "blockers": ["short bullet", "..."],
  "suggested_tweak": "one concrete adjustment or null"
}
"""


def _compact_player(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": row.get("name") or row.get("player_name"),
        "position": row.get("position") or row.get("pos"),
        "tv": row.get("tv") or row.get("trade_value"),
        "hppg": row.get("hppg"),
        "ovr": row.get("ovr"),
        "age": row.get("age"),
        "trade_tag": row.get("trade_tag"),
        "lineup_delta_ppg": row.get("lineup_delta_ppg"),
    }


def _compact_pick(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "label": row.get("label"),
        "season": row.get("season"),
        "round": row.get("round"),
        "tv": row.get("trade_value") or row.get("tv"),
        "slot_tier": row.get("slot_tier"),
        "trade_tag": row.get("trade_tag"),
        "is_own_slot": row.get("is_own_slot"),
    }


def build_validation_payload(
    *,
    proposer_roster_id: str,
    counterparty_roster_id: str,
    proposer_team: dict[str, Any],
    counterparty_team: dict[str, Any],
    give: dict[str, Any],
    receive: dict[str, Any],
    tv_evaluation: dict[str, Any],
) -> dict[str, Any]:
    """Shape context for the validation LLM."""
    return {
        "proposer": {
            "roster_id": proposer_roster_id,
            "team_name": proposer_team.get("team_name"),
            "contender_tier": proposer_team.get("contender_tier"),
            "dynasty_rank": proposer_team.get("dynasty_rank"),
            "surplus": proposer_team.get("surplus") or [],
            "needs": proposer_team.get("needs") or [],
            "draft_picks": [
                _compact_pick(p) for p in (proposer_team.get("draft_picks") or [])[:8]
            ],
        },
        "counterparty": {
            "roster_id": counterparty_roster_id,
            "team_name": counterparty_team.get("team_name"),
            "contender_tier": counterparty_team.get("contender_tier"),
            "dynasty_rank": counterparty_team.get("dynasty_rank"),
            "surplus": counterparty_team.get("surplus") or [],
            "needs": counterparty_team.get("needs") or [],
            "top_players": [
                _compact_player(p)
                for p in (counterparty_team.get("players") or [])[:12]
            ],
            "draft_picks": [
                _compact_pick(p) for p in (counterparty_team.get("draft_picks") or [])[:8]
            ],
        },
        "trade_from_proposer_view": {
            "proposer_gives": {
                "players": [_compact_player(p) for p in give.get("players") or []],
                "picks": [_compact_pick(p) for p in give.get("picks") or []],
            },
            "proposer_receives": {
                "players": [_compact_player(p) for p in receive.get("players") or []],
                "picks": [_compact_pick(p) for p in receive.get("picks") or []],
            },
        },
        "deterministic_tv": {
            "give_total_tv": tv_evaluation.get("give_total_tv"),
            "receive_total_tv": tv_evaluation.get("receive_total_tv"),
            "net_delta_adjusted_pct": tv_evaluation.get("net_delta_adjusted_pct"),
            "fairness": tv_evaluation.get("fairness"),
            "within_band": tv_evaluation.get("within_band"),
            "consolidation_tax_tv": tv_evaluation.get("consolidation_tax_tv"),
            "positional_notes": tv_evaluation.get("positional_notes"),
        },
    }


def _parse_validation_json(text: str) -> dict[str, Any]:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", text)
        if match is None:
            raise ValueError("validation response was not JSON")
        return json.loads(match.group(0))


def _normalize_validation(parsed: dict[str, Any]) -> dict[str, Any]:
    likelihood = str(parsed.get("accept_likelihood") or "medium").lower()
    if likelihood not in ("low", "medium", "high"):
        likelihood = "medium"
    fairness = str(parsed.get("fairness_from_counterparty_view") or "fair").lower()
    if fairness not in ("favors_them", "fair", "favors_you"):
        fairness = "fair"
    blockers = parsed.get("blockers") or []
    if not isinstance(blockers, list):
        blockers = [str(blockers)]
    tweak = parsed.get("suggested_tweak")
    return {
        "accept_likelihood": likelihood,
        "fairness_from_counterparty_view": fairness,
        "would_improve_their_roster": bool(parsed.get("would_improve_their_roster")),
        "reasoning": str(parsed.get("reasoning") or "").strip(),
        "blockers": [str(b).strip() for b in blockers if str(b).strip()],
        "suggested_tweak": str(tweak).strip() if tweak else None,
    }


def validate_trade_with_llm(
    payload: dict[str, Any],
    *,
    api_key: str | None,
    model: str = DEFAULT_MODEL,
) -> dict[str, Any]:
    """Run counterparty-perspective validation. Requires Anthropic API key."""
    if not api_key or not api_key.strip():
        return {
            "error": "ANTHROPIC_API_KEY not configured — validation skipped",
            "skipped": True,
        }

    client = anthropic.Anthropic(api_key=api_key.strip())
    response = client.messages.create(
        model=model,
        max_tokens=900,
        system=_VALIDATION_SYSTEM,
        messages=[
            {
                "role": "user",
                "content": json.dumps(payload, indent=2, default=str),
            }
        ],
    )
    text_parts = [
        block.text for block in response.content if getattr(block, "type", None) == "text"
    ]
    raw_text = "".join(text_parts)
    parsed = _parse_validation_json(raw_text)
    return _normalize_validation(parsed)
