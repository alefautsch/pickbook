"""Counterparty-perspective trade validation via a focused LLM call."""

from __future__ import annotations

import json
import re
from typing import Any, Literal

import anthropic

from dynasty_draft.llm_advisor import DEFAULT_MODEL

AcceptLikelihood = Literal["low", "medium", "high"]
FairnessView = Literal["favors_them", "fair", "favors_you"]

ACCEPT_LIKELIHOOD_SCORE: dict[str, float] = {
    "low": 0.0,
    "medium": 0.55,
    "high": 1.0,
}


def validation_accept_score(validation: dict[str, Any]) -> float | None:
    """Scalar for ranking packages by counterparty accept likelihood."""
    if validation.get("skipped") or validation.get("error"):
        return None
    likelihood = str(validation.get("accept_likelihood") or "medium").lower()
    score = ACCEPT_LIKELIHOOD_SCORE.get(likelihood, 0.55)
    if validation.get("would_improve_their_roster"):
        score += 0.12
    fairness = str(validation.get("fairness_from_counterparty_view") or "fair").lower()
    if fairness == "favors_them":
        score += 0.05
    elif fairness == "favors_you":
        score -= 0.08
    return round(min(1.0, max(0.0, score)), 3)


_VALIDATION_SYSTEM = """You are a dynasty fantasy football trade analyst.
Evaluate whether review_for_team would ACCEPT this trade if it were offered to them.

You receive:
- review_for_team: the manager judging the trade (their roster, needs, surplus, window)
- the_other_team: the other manager in the deal
- trade_from_proposer_view: package orientation (see Rules below)
- Per-asset depth context (lineup_delta_ppg = marginal PPG lost if that player is moved)
- Post-trade ideal starter lineup impact for both sides (starter_ppg_before/after/delta, changed slots)
- counterparty_tv: TV math from review_for_team's perspective (authoritative for fairness)

Rules:
- review_for_team is always the "counterparty" block in the payload.
- review_for_team GIVES what the other manager receives and GETS what the other manager gives.
- Judge objectively: would review_for_team accept this package given their roster situation?
- In reasoning and blockers, use team_name fields only — never say "counterparty", "proposer", "you", or "they".
- Use counterparty_tv for all TV delta/fairness statements — never invert it.
- counterparty_tv.net_tv_delta positive = review_for_team receives MORE total TV (favors review_for_team).
- counterparty_tv.net_tv_delta negative = review_for_team receives LESS total TV (favors the other manager).
- fairness_from_counterparty_view: favors_them = favors review_for_team; favors_you = favors the other manager.
- Only cite players and picks explicitly listed in the trade payload — do not substitute other names.
- Rebuilders hoard early picks; contenders ship surplus picks/depth for win-now production.
- A trade can be TV-lopsided but still accepted when it fixes a critical need from surplus depth.
- For contenders, weigh starter_ppg_delta heavily: a large positive delta at a need position can justify TV overpay.
- For rebuilders, negative starter_ppg_delta is acceptable when acquiring youth/picks; positive delta is a bonus.
- If review_for_team's lineup_impact shows new incoming starters or materially higher starter PPG, that supports acceptance.
- Be specific: name players, positions, pick slots, PPG deltas, and roster holes.

Respond with ONLY valid JSON (no markdown):
{
  "accept_likelihood": "low" | "medium" | "high",
  "fairness_from_counterparty_view": "favors_them" | "fair" | "favors_you",
  "would_improve_their_roster": true | false,
  "reasoning": "2-4 sentences about review_for_team by name",
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
        "depth_rank": row.get("depth_rank"),
        "lineup_delta_ppg": row.get("lineup_delta_ppg"),
    }


def _player_roster_index(team: dict[str, Any]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for row in team.get("players") or []:
        pid = row.get("player_id")
        if pid:
            index[str(pid)] = row
    return index


def _enrich_trade_players(
    players: list[dict[str, Any]],
    roster_index: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for player in players:
        row = dict(player)
        pid = str(row.get("player_id") or "")
        roster_row = roster_index.get(pid) if pid else None
        if roster_row:
            for key in ("lineup_delta_ppg", "trade_tag", "depth_rank", "age", "hppg", "ovr"):
                if row.get(key) is None and roster_row.get(key) is not None:
                    row[key] = roster_row.get(key)
        enriched.append(_compact_player(row))
    return enriched


def _compact_lineup_starter(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "slot": row.get("slot"),
        "name": row.get("name"),
        "position": row.get("position"),
        "ppg": row.get("ppg"),
        "ovr": row.get("ovr"),
        "is_incoming": bool(row.get("is_incoming")),
        "is_changed": bool(row.get("is_changed")),
    }


def _compact_lineup_side(side: dict[str, Any] | None) -> dict[str, Any] | None:
    if not side:
        return None
    return {
        "starter_ppg_before": side.get("before"),
        "starter_ppg_after": side.get("after"),
        "starter_ppg_delta": side.get("delta"),
        "post_trade_starters": [
            _compact_lineup_starter(slot) for slot in (side.get("starters") or [])
        ],
        "incoming_picks": [
            _compact_pick(pick) for pick in (side.get("incoming_picks") or [])
        ],
    }


def _compact_team_context(team: dict[str, Any]) -> dict[str, Any]:
    return {
        "team_name": team.get("team_name"),
        "contender_tier": team.get("contender_tier"),
        "dynasty_rank": team.get("dynasty_rank"),
        "starter_total_ppg": team.get("starter_total_ppg"),
        "surplus": team.get("surplus") or [],
        "needs": team.get("needs") or [],
        "starter_needs": team.get("starter_needs") or [],
        "draft_picks": [
            _compact_pick(pick) for pick in (team.get("draft_picks") or [])[:8]
        ],
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


def _counterparty_tv_summary(
    give: dict[str, Any],
    receive: dict[str, Any],
    tv_evaluation: dict[str, Any],
    *,
    proposer_index: dict[str, dict[str, Any]],
    counterparty_index: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Flip proposer-centric TV math into explicit counterparty perspective."""
    proposer_gives = float(tv_evaluation.get("give_total_tv") or 0)
    proposer_receives = float(tv_evaluation.get("receive_total_tv") or 0)
    proposer_gives_adj = float(tv_evaluation.get("give_adjusted_tv") or 0)
    proposer_receives_adj = float(tv_evaluation.get("receive_adjusted_tv") or 0)

    cp_gives = proposer_receives
    cp_receives = proposer_gives
    cp_gives_adj = proposer_receives_adj
    cp_receives_adj = proposer_gives_adj

    net_raw = cp_receives - cp_gives
    net_adj = cp_receives_adj - cp_gives_adj
    net_adj_total = -float(tv_evaluation.get("net_delta_adjusted_total_tv") or 0)

    fairness = str(tv_evaluation.get("fairness") or "fair")
    if tv_evaluation.get("within_band"):
        tv_favors = "fair"
    elif net_adj_total > 0:
        tv_favors = "counterparty"
    elif net_adj_total < 0:
        tv_favors = "proposer"
    else:
        tv_favors = "fair" if fairness == "fair" else (
            "counterparty" if fairness == "favors_counterparty" else "proposer"
        )

    return {
        "counterparty_gives": {
            "players": _enrich_trade_players(
                receive.get("players") or [],
                counterparty_index,
            ),
            "picks": [_compact_pick(pick) for pick in receive.get("picks") or []],
            "total_tv": round(cp_gives, 2),
            "adjusted_tv": round(cp_gives_adj, 2),
        },
        "counterparty_receives": {
            "players": _enrich_trade_players(
                give.get("players") or [],
                proposer_index,
            ),
            "picks": [_compact_pick(pick) for pick in give.get("picks") or []],
            "total_tv": round(cp_receives, 2),
            "adjusted_tv": round(cp_receives_adj, 2),
        },
        "net_tv_delta": round(net_raw, 2),
        "net_adjusted_tv_delta": round(net_adj, 2),
        "net_adjusted_total_tv_delta": round(net_adj_total, 2),
        "net_adjusted_total_tv_pct": round(
            -float(tv_evaluation.get("net_delta_adjusted_pct") or 0), 2
        ),
        "tv_favors": tv_favors,
        "within_band": tv_evaluation.get("within_band"),
        "consolidation_tax_tv": tv_evaluation.get("consolidation_tax_tv"),
        "proposer_pays_consolidation_tax": bool(tv_evaluation.get("receive_consolidating")),
    }


