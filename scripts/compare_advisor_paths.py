#!/usr/bin/env python3
"""Compare legacy tool-loop advisor vs Haiku router + harness on the same questions.

Usage:
  uv run python scripts/compare_advisor_paths.py --db
  uv run python scripts/compare_advisor_paths.py --db --question "Best waiver TE adds?"
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_LEAGUE = "1314731206859853824"
DEFAULT_ROSTER = "3"

SAMPLE_QUESTIONS = [
    "What trades make sense for my team right now?",
    "Who are the best waiver wire adds at TE this week?",
    "Should I drop Romeo Doubs for a younger WR on waivers?",
    "How does my roster stack up — am I contending or rebuilding?",
    "What's Trevor Lawrence's dynasty outlook in this league?",
]


def _collect_stream(chunks) -> str:
    return "".join(chunks)


def _run_path(
    db,
    *,
    league_id: str,
    roster_id: str,
    question: str,
    path: str,
    model_id: str,
) -> tuple[str, dict[str, Any]]:
    from backend.config import get_settings
    from backend.services.advisor_service import stream_advisor_chat
    from backend.services.advisor_tools import ADVISOR_TOOL_SPECS, AdvisorToolContext, AdvisorTools
    from backend.services.llm_usage import reset_usage_log, usage_summary
    from dynasty_draft.llm_advisor import stream_inseason_advisor

    settings = get_settings()
    reset_usage_log()

    if path == "router":
        settings.llm_advisor_router_enabled = True
        text = _collect_stream(
            stream_advisor_chat(
                db,
                league_id=league_id,
                question=question,
                model_id=model_id,
                focused_roster_id=roster_id,
            )
        )
    else:
        from backend.services.advisor_service import build_minimal_advisor_context, _advisor_api_key
        from dynasty_draft.llm_advisor import advisor_model_by_id

        settings.llm_advisor_router_enabled = False
        row = advisor_model_by_id(model_id)
        api_key = _advisor_api_key(row["provider"])
        context, my_roster_id, focus_id = build_minimal_advisor_context(
            db, league_id, focused_roster_id=roster_id
        )
        tools = AdvisorTools(
            AdvisorToolContext(
                db=db,
                league_id=league_id,
                my_roster_id=my_roster_id,
                focused_roster_id=focus_id,
            )
        )
        text = _collect_stream(
            stream_inseason_advisor(
                context,
                api_key or "",
                user_question=question,
                model=row["model"],
                tools=ADVISOR_TOOL_SPECS,
                tool_handler=tools.dispatch,
            )
        )

    return text, usage_summary()


def main() -> int:
    parser = argparse.ArgumentParser(description="A/B advisor: tool loop vs router")
    parser.add_argument("--league", default=DEFAULT_LEAGUE)
    parser.add_argument("--roster", default=DEFAULT_ROSTER)
    parser.add_argument("--model", default="claude-sonnet-4-6")
    parser.add_argument("--question", action="append", help="Question(s) to compare")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    from backend.config import get_settings

    if not get_settings().anthropic_api_key:
        raise SystemExit("ANTHROPIC_API_KEY required")

    from backend.db.session import SessionLocal

    questions = args.question or SAMPLE_QUESTIONS
    report: list[dict[str, Any]] = []

    with SessionLocal() as db:
        for q in questions:
            print(f"\n{'=' * 72}\nQUESTION: {q}\n{'=' * 72}")
            legacy_text, legacy_usage = _run_path(
                db,
                league_id=args.league,
                roster_id=args.roster,
                question=q,
                path="legacy",
                model_id=args.model,
            )
            router_text, router_usage = _run_path(
                db,
                league_id=args.league,
                roster_id=args.roster,
                question=q,
                path="router",
                model_id=args.model,
            )

            row = {
                "question": q,
                "legacy": {
                    "calls": legacy_usage["calls"],
                    "input_tokens": legacy_usage["input_tokens"],
                    "output_tokens": legacy_usage["output_tokens"],
                    "est_usd": legacy_usage["estimated_cost_usd"],
                    "by_feature": legacy_usage.get("by_feature"),
                    "answer_chars": len(legacy_text),
                },
                "router": {
                    "calls": router_usage["calls"],
                    "input_tokens": router_usage["input_tokens"],
                    "output_tokens": router_usage["output_tokens"],
                    "est_usd": router_usage["estimated_cost_usd"],
                    "by_feature": router_usage.get("by_feature"),
                    "answer_chars": len(router_text),
                },
                "legacy_answer": legacy_text,
                "router_answer": router_text,
            }
            report.append(row)

            savings = legacy_usage["estimated_cost_usd"] - router_usage["estimated_cost_usd"]
            print(
                f"\nCOST  legacy: ${legacy_usage['estimated_cost_usd']:.4f} "
                f"({legacy_usage['calls']} calls) | "
                f"router: ${router_usage['estimated_cost_usd']:.4f} "
                f"({router_usage['calls']} calls) | "
                f"saved: ${savings:.4f}"
            )
            print(f"\n--- LEGACY ({legacy_usage['calls']} calls) ---\n{legacy_text[:2500]}")
            if len(legacy_text) > 2500:
                print("… [truncated]")
            print(f"\n--- ROUTER ({router_usage['calls']} calls) ---\n{router_text[:2500]}")
            if len(router_text) > 2500:
                print("… [truncated]")

    if args.json:
        slim = [
            {
                "question": r["question"],
                "legacy": {k: v for k, v in r["legacy"].items()},
                "router": {k: v for k, v in r["router"].items()},
            }
            for r in report
        ]
        print(json.dumps(slim, indent=2))

    total_legacy = sum(r["legacy"]["est_usd"] for r in report)
    total_router = sum(r["router"]["est_usd"] for r in report)
    print(
        f"\n=== TOTAL est. cost: legacy ${total_legacy:.4f} | "
        f"router ${total_router:.4f} | saved ${total_legacy - total_router:.4f} ==="
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
