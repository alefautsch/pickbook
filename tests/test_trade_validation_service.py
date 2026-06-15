"""Tests for counterparty trade validation."""

import json
from unittest.mock import MagicMock, patch

from backend.services.trade_validation_service import (
    ACCEPT_LIKELIHOOD_SCORE,
    build_fix_payload,
    build_validation_payload,
    suggest_trade_fix_with_llm,
    validate_trade_with_llm,
    validation_accept_score,
    _fairness_label_for_counterparty,
    _parse_validation_json,
    _sanitize_fix_against_inventory,
    _inverted_pick_swap_claim,
)


def test_build_validation_payload_shapes_counterparty_context():
    payload = build_validation_payload(
        proposer_roster_id="1",
        counterparty_roster_id="2",
        proposer_team={
            "team_name": "Mine",
            "contender_tier": "contender",
            "dynasty_rank": 2,
            "starter_total_ppg": 118.5,
            "surplus": [{"position": "WR"}],
            "needs": [{"position": "RB"}],
            "starter_needs": [{"position": "RB"}],
            "players": [
                {
                    "player_id": "wr-depth",
                    "name": "Depth WR",
                    "position": "WR",
                    "tv": 4200,
                    "hppg": 5.0,
                    "lineup_delta_ppg": 1.2,
                    "trade_tag": "trade",
                }
            ],
            "draft_picks": [{"label": "2027 1.12", "trade_value": 4200, "slot_tier": "late"}],
        },
        counterparty_team={
            "team_name": "Theirs",
            "contender_tier": "rebuild",
            "dynasty_rank": 10,
            "starter_total_ppg": 104.0,
            "surplus": [{"position": "RB"}],
            "needs": [{"position": "WR"}],
            "starter_needs": [{"position": "WR"}],
            "players": [
                {
                    "player_id": "rb-stud",
                    "name": "Stud RB",
                    "position": "RB",
                    "tv": 6800,
                    "hppg": 14.0,
                    "trade_tag": "core",
                    "lineup_delta_ppg": 9.5,
                }
            ],
            "draft_picks": [{"label": "2026 1.01", "trade_value": 10880, "slot_tier": "early"}],
        },
        give={
            "players": [
                {
                    "player_id": "wr-depth",
                    "name": "Depth WR",
                    "position": "WR",
                    "tv": 4200,
                    "hppg": 5.0,
                }
            ],
            "picks": [],
        },
        receive={
            "players": [
                {
                    "player_id": "rb-stud",
                    "name": "Stud RB",
                    "position": "RB",
                    "tv": 6800,
                    "hppg": 14.0,
                }
            ],
            "picks": [],
        },
        tv_evaluation={
            "tv_fairness_grade": "C+",
            "give_total_tv": 4200,
            "receive_total_tv": 6800,
            "give_adjusted_tv": 4200,
            "receive_adjusted_tv": 6800,
            "net_delta_adjusted_pct": 18.0,
            "net_delta_adjusted_total_tv": 2600,
            "fairness": "favors_you",
            "within_band": False,
            "positional_notes": ["Receive 1 RB — fills a roster hole"],
        },
        proposer_lineup={
            "before": 118.5,
            "after": 127.0,
            "delta": 8.5,
            "starters": [
                {
                    "slot": "RB",
                    "name": "Stud RB",
                    "position": "RB",
                    "ppg": 14.0,
                    "is_incoming": True,
                    "is_changed": True,
                }
            ],
            "incoming_picks": [],
        },
        counterparty_lineup={
            "before": 104.0,
            "after": 95.5,
            "delta": -8.5,
            "starters": [],
            "incoming_picks": [],
        },
    )

    assert payload["review_for_team"] == "Theirs"
    assert payload["the_other_team"] == "Mine"
    assert payload["review_for_team_context"]["starter_total_ppg"] == 104.0
    assert payload["review_for_team_trade"]["gives"]["players"][0]["lineup_delta_ppg"] == 9.5
    assert payload["review_for_team_trade"]["gets"]["players"][0]["lineup_delta_ppg"] == 1.2

    review_tv = payload["review_for_team_tv"]
    assert review_tv["gives"]["total_tv"] == 6800
    assert review_tv["gets"]["total_tv"] == 4200
    assert review_tv["net_tv_delta"] == -2600
    assert review_tv["tv_favors"] == "Mine"
    assert payload["lineup_impact"]["Theirs"]["starter_ppg_delta"] == -8.5
    assert payload["lineup_impact"]["Mine"]["starter_ppg_delta"] == 8.5
    assert payload["lineup_impact"]["Mine"]["post_trade_starters"][0]["is_incoming"] is True


