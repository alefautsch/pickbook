"""Regression: Egbuka + 2026 1.06 for Judkins — University Terrace style inventory."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from backend.services.trade_validation_service import (
    build_fix_payload,
    suggest_trade_fix_with_llm,
    _sanitize_fix_against_inventory,
    _sanitize_fix_tv_claims,
)

# bruno offers Egbuka + 1.06, receives Judkins. Pick stays on bruno's give side.
# bruno's owned 2026 firsts: 1.04 and 1.06 only — no 1.08, and 1.04 is higher TV than 1.06.
BRUNO = "bruno caboclo"
FOURCHAN = "4chan Achane 5head"

EGBUKA = {"name": "Emeka Egbuka", "position": "WR", "tv": 4279, "trade_value": 4279}
JUDKINS = {"name": "Quinshon Judkins", "position": "RB", "tv": 3698, "trade_value": 3698}
PICK_104 = {"label": "2026 1.04", "season": "2026", "round": 1, "tv": 6087, "trade_value": 6087}
PICK_106 = {"label": "2026 1.06", "season": "2026", "round": 1, "tv": 4684, "trade_value": 4684}
PICK_203 = {"label": "2026 2.03", "season": "2026", "round": 2, "tv": 2100, "trade_value": 2100}


def _bruno_team() -> dict:
    return {
        "team_name": BRUNO,
        "contender_tier": "contender",
        "players": [EGBUKA],
        "draft_picks": [PICK_106, PICK_104],
        "needs": [{"position": "RB"}],
        "surplus": [{"position": "WR"}],
    }


def _fourchan_team() -> dict:
    return {
        "team_name": FOURCHAN,
        "contender_tier": "rebuild",
        "players": [JUDKINS],
        "draft_picks": [PICK_104, PICK_106, PICK_203],
        "needs": [{"position": "WR"}],
        "surplus": [{"position": "RB"}],
    }


def _fix_payload() -> dict:
    return build_fix_payload(
        side_a_team=_bruno_team(),
        side_b_team=_fourchan_team(),
        give={"players": [EGBUKA], "picks": [PICK_106]},
        receive={"players": [JUDKINS], "picks": []},
        tv_evaluation={
            "give_total_tv": 4279 + 4684,
            "receive_total_tv": 3698,
            "give_adjusted_tv": 4279 + 4684,
            "receive_adjusted_tv": 3698,
            "net_delta_adjusted_pct": 12.0,
            "net_delta_adjusted_total_tv": 5265,
            "within_band": False,
        },
        side_a_validation={
            "accept_likelihood": "low",
            "blockers": ["TV gap"],
            "suggested_tweak": "Remove 1.06 or ask 4chan to add capital",
        },
        side_b_validation={
            "accept_likelihood": "medium",
            "blockers": [],
            "suggested_tweak": None,
        },
    )


def _sanitize(fix: dict, payload: dict) -> dict:
    after_roles = _sanitize_fix_against_inventory(
        fix,
        tradable_inventory=payload["tradable_inventory"],
        trade_package=payload["trade_package"],
    )
    return _sanitize_fix_tv_claims(
        after_roles,
        tv_catalog=payload["pick_tv_catalog"],
    )


def test_bruno_egbuka_106_for_judkins_pick_on_bruno_side():
    payload = _fix_payload()
    assert payload["picks_given_in_trade"][BRUNO] == ["2026 1.06"]
    assert payload["picks_given_in_trade"][FOURCHAN] == []
    pkg = payload["trade_package"]
    assert pkg[BRUNO]["gives"]["picks"][0]["label"] == "2026 1.06"
    assert pkg[FOURCHAN]["gives"]["picks"] == []


def test_bruno_has_no_valid_first_downgrade_in_payload():
    """1.04 is higher TV than 1.06; bruno does not own 1.08."""
    payload = _fix_payload()
    assert payload["pick_downgrade_options"][BRUNO] == []
    assert "2026 1.04" in payload["tradable_inventory"][BRUNO]["pick_labels"]
    assert "2026 1.08" not in payload["tradable_inventory"][BRUNO]["pick_labels"]


def test_rejects_unowned_108_for_bruno():
    payload = _fix_payload()
    fix = {
        "headline": "Use 1.08",
        "reasoning": f"{BRUNO} swaps to 2026 1.08 to reduce overpay.",
        "adjustments": [
            f"{BRUNO} gives Emeka Egbuka + 2026 1.08 (instead of 2026 1.06); "
            f"receives Quinshon Judkins"
        ],
        "both_sides_likely_accept": True,
    }
    cleaned = _sanitize(fix, payload)
    assert cleaned["adjustments"] == []
    assert "1.08" in cleaned["reasoning"]


def test_rejects_104_upgrade_on_bruno_side():
    payload = _fix_payload()
    fix = {
        "headline": "Swap to 1.04",
        "reasoning": f"{BRUNO} replaces 2026 1.06 with 2026 1.04 to balance TV.",
        "adjustments": [
            f"{BRUNO} gives Emeka Egbuka + 2026 1.04 (instead of 2026 1.06); "
            f"receives Quinshon Judkins"
        ],
        "both_sides_likely_accept": True,
    }
    cleaned = _sanitize(fix, payload)
    assert cleaned["adjustments"] == []


def test_rejects_pick_moved_to_fourchan_side():
    payload = _fix_payload()
    fix = {
        "headline": "Swap pick on wrong team",
        "reasoning": f"{FOURCHAN} swaps 2026 1.06 for 2026 1.04.",
        "adjustments": [
            f"{FOURCHAN} gives Quinshon Judkins + 2026 1.04 (instead of 2026 1.06); "
            f"receives Emeka Egbuka"
        ],
        "both_sides_likely_accept": True,
    }
    cleaned = _sanitize(fix, payload)
    assert cleaned["adjustments"] == []
    assert "2026 1.06 is given by bruno caboclo" in cleaned["reasoning"]


def test_accepts_remove_pick_from_bruno_offer():
    """When no later first exists, drop the pick from bruno's Egbuka package."""
    payload = _fix_payload()
    fix = {
        "headline": "Drop the attached first",
        "reasoning": (
            f"{BRUNO} has no later 2026 first in inventory (only 1.04 and 1.06). "
            f"Remove 2026 1.06 from the offer — Egbuka straight up for Judkins."
        ),
        "adjustments": [
            f"{BRUNO} gives Emeka Egbuka only (remove 2026 1.06); receives Quinshon Judkins"
        ],
        "both_sides_likely_accept": True,
    }
    cleaned = _sanitize(fix, payload)
    assert len(cleaned["adjustments"]) == 1
    assert "remove 2026 1.06" in cleaned["adjustments"][0].lower()
    assert cleaned["both_sides_likely_accept"] is True


