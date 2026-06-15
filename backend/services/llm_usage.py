"""Anthropic call wrapper with token usage logging and cost estimates."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

import anthropic

logger = logging.getLogger(__name__)

DEFAULT_ADVISOR_MODEL = "claude-sonnet-4-6"
DEFAULT_VALIDATION_MODEL = "claude-haiku-4-5"

# USD per million tokens (approximate; used for benchmark estimates only).
MODEL_PRICING_PER_MTOK: dict[str, dict[str, float]] = {
    "claude-sonnet-4-6": {"input": 3.0, "output": 15.0},
    "claude-haiku-4-5": {"input": 0.80, "output": 4.0},
    "kimi-k2.6": {"input": 0.60, "output": 2.50},
}


@dataclass
class LlmUsageRecord:
    feature: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    tool_name: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def estimated_cost_usd(self) -> float:
        return estimate_cost_usd(self.model, self.input_tokens, self.output_tokens)


_usage_log: list[LlmUsageRecord] = []


def reset_usage_log() -> None:
    _usage_log.clear()


def get_usage_log() -> list[LlmUsageRecord]:
    return list(_usage_log)


def estimate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    rates = MODEL_PRICING_PER_MTOK.get(model) or MODEL_PRICING_PER_MTOK[DEFAULT_ADVISOR_MODEL]
    return (input_tokens * rates["input"] + output_tokens * rates["output"]) / 1_000_000


def _record_usage(
    *,
    feature: str,
    model: str,
    usage: Any,
    tool_name: str | None = None,
    extra: dict[str, Any] | None = None,
) -> LlmUsageRecord:
    input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
    output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
    row = LlmUsageRecord(
        feature=feature,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        tool_name=tool_name,
        extra=extra or {},
    )
    _usage_log.append(row)
    logger.info(
        "llm_usage feature=%s model=%s in=%s out=%s est_usd=%.4f tool=%s",
        feature,
        model,
        input_tokens,
        output_tokens,
        row.estimated_cost_usd,
        tool_name or "",
    )
    return row


def usage_summary() -> dict[str, Any]:
    """Aggregate logged usage for benchmarks and ops dashboards."""
    total_in = sum(r.input_tokens for r in _usage_log)
    total_out = sum(r.output_tokens for r in _usage_log)
    total_cost = sum(r.estimated_cost_usd for r in _usage_log)
    by_feature: dict[str, dict[str, Any]] = {}
    by_model: dict[str, dict[str, Any]] = {}
    for row in _usage_log:
        for bucket, key in ((by_feature, row.feature), (by_model, row.model)):
            slot = bucket.setdefault(
                key,
                {"calls": 0, "input_tokens": 0, "output_tokens": 0, "est_usd": 0.0},
            )
            slot["calls"] += 1
            slot["input_tokens"] += row.input_tokens
            slot["output_tokens"] += row.output_tokens
            slot["est_usd"] += row.estimated_cost_usd
    return {
        "calls": len(_usage_log),
        "input_tokens": total_in,
        "output_tokens": total_out,
        "estimated_cost_usd": round(total_cost, 4),
        "by_feature": by_feature,
        "by_model": by_model,
        "records": [
            {
                "feature": r.feature,
                "model": r.model,
                "input_tokens": r.input_tokens,
                "output_tokens": r.output_tokens,
                "estimated_cost_usd": round(r.estimated_cost_usd, 4),
                "tool_name": r.tool_name,
            }
            for r in _usage_log
        ],
    }


def create_message(
    client: anthropic.Anthropic,
    *,
    feature: str,
    model: str,
    tool_name: str | None = None,
    extra: dict[str, Any] | None = None,
    **kwargs: Any,
) -> anthropic.types.Message:
    """Non-streaming messages.create with usage logging."""
    response = client.messages.create(model=model, **kwargs)
    _record_usage(
        feature=feature,
        model=model,
        usage=response.usage,
        tool_name=tool_name,
        extra=extra,
    )
    return response


@contextmanager
def stream_message(
    client: anthropic.Anthropic,
    *,
    feature: str,
    model: str,
    tool_name: str | None = None,
    **kwargs: Any,
) -> Iterator[Any]:
    """Streaming messages.stream with usage logging on completion."""
    with client.messages.stream(model=model, **kwargs) as stream:
        yield stream
        try:
            final = stream.get_final_message()
            _record_usage(
                feature=feature,
                model=model,
                usage=final.usage,
                tool_name=tool_name,
            )
        except Exception:
            logger.exception("llm_usage: failed to read stream usage for %s", feature)
