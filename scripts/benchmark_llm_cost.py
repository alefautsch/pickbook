#!/usr/bin/env python3
"""Benchmark LLM token usage and estimated cost for advisor + calculator paths.

Requires ANTHROPIC_API_KEY and local league data (--db) or live API.

Usage:
  uv run python scripts/benchmark_llm_cost.py --db --scenario validation
  uv run python scripts/benchmark_llm_cost.py --db --scenario all
  uv run python scripts/benchmark_llm_cost.py --db --scenario advisor_suggest_trade
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

SCENARIOS = (
    "validation",
    "suggest_trades",
    "suggest_trades_ranked",
    "calculator_dual",
    "advisor_suggest_trade",
    "all",
)


def _print_summary(label: str) -> dict[str, Any]:
    from backend.services.llm_usage import usage_summary

    summary = usage_summary()
    print(f"\n--- {label} ---")
    print(f"  calls: {summary['calls']}")
    print(f"  input tokens:  {summary['input_tokens']:,}")
    print(f"  output tokens: {summary['output_tokens']:,}")
    print(f"  est. cost USD: ${summary['estimated_cost_usd']:.4f}")
    if summary["by_feature"]:
        print("  by feature:")
        for feat, row in summary["by_feature"].items():
            print(
                f"    {feat}: {row['calls']} calls, "
                f"{row['input_tokens']:,} in / {row['output_tokens']:,} out, "
                f"${row['est_usd']:.4f}"
            )
    if summary["by_model"]:
        print("  by model:")
        for model, row in summary["by_model"].items():
            print(
                f"    {model}: {row['calls']} calls, "
                f"${row['est_usd']:.4f}"
            )
    return summary


def _require_api_key() -> str:
    from backend.config import get_settings

    key = get_settings().anthropic_api_key
    if not key or not key.strip():
        raise SystemExit("ANTHROPIC_API_KEY is required for live benchmarks")
    return key.strip()


def _load_tools_db(league_id: str, roster_id: str):
    from sqlalchemy.orm import Session

    from backend.db.session import SessionLocal
    from backend.services.advisor_tools import AdvisorToolContext, AdvisorTools

    db: Session = SessionLocal()
    tools = AdvisorTools(
        AdvisorToolContext(
            db=db,
            league_id=league_id,
            my_roster_id=roster_id,
            focused_roster_id=roster_id,
        )
    )
    return db, tools


def _first_package_give_receive(tools, roster_id: str) -> tuple[str, dict, dict] | None:
    result = tools.suggest_trades(rank_by_validation=False)
    packages = result.get("packages") or []
    if not packages:
        return None
    pkg = packages[0]
    cp_id = str((pkg.get("counterparty") or {}).get("roster_id") or "")

    def _player_ids(rows: list[dict]) -> list[str]:
        return [str(p["player_id"]) for p in rows if p.get("player_id")]

    def _pick_refs(rows: list[dict]) -> list[dict]:
        refs = []
        for pick in rows:
            if pick.get("player_id"):
                continue
            refs.append(
                {
                    "season": pick["season"],
                    "round": pick["round"],
                    "original_roster_id": pick["original_roster_id"],
                }
            )
        return refs

    give = pkg.get("give") or {}
    recv = pkg.get("receive") or {}
    return (
        cp_id,
        {
            "players": _player_ids(give.get("players") or []),
            "picks": _pick_refs(give.get("picks") or []),
        },
        {
            "players": _player_ids(recv.get("players") or []),
            "picks": _pick_refs(recv.get("picks") or []),
        },
    )


def run_validation(league_id: str, roster_id: str) -> None:
    from backend.config import get_settings
    from backend.services.trade_validation_service import (
        build_validation_payload,
        validate_trade_with_llm,
    )
    from backend.services.advisor_tools import evaluate_trade_package

    db, tools = _load_tools_db(league_id, roster_id)
    try:
        trade = _first_package_give_receive(tools, roster_id)
        if trade is None:
            print("validation: no packages — skip")
            return
        cp_id, give, recv = trade
        eval_result = evaluate_trade_package(
            give,
            recv,
            resolve_player=tools._resolve_player,
            resolve_pick=tools._resolve_pick,
        )
        payload = build_validation_payload(
            proposer_roster_id=roster_id,
            counterparty_roster_id=cp_id,
            proposer_team=tools.get_team(roster_id),
            counterparty_team=tools.get_team(cp_id),
            give=eval_result["give"],
            receive=eval_result["receive"],
            tv_evaluation=eval_result,
        )
        result = validate_trade_with_llm(payload, api_key=get_settings().anthropic_api_key)
        print("validation result:", result.get("accept_likelihood"), result.get("fairness_from_counterparty_view"))
    finally:
        db.close()


def run_suggest_trades(league_id: str, roster_id: str, *, ranked: bool) -> None:
    db, tools = _load_tools_db(league_id, roster_id)
    try:
        result = tools.suggest_trades(rank_by_validation=ranked)
        n = len(result.get("packages") or [])
        print(f"suggest_trades (ranked={ranked}): {n} packages")
    finally:
        db.close()


def run_calculator_dual(league_id: str, roster_id: str) -> None:
    from backend.db.session import SessionLocal
    from backend.schemas.trade import TradeEvaluateRequest, TradePickRef, TradeSideInput
    from backend.services.trade_calculator_service import validate_trade_dual

    db, tools = _load_tools_db(league_id, roster_id)
    try:
        trade = _first_package_give_receive(tools, roster_id)
        if trade is None:
            print("calculator_dual: no packages — skip")
            return
        cp_id, give, recv = trade
        pick_models = [
            TradePickRef(
                season=str(p["season"]),
                round=int(p["round"]),
                original_roster_id=str(p["original_roster_id"]),
            )
            for p in give.get("picks") or []
        ]
        recv_pick_models = [
            TradePickRef(
                season=str(p["season"]),
                round=int(p["round"]),
                original_roster_id=str(p["original_roster_id"]),
            )
            for p in recv.get("picks") or []
        ]
        req = TradeEvaluateRequest(
            side_a_roster_id=roster_id,
            side_b_roster_id=cp_id,
            side_a_gives=TradeSideInput(players=give["players"], picks=pick_models),
            side_b_gives=TradeSideInput(players=recv["players"], picks=recv_pick_models),
        )
        # Re-open session for service layer
        db.close()
        with SessionLocal() as session:
            result = validate_trade_dual(session, league_id, req)
        if result is None:
            print("calculator_dual: validate returned None")
            return
        print(
            "calculator_dual:",
            result.overall_grade,
            "|",
            result.side_a.accept_likelihood,
            "/",
            result.side_b.accept_likelihood,
        )
    finally:
        try:
            db.close()
        except Exception:
            pass


def run_advisor_suggest_trade(league_id: str, roster_id: str) -> None:
    """Full preset path: deterministic harness + single LLM prose call."""
    from backend.db.session import SessionLocal
    from backend.services.advisor_service import stream_advisor_chat
    from dynasty_draft.llm_advisor import inseason_prompt_by_id

    preset = inseason_prompt_by_id("suggest_trade")
    if preset is None:
        raise SystemExit("suggest_trade preset not found")

    chunks: list[str] = []
    with SessionLocal() as db:
        for chunk in stream_advisor_chat(
            db,
            league_id=league_id,
            prompt_id="suggest_trade",
            focused_roster_id=roster_id,
        ):
            chunks.append(chunk)
    text = "".join(chunks)
    print(f"advisor_suggest_trade: {len(text)} chars reply")
    print(text[:400].replace("\n", " ") + ("…" if len(text) > 400 else ""))


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark LLM cost for advisor/calculator")
    parser.add_argument("--league", default=DEFAULT_LEAGUE)
    parser.add_argument("--roster", default=DEFAULT_ROSTER)
    parser.add_argument(
        "--scenario",
        choices=SCENARIOS,
        default="all",
        help="Which path to benchmark (default: all)",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable summaries")
    args = parser.parse_args()

    _require_api_key()

    from backend.services.llm_usage import reset_usage_log

    summaries: dict[str, Any] = {}

    def _run(name: str, fn) -> None:
        reset_usage_log()
        print(f"\n>>> Running {name}")
        fn()
        summaries[name] = _print_summary(name)

    scenario = args.scenario
    if scenario in ("validation", "all"):
        _run("validation", lambda: run_validation(args.league, args.roster))
    if scenario in ("suggest_trades", "all"):
        _run("suggest_trades", lambda: run_suggest_trades(args.league, args.roster, ranked=False))
    if scenario in ("suggest_trades_ranked", "all"):
        _run(
            "suggest_trades_ranked",
            lambda: run_suggest_trades(args.league, args.roster, ranked=True),
        )
    if scenario in ("calculator_dual", "all"):
        _run("calculator_dual", lambda: run_calculator_dual(args.league, args.roster))
    if scenario in ("advisor_suggest_trade", "all"):
        _run("advisor_suggest_trade", lambda: run_advisor_suggest_trade(args.league, args.roster))

    if args.json:
        print(json.dumps(summaries, indent=2))

    if scenario == "all":
        total = sum(s["estimated_cost_usd"] for s in summaries.values())
        print(f"\n=== Total estimated cost (all scenarios): ${total:.4f} ===")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