def test_build_validation_payload_includes_rookie_draft_context():
    rookie_ctx = {
        "season": "2026",
        "picks_in_trade": [
            {
                "label": "2026 1.01",
                "projected_rookie": {"name": "Jeremiyah Love", "pos": "RB"},
            }
        ],
    }
    payload = build_validation_payload(
        proposer_roster_id="1",
        counterparty_roster_id="2",
        proposer_team={"team_name": "Mine", "players": [], "needs": [], "surplus": []},
        counterparty_team={"team_name": "Theirs", "players": [], "needs": [], "surplus": []},
        give={"players": [], "picks": []},
        receive={"players": [], "picks": []},
        tv_evaluation={"fairness": "fair", "within_band": True},
        rookie_draft_context=rookie_ctx,
    )
    assert payload["rookie_draft_context"]["picks_in_trade"][0]["projected_rookie"]["name"] == "Jeremiyah Love"


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

    with patch("backend.services.trade_validation_service.create_message", return_value=mock_response):
        result = validate_trade_with_llm({"x": 1}, api_key="test-key")

    assert result["accept_likelihood"] == "medium"
    assert result["would_improve_their_roster"] is True


def test_fairness_label_uses_team_names():
    assert _fairness_label_for_counterparty(
        "favors_them", counterparty_name="mcalver", proposer_name="sailboat"
    ) == "Favors mcalver"
    assert _fairness_label_for_counterparty(
        "favors_you", counterparty_name="mcalver", proposer_name="sailboat"
    ) == "Favors sailboat"


def test_build_fix_payload_includes_both_validations():
    payload = build_fix_payload(
        side_a_team={
            "team_name": "Alpha",
            "draft_picks": [
                {"label": "2026 1.04", "season": "2026", "round": 1, "trade_value": 7200},
            ],
        },
        side_b_team={
            "team_name": "Beta",
            "draft_picks": [
                {"label": "2026 1.06", "season": "2026", "round": 1, "trade_value": 6500},
            ],
        },
        give={"players": [], "picks": [{"label": "2026 1.01", "trade_value": 10800}]},
        receive={"players": [], "picks": []},
        tv_evaluation={
            "give_adjusted_tv": 10800,
            "receive_adjusted_tv": 6500,
            "net_delta_adjusted_pct": 8,
            "within_band": False,
        },
        side_a_validation={
            "accept_likelihood": "low",
            "blockers": ["TV gap"],
            "suggested_tweak": "Add a pick",
        },
        side_b_validation={
            "accept_likelihood": "high",
            "blockers": [],
            "suggested_tweak": None,
        },
    )
    assert payload["side_a_team"]["team_name"] == "Alpha"
    assert "Alpha" in payload["trade_package"]
    assert payload["side_a_validation"]["accept_likelihood"] == "low"
    assert payload["side_b_validation"]["accept_likelihood"] == "high"
    assert payload["tradable_inventory"]["Alpha"]["pick_labels"] == ["2026 1.04"]
    assert payload["tradable_inventory"]["Beta"]["pick_labels"] == ["2026 1.06"]
    assert payload["tv_by_side"]["Alpha"]["gives_adjusted_tv"] == 10800
    assert payload["tv_by_side"]["Beta"]["receives_adjusted_tv"] == 10800
    assert payload["pick_tv_catalog"]["2026 1.04"] == 7200


def test_inverted_pick_swap_claim_detects_backwards_tv_reasoning():
    catalog = {
        "2026 1.06": 2468.0,
        "2027 1st": 5619.0,
    }
    text = (
        "Swapping the 2026 1.06 (2468 TV) for bruno's 2027 1st (5619 TV) "
        "reduces immediate TV bleed by ~3,151."
    )
    warning = _inverted_pick_swap_claim(text, catalog)
    assert warning is not None
    assert "does not reduce bleed" in warning
    assert "3,151" in warning or "3,151" in warning.replace(",", "")


def test_sanitize_fix_drops_picks_not_owned():
    inventory = {
        "bruno caboclo": {"pick_labels": ["2026 1.04", "2026 1.06"]},
        "Jackson Nine": {"pick_labels": ["2027 2.01"]},
    }
    fix = {
        "headline": "Swap picks",
        "reasoning": "Balances TV for both sides.",
        "adjustments": [
            "bruno caboclo gives: Nico Collins, 2026 1.06, 2026 2.05 (instead of 1.04)",
            "Jackson Nine gives: Jahmyr Gibbs",
        ],
        "both_sides_likely_accept": True,
    }
    cleaned = _sanitize_fix_against_inventory(fix, tradable_inventory=inventory)
    assert cleaned["adjustments"] == ["Jackson Nine gives: Jahmyr Gibbs"]
    assert cleaned["both_sides_likely_accept"] is False
    assert "2.05" in cleaned["reasoning"] or "Removed suggestions" in cleaned["reasoning"]


def test_suggest_trade_fix_with_llm_mocked():
    mock_response = MagicMock()
    mock_response.content = [
        MagicMock(
            type="text",
            text=json.dumps(
                {
                    "headline": "Add late pick to balance",
                    "reasoning": "Beta needs more TV; Alpha can spare a 3rd.",
                    "adjustments": ["Alpha adds 2027 3rd"],
                    "both_sides_likely_accept": True,
                }
            ),
        )
    ]

    with patch("backend.services.trade_validation_service.create_message", return_value=mock_response):
        result = suggest_trade_fix_with_llm({"trade": True}, api_key="test-key")

    assert result["headline"] == "Add late pick to balance"
    assert result["both_sides_likely_accept"] is True
    assert result["adjustments"] == ["Alpha adds 2027 3rd"]
