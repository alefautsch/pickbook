"""Tests for LLM usage logging."""

from unittest.mock import MagicMock

from backend.services.llm_usage import (
    DEFAULT_VALIDATION_MODEL,
    estimate_cost_usd,
    get_usage_log,
    reset_usage_log,
    usage_summary,
    create_message,
)


def test_estimate_cost_usd():
    # Sonnet: 1M in + 100k out
    cost = estimate_cost_usd("claude-sonnet-4-6", 1_000_000, 100_000)
    assert round(cost, 2) == 4.50


def test_create_message_logs_usage():
    reset_usage_log()
    mock_usage = MagicMock(input_tokens=1200, output_tokens=80)
    mock_response = MagicMock(usage=mock_usage)
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_response

    create_message(
        mock_client,
        feature="trade_validation",
        model=DEFAULT_VALIDATION_MODEL,
        max_tokens=100,
        messages=[{"role": "user", "content": "hi"}],
    )

    log = get_usage_log()
    assert len(log) == 1
    assert log[0].feature == "trade_validation"
    assert log[0].model == DEFAULT_VALIDATION_MODEL
    assert log[0].input_tokens == 1200
    assert log[0].output_tokens == 80

    summary = usage_summary()
    assert summary["calls"] == 1
    assert summary["input_tokens"] == 1200
    assert "trade_validation" in summary["by_feature"]
