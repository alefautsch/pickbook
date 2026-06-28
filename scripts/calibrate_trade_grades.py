#!/usr/bin/env python3
"""Report and experiment with trade-analysis grade calibration.

Usage:
  uv run python scripts/calibrate_trade_grades.py report
  uv run python scripts/calibrate_trade_grades.py simulate
  uv run python scripts/calibrate_trade_grades.py revalidate --limit 2
  uv run python scripts/calibrate_trade_grades.py revalidate --limit 2 --completed-prompt
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.services.trade_validation_service import COMPLETED_TRADE_VALIDATION_SUFFIX

DEFAULT_LEAGUE = "1314731206859853824"
GRADE_ORDER = ["F", "D", "C", "C+", "B", "B+", "A"]

COMPLETED_TRADE_PROMPT_SUFFIX = COMPLETED_TRADE_VALIDATION_SUFFIX


def _grade_idx(grade: str | None) -> int:
    if not grade:
        return 3
    return GRADE_ORDER.index(grade) if grade in GRADE_ORDER else 3


def _load_analyzed_trades(league_id: str) -> list[Any]:
    from sqlalchemy import select

    from backend.db.models import LeagueTransaction
    from backend.db.session import SessionLocal

    with SessionLocal() as db:
        return list(
            db.scalars(
                select(LeagueTransaction)
                .where(
                    LeagueTransaction.league_id == league_id,
                    LeagueTransaction.analysis_json.is_not(None),
                )
                .order_by(LeagueTransaction.created_ms.desc())
            ).all()
        )


def _side(row: dict[str, Any], key: str) -> dict[str, Any]:
    return dict(row.get(key) or {})


def cmd_report(league_id: str) -> None:
    from backend.services.trade_calculator_service import _tv_fairness_grade

    rows = _load_analyzed_trades(league_id)
    if not rows:
        print("No analyzed trades in DB.")
        return

    overall = Counter()
    tv = Counter()
    accept = Counter()
    both_low = 0

    print(f"Analyzed trades: {len(rows)} (league {league_id})\n")
    for row in rows:
        analysis = dict(row.analysis_json or {})
        tv_json = dict(row.tv_evaluation_json or {})
        side_a = _side(analysis, "side_a")
        side_b = _side(analysis, "side_b")
        tv_grade = analysis.get("tv_fairness_grade") or _tv_fairness_grade(tv_json)

        overall[analysis.get("overall_grade")] += 1
        tv[tv_grade] += 1
        accept[side_a.get("accept_likelihood")] += 1
        accept[side_b.get("accept_likelihood")] += 1
        if side_a.get("accept_likelihood") == "low" and side_b.get("accept_likelihood") == "low":
            both_low += 1

        print(
            f"  tx={row.sleeper_transaction_id[:10]} "
            f"overall={analysis.get('overall_grade')} tv={tv_grade} "
            f"pct={tv_json.get('net_delta_adjusted_pct')} "
            f"| A={side_a.get('grade')}/{side_a.get('accept_likelihood')} "
            f"B={side_b.get('grade')}/{side_b.get('accept_likelihood')}"
        )

    print("\nDistribution:")
    print(f"  overall:     {dict(overall)}")
    print(f"  tv_fairness: {dict(tv)}")
    print(f"  accept:      {dict(accept)}")
    print(f"  both low:    {both_low}/{len(rows)}")


def _accept_grade_v1(likelihood: str | None) -> str:
    from backend.services.trade_calculator_service import _accept_likelihood_grade

    return _accept_likelihood_grade(likelihood)


def _accept_grade_v2(likelihood: str | None) -> str:
    key = str(likelihood or "medium").lower()
    return {"high": "A", "medium": "B", "low": "C"}.get(key, "C")


def _overall_min(tv: str, ga: str | None, gb: str | None) -> str:
    from backend.services.trade_calculator_service import _overall_grade

    return _overall_grade(tv, ga, gb)


def _overall_completed(tv: str, ga: str | None, gb: str | None) -> str:
    accept = [g for g in (ga, gb) if g]
    if not accept:
        return tv
    tv_idx = _grade_idx(tv)
    accept_idx = sum(_grade_idx(g) for g in accept) / len(accept)
    combined = round(0.55 * tv_idx + 0.45 * accept_idx)
    return GRADE_ORDER[max(0, min(combined, len(GRADE_ORDER) - 1))]


def cmd_simulate(league_id: str) -> None:
    from backend.services.trade_calculator_service import _tv_fairness_grade

    rows = _load_analyzed_trades(league_id)
    if not rows:
        print("No analyzed trades in DB.")
        return

    scenarios = {
        "current (stored)": lambda tv, sa, sb: _overall_min(
            tv, sa.get("grade"), sb.get("grade")
        ),
        "low->C + min overall": lambda tv, sa, sb: _overall_min(
            tv, _accept_grade_v2(sa.get("accept_likelihood")), _accept_grade_v2(sb.get("accept_likelihood"))
        ),
        "low->C + completed overall": lambda tv, sa, sb: _overall_completed(
            tv, _accept_grade_v2(sa.get("accept_likelihood")), _accept_grade_v2(sb.get("accept_likelihood"))
        ),
    }
    totals = {name: Counter() for name in scenarios}

    for row in rows:
        analysis = dict(row.analysis_json or {})
        tv_json = dict(row.tv_evaluation_json or {})
        tv = analysis.get("tv_fairness_grade") or _tv_fairness_grade(tv_json)
        side_a = _side(analysis, "side_a")
        side_b = _side(analysis, "side_b")
        for name, fn in scenarios.items():
            totals[name][fn(tv, side_a, side_b)] += 1

    print(f"Simulations on {len(rows)} stored trades:\n")
    for name, counter in totals.items():
        print(f"  {name}: {dict(counter)}")


def cmd_revalidate(league_id: str, *, limit: int, completed_prompt: bool) -> None:
    from sqlalchemy import select

    from backend.db.models import LeagueTransaction
    from backend.db.session import SessionLocal
    from backend.services.trade_activity_service import _build_evaluate_request
    from backend.services.trade_calculator_service import validate_trade_dual

    label = "completed-trade mode" if completed_prompt else "hypothetical mode"
    accept = Counter()
    overall = Counter()
    tv = Counter()

    with SessionLocal() as db:
        rows = list(
            db.scalars(
                select(LeagueTransaction)
                .where(
                    LeagueTransaction.league_id == league_id,
                    LeagueTransaction.analysis_json.is_not(None),
                )
                .order_by(LeagueTransaction.created_ms.desc())
                .limit(limit)
            ).all()
        )
        if not rows:
            print("No analyzed trades in DB.")
            return

        print(f"Revalidating {len(rows)} trade(s) [{label}]\n")
        for row in rows:
            roster_ids = list(row.roster_ids_json or [])
            sides = dict(row.sides_json or {})
            req = _build_evaluate_request(roster_ids[0], roster_ids[1], sides)
            stored = dict(row.analysis_json or {})
            result = validate_trade_dual(
                db,
                league_id,
                req,
                include_fix=False,
                completed_trade=completed_prompt,
            )
            if result is None:
                print(f"  tx={row.sleeper_transaction_id[:10]} — skipped")
                continue

            overall[result.overall_grade] += 1
            tv[result.evaluation.tv_fairness_grade] += 1
            accept[result.side_a.accept_likelihood] += 1
            accept[result.side_b.accept_likelihood] += 1

            print(
                f"  tx={row.sleeper_transaction_id[:10]} "
                f"stored={stored.get('overall_grade')} -> fresh={result.overall_grade} "
                f"tv={result.evaluation.tv_fairness_grade} "
                f"({result.evaluation.net_delta_adjusted_pct:+.1f}%)"
            )
            print(
                f"    A: {result.side_a.grade}/{result.side_a.accept_likelihood} "
                f"| B: {result.side_b.grade}/{result.side_b.accept_likelihood}"
            )

        print(f"\nFresh distribution [{label}]:")
        print(f"  overall: {dict(overall)}")
        print(f"  tv:      {dict(tv)}")
        print(f"  accept:  {dict(accept)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Trade grade calibration experiments")
    parser.add_argument("--league-id", default=DEFAULT_LEAGUE)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("report", help="Grade distribution from stored analyses")
    sub.add_parser("simulate", help="Simulate mapping changes without LLM calls")

    revalidate = sub.add_parser("revalidate", help="Re-run LLM validation on stored trades")
    revalidate.add_argument("--limit", type=int, default=2, help="Max trades to revalidate")
    revalidate.add_argument(
        "--completed-prompt",
        action="store_true",
        help="Use completed-trade mode (default: proposed/negotiation mode for trade calc)",
    )

    args = parser.parse_args()
    if args.command == "report":
        cmd_report(args.league_id)
    elif args.command == "simulate":
        cmd_simulate(args.league_id)
    elif args.command == "revalidate":
        cmd_revalidate(
            args.league_id,
            limit=args.limit,
            completed_prompt=args.completed_prompt,
        )


if __name__ == "__main__":
    main()