def test_accepts_fourchan_adds_owned_pick():
    """Other side can add a pick they own to balance."""
    payload = _fix_payload()
    fix = {
        "headline": "4chan adds a second",
        "reasoning": f"{FOURCHAN} adds owned 2026 2.03 to the Judkins side of the deal.",
        "adjustments": [
            f"{FOURCHAN} gives Quinshon Judkins + 2026 2.03; receives Emeka Egbuka + 2026 1.06"
        ],
        "both_sides_likely_accept": True,
    }
    cleaned = _sanitize(fix, payload)
    assert len(cleaned["adjustments"]) == 1
    assert "2026 2.03" in cleaned["adjustments"][0]


def test_end_to_end_remove_pick_when_no_downgrade():
    payload = _fix_payload()
    mock_response = MagicMock()
    mock_response.content = [
        MagicMock(
            type="text",
            text=json.dumps(
                {
                    "headline": "Remove 1.06 from bruno's offer",
                    "reasoning": (
                        f"{BRUNO} owns 1.04 and 1.06 only — no lower-TV first to substitute. "
                        "Drop 2026 1.06; Egbuka for Judkins is the realistic fix."
                    ),
                    "adjustments": [
                        f"{BRUNO} gives Emeka Egbuka only (remove 2026 1.06); "
                        f"receives Quinshon Judkins"
                    ],
                    "both_sides_likely_accept": True,
                }
            ),
        )
    ]

    with patch(
        "backend.services.trade_validation_service.create_message",
        return_value=mock_response,
    ):
        result = suggest_trade_fix_with_llm(payload, api_key="test-key")

    assert len(result["adjustments"]) == 1
    assert "remove 2026 1.06" in result["adjustments"][0].lower()
    assert result["both_sides_likely_accept"] is True


def test_end_to_end_rejects_invented_108():
    payload = _fix_payload()
    mock_response = MagicMock()
    mock_response.content = [
        MagicMock(
            type="text",
            text=json.dumps(
                {
                    "headline": "Swap to 1.08",
                    "reasoning": f"{BRUNO} uses 2026 1.08 instead of 1.06.",
                    "adjustments": [
                        f"{BRUNO} gives Emeka Egbuka + 2026 1.08 (instead of 2026 1.06); "
                        f"receives Quinshon Judkins"
                    ],
                    "both_sides_likely_accept": True,
                }
            ),
        )
    ]

    with patch(
        "backend.services.trade_validation_service.create_message",
        return_value=mock_response,
    ):
        result = suggest_trade_fix_with_llm(payload, api_key="test-key")

    assert result["adjustments"] == []
    assert result["both_sides_likely_accept"] is False
