"""Tests for counterparty trade validation."""

import json
from unittest.mock import MagicMock, patch

from backend.services.trade_validation_service import (
    ACCEPT_LIKELIHOOD_SCORE,
    build_validation_payload,
    validate_trade_with_llm,
    validation_accept_score,
    _parse_validation_json,
)


def test_build_validation_payload_shapes_counterparty_context():
    payload = build_validation_payload(
        proposer_roster_id="1",
        counterparty_roster_id="2",
        proposer_team={
            "team_name": "Mine",
            "contender_tier": "contender",
            "dynasty_rank": 2,
            "surplus": [{"position": "WR"}],
            "needs": [{"position": "RB"}],
            "draft_picks": [{"label": "2027 1.12", "trade_value": 4200, "slot_tier": "late"}],
        },
        counterparty_team={
            "team_name": "Theirs",
            "contender_tier": "rebuild",
            "dynasty_rank": 10,
            "surplus": [{"position": "RB"}],
            "needs": [{"position": "WR"}],
            "players": [
                {
                    "name": "Stud RB",
                    "position": "RB",
                    "tv": 6800,
                    "hppg": 14.0,
                    "trade_tag": "core",
                }
            ],
            "draft_picks": [{"label": "2026 1.01", "trade_value": 10880, "slot_tier": "early"}],
        },
        give={
            "players": [{"name": "Depth WR", "position": "WR", "tv": 4200, "hppg": 5.0}],
            "picks": [],
        },
        receive={
            "players": [{"name": "Stud RB", "position": "RB", "tv": 6800, "hppg": 14.0}],
            "picks": [],
        },
        tv_evaluation={
            "give_total_tv": 4200,
            "receive_total_tv": 6800,
            "net_delta_adjusted_pct": -18.0,
            "fairness": "favors_counterparty",
            "within_band": False,
            "positional_notes": ["Receive 1 RB — fills a roster hole"],
        },
    )

    assert payload["counterparty"]["team_name"] == "Theirs"
    assert payload["trade_from_proposer_view"]["proposer_gives"]["players"][0]["name"] == "Depth WR"
    assert payload["deterministic_tv"]["fairness"] == "favors_counterparty"


def test_parse_validation_json_from_fenced_block():
    raw = """Here is the result:
```json
{"accept_likelihood": "low", "fairness_from_counterparty_view": "favors_you",
 "would_improve_their_roster": false, "reasoning": "TV short", "blockers": ["gap"],
 "suggested_tweak": "Add a pick"}
```
"""
    parsed = _parse_validation_json(raw)
    assert parsed["accept_likelihood"] == "low"
    assert parsed["blockers"] == ["gap"]


def test_validation_accept_score_bonuses_and_penalties():
    base = validation_accept_score(
        {
            "accept_likelihood": "medium",
            "fairness_from_counterparty_view": "fair",
            "would_improve_their_roster": False,
        }
    )
    assert base == ACCEPT_LIKELIHOOD_SCORE["medium"]

    improved = validation_accept_score(
        {
            "accept_likelihood": "high",
            "fairness_from_counterparty_view": "favors_them",
            "would_improve_their_roster": True,
        }
    )
    assert improved == 1.0  # capped at 1.0

    penalized = validation_accept_score(
        {
            "accept_likelihood": "low",
            "fairness_from_counterparty_view": "favors_you",
            "would_improve_their_roster": False,
        }
    )
    assert penalized == 0.0  # 0 - 0.08 floored at 0

    assert validation_accept_score({"skipped": True}) is None
    assert validation_accept_score({"error": "x"}) is None


def test_validate_trade_with_llm_skips_without_api_key():
    result = validate_trade_with_llm({"trade": True}, api_key=None)
    assert result["skipped"] is True
    assert "ANTHROPIC_API_KEY" in result["error"]


def test_validate_trade_with_llm_mocked():
    mock_response = MagicMock()
    mock_response.content = [
        MagicMock(
            type="text",
            text=json.dumps(
                {
                    "accept_likelihood": "medium",
                    "fairness_from_counterparty_view": "fair",
                    "would_improve_their_roster": True,
                    "reasoning": "Fills their WR need.",
                    "blockers": [],
                    "suggested_tweak": None,
                }
            ),
        )
    ]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_response

    with patch("backend.services.trade_validation_service.anthropic.Anthropic", return_value=mock_client):
        result = validate_trade_with_llm({"x": 1}, api_key="test-key")

    assert result["accept_likelihood"] == "medium"
    assert result["would_improve_their_roster"] is True
    mock_client.messages.create.assert_called_once()
