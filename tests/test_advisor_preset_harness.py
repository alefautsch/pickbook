"""Tests for deterministic advisor preset harness."""

from unittest.mock import MagicMock

from backend.services.advisor_preset_harness import (
    HARNESS_PRESET_IDS,
    _compact_package,
    run_preset_harness,
)


def test_harness_preset_ids_cover_all_prompts():
    from dynasty_draft.llm_advisor import INSEASON_ADVISOR_PROMPTS

    prompt_ids = {row["id"] for row in INSEASON_ADVISOR_PROMPTS}
    assert prompt_ids == HARNESS_PRESET_IDS


def test_compact_package_shapes_trade_assets():
    pkg = {
        "counterparty": {"roster_id": "2", "team_name": "Rivals", "direction": "sell"},
        "give": {
            "players": [{"player_id": "a", "name": "Alpha", "position": "WR", "ovr": 72, "tv": 4000}],
            "picks": [],
        },
        "receive": {
            "players": [{"player_id": "b", "name": "Beta", "position": "RB", "ovr": 80, "tv": 5500}],
            "picks": [{"label": "2027 1st", "trade_value": 3000}],
        },
        "fairness": "fair",
        "net_delta_adjusted_pct": 1.2,
        "package_quality": 7.5,
        "rationale": "WR depth swap",
    }
    compact = _compact_package(pkg)
    assert compact["counterparty"] == "Rivals"
    assert compact["give"][0]["name"] == "Alpha"
    assert compact["receive"][1]["pick"] == "2027 1st"


def test_run_suggest_trade_targets_focus_when_viewing_opponent():
    tools = MagicMock()
    tools.suggest_trades.return_value = {"packages": [], "trade_surplus_summary": {}}
    context = {"focused_team": {"viewing_opponent": True}}

    from backend.services.advisor_preset_harness import _run_suggest_trade

    _run_suggest_trade(
        tools,
        context,
        my_roster_id="3",
        focus_id="9",
        params={},
    )
    tools.suggest_trades.assert_called_once_with(target_roster_id="9", rank_by_validation=False)

    tools.suggest_trades.reset_mock()
    context["focused_team"]["viewing_opponent"] = False
    _run_suggest_trade(
        tools,
        context,
        my_roster_id="3",
        focus_id="9",
        params={},
    )
    tools.suggest_trades.assert_called_once_with(target_roster_id=None, rank_by_validation=False)


def test_run_preset_harness_dispatches():
    tools = MagicMock()
    tools.suggest_trades.return_value = {"packages": [], "trade_surplus_summary": {}}
    context = {"focused_team": {"viewing_opponent": False}}

    payload = run_preset_harness(
        "suggest_trade",
        tools,
        context,
        my_roster_id="3",
        focus_id="3",
    )

    assert payload["preset_id"] == "suggest_trade"
    assert payload["intent"] == "suggest_trade"
    assert payload["harness"] == "intent_v1"
    tools.suggest_trades.assert_called_once()