def _fairness_label_for_counterparty(
    fairness: str | None,
    *,
    counterparty_name: str,
    proposer_name: str,
) -> str:
    key = str(fairness or "fair").lower()
    cp = counterparty_name or "them"
    prop = proposer_name or "opponent"
    if key == "favors_them":
        return f"Favors {cp}"
    if key == "favors_you":
        return f"Favors {prop}"
    return "Fair"


def build_validation_payload(
    *,
    proposer_roster_id: str,
    counterparty_roster_id: str,
    proposer_team: dict[str, Any],
    counterparty_team: dict[str, Any],
    give: dict[str, Any],
    receive: dict[str, Any],
    tv_evaluation: dict[str, Any],
    proposer_lineup: dict[str, Any] | None = None,
    counterparty_lineup: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Shape context for the validation LLM."""
    proposer_index = _player_roster_index(proposer_team)
    counterparty_index = _player_roster_index(counterparty_team)

    payload: dict[str, Any] = {
        "review_for_team": counterparty_team.get("team_name") or counterparty_roster_id,
        "the_other_team": proposer_team.get("team_name") or proposer_roster_id,
        "proposer": {
            "roster_id": proposer_roster_id,
            **_compact_team_context(proposer_team),
        },
        "counterparty": {
            "roster_id": counterparty_roster_id,
            **_compact_team_context(counterparty_team),
            "top_players": [
                _compact_player(player)
                for player in (counterparty_team.get("players") or [])[:12]
            ],
        },
        "trade_from_proposer_view": {
            "proposer_gives": {
                "players": _enrich_trade_players(
                    give.get("players") or [],
                    proposer_index,
                ),
                "picks": [_compact_pick(pick) for pick in give.get("picks") or []],
            },
            "proposer_receives": {
                "players": _enrich_trade_players(
                    receive.get("players") or [],
                    counterparty_index,
                ),
                "picks": [_compact_pick(pick) for pick in receive.get("picks") or []],
            },
        },
        "counterparty_tv": _counterparty_tv_summary(
            give,
            receive,
            tv_evaluation,
            proposer_index=proposer_index,
            counterparty_index=counterparty_index,
        ),
        "deterministic_tv": {
            "_note": "Proposer-centric. Prefer counterparty_tv for accept/reject reasoning.",
            "tv_fairness_grade": tv_evaluation.get("tv_fairness_grade"),
            "give_total_tv": tv_evaluation.get("give_total_tv"),
            "receive_total_tv": tv_evaluation.get("receive_total_tv"),
            "give_adjusted_tv": tv_evaluation.get("give_adjusted_tv"),
            "receive_adjusted_tv": tv_evaluation.get("receive_adjusted_tv"),
            "give_effective_tv": tv_evaluation.get("give_effective_tv"),
            "receive_effective_tv": tv_evaluation.get("receive_effective_tv"),
            "net_delta_tv": tv_evaluation.get("net_delta_tv"),
            "net_delta_adjusted_tv": tv_evaluation.get("net_delta_adjusted_tv"),
            "net_delta_effective_tv": tv_evaluation.get("net_delta_effective_tv"),
            "net_delta_adjusted_total_tv": tv_evaluation.get("net_delta_adjusted_total_tv"),
            "net_delta_pct": tv_evaluation.get("net_delta_pct"),
            "net_delta_adjusted_pct": tv_evaluation.get("net_delta_adjusted_pct"),
            "fairness": tv_evaluation.get("fairness"),
            "within_band": tv_evaluation.get("within_band"),
            "fairness_band": tv_evaluation.get("fairness_band"),
            "consolidation_tax_tv": tv_evaluation.get("consolidation_tax_tv"),
            "consolidation_premium_pct": tv_evaluation.get("consolidation_premium_pct"),
            "give_consolidating": tv_evaluation.get("give_consolidating"),
            "receive_consolidating": tv_evaluation.get("receive_consolidating"),
            "positional_notes": tv_evaluation.get("positional_notes"),
        },
    }

    lineup_impact: dict[str, Any] = {}
    counterparty_lineup_compact = _compact_lineup_side(counterparty_lineup)
    proposer_lineup_compact = _compact_lineup_side(proposer_lineup)
    if counterparty_lineup_compact is not None:
        lineup_impact["counterparty"] = counterparty_lineup_compact
    if proposer_lineup_compact is not None:
        lineup_impact["proposer"] = proposer_lineup_compact
    if lineup_impact:
        payload["lineup_impact"] = lineup_impact

    return payload


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
