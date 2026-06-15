#!/usr/bin/env python3
"""Compare Haiku vs Sonnet on dual trade calculator AI validation.

Runs the same trade package through validate_trade_dual twice and prints
accept grades, reasoning, agreement, and cost.

Usage:
  uv run python scripts/compare_trade_validation_models.py
  uv run python scripts/compare_trade_validation_models.py --package 2
  uv run python scripts/compare_trade_validation_models.py --json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_LEAGUE = "1314731206859853824"
DEFAULT_ROSTER = "3"
DEFAULT_API = os.environ.get(
    "API_BASE",
    os.environ.get("NEXT_PUBLIC_API_URL", "https://dynasty-bb.up.railway.app"),
)
HAIKU_MODEL = "claude-haiku-4-5"
SONNET_MODEL = "claude-sonnet-4-6"


def _player_ids(rows: list[dict]) -> list[str]:
    return [str(p["player_id"]) for p in rows if p.get("player_id")]


def _pick_refs(rows: list[dict]) -> list[dict]:
    refs: list[dict] = []
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


def _fmt_assets(side: dict[str, Any]) -> str:
    parts: list[str] = []
    for p in side.get("players") or []:
        name = p.get("name") or p.get("player_name") or "?"
        pos = p.get("position") or p.get("pos") or "?"
        tv = p.get("tv") or p.get("trade_value")
        parts.append(f"{name} ({pos}, TV {tv:.0f})" if tv else f"{name} ({pos})")
    for p in side.get("picks") or []:
        label = p.get("label") or f"{p.get('season')} R{p.get('round')}"
        tv = p.get("trade_value") or p.get("tv")
        parts.append(f"{label} (TV {tv:.0f})" if tv else label)
    return ", ".join(parts) if parts else "—"


def _packages_for_roster(
    league_id: str,
    roster_id: str,
    *,
    use_api: bool,
    api_base: str,
) -> list[dict[str, Any]]:
    from backend.services.advisor_tools import (
        AdvisorToolContext,
        AdvisorTools,
        generate_trade_suggestions,
    )

    if use_api:
        from scripts.run_trade_iteration import load_from_api

        trade_surplus, roster_players, picks_by_roster, tiers, team_names = load_from_api(
            api_base, league_id, roster_id
        )
        return generate_trade_suggestions(
            my_roster_id=str(roster_id),
            trade_surplus=trade_surplus,
            roster_players=roster_players,
            picks_by_roster=picks_by_roster,
            contender_tier_by_roster=tiers,
        )

    from backend.db.session import SessionLocal
    from scripts.run_trade_iteration import load_from_db

    trade_surplus, roster_players, picks_by_roster, tiers, _team_names = load_from_db(
        league_id, roster_id
    )
    with SessionLocal() as db:
        tools = AdvisorTools(
            AdvisorToolContext(
                db=db,
                league_id=league_id,
                my_roster_id=roster_id,
                focused_roster_id=roster_id,
            )
        )
        packages = (tools.suggest_trades(rank_by_validation=False).get("packages") or [])
        if packages:
            return packages
    return generate_trade_suggestions(
        my_roster_id=str(roster_id),
        trade_surplus=trade_surplus,
        roster_players=roster_players,
        picks_by_roster=picks_by_roster,
        contender_tier_by_roster=tiers,
    )


def _synthetic_trade_from_db(
    league_id: str,
    roster_id: str,
) -> tuple[Any, dict[str, Any]] | None:
    """Build a plausible 1-for-1 player swap when suggest_trades returns nothing."""
    from backend.db.session import SessionLocal
    from backend.schemas.trade import TradeEvaluateRequest, TradeSideInput
    from backend.services.advisor_tools import AdvisorToolContext, AdvisorTools
    from sqlalchemy import select
    from backend.db.models import Roster

    with SessionLocal() as db:
        tools = AdvisorTools(
            AdvisorToolContext(
                db=db,
                league_id=league_id,
                my_roster_id=roster_id,
                focused_roster_id=roster_id,
            )
        )
        my_team = tools.get_team(roster_id)
        if my_team.get("error"):
            return None
        my_player = next(
            (
                p
                for p in my_team.get("players") or []
                if p.get("player_id") and p.get("trade_tag") == "trade"
            ),
            None,
        )
        if my_player is None:
            return None

        my_tv = float(my_player.get("tv") or 0)
        best: tuple[str, dict[str, Any], float] | None = None
        for roster in db.scalars(select(Roster).where(Roster.league_id == league_id)).all():
            cp_id = roster.sleeper_roster_id
            if cp_id == roster_id:
                continue
            their_team = tools.get_team(cp_id)
            for p in their_team.get("players") or []:
                if not p.get("player_id") or p.get("trade_tag") == "core":
                    continue
                tv = float(p.get("tv") or 0)
                if tv <= 0:
                    continue
                delta = abs(tv - my_tv)
                if best is None or delta < best[2]:
                    best = (cp_id, p, delta)

        if best is None:
            return None
        cp_id, their_player, _ = best
        cp_team = tools.get_team(cp_id)

        give = {"players": [my_player], "picks": []}
        recv = {"players": [their_player], "picks": []}
        req = TradeEvaluateRequest(
            side_a_roster_id=roster_id,
            side_b_roster_id=cp_id,
            side_a_gives=TradeSideInput(players=[str(my_player["player_id"])], picks=[]),
            side_b_gives=TradeSideInput(players=[str(their_player["player_id"])], picks=[]),
        )
        meta = {
            "package_index": 1,
            "package_count": 1,
            "counterparty": cp_team.get("team_name"),
            "give_summary": _fmt_assets(give),
            "receive_summary": _fmt_assets(recv),
            "fairness": None,
            "net_delta_adjusted_pct": None,
            "synthetic": True,
        }
        return req, meta
    return None


def _load_trade_request(
    league_id: str,
    roster_id: str,
    *,
    package_index: int,
    use_api: bool,
    api_base: str,
):
    from backend.schemas.trade import TradeEvaluateRequest, TradePickRef, TradeSideInput

    packages = _packages_for_roster(
        league_id, roster_id, use_api=use_api, api_base=api_base
    )
    if not packages:
        synthetic = _synthetic_trade_from_db(league_id, roster_id)
        if synthetic is not None:
            return synthetic
        raise SystemExit(
            "No trade packages found — try --api, another --roster, or sync league data"
        )

    idx = max(0, min(package_index - 1, len(packages) - 1))
    pkg = packages[idx]
    cp_id = str((pkg.get("counterparty") or {}).get("roster_id") or "")
    give = pkg.get("give") or {}
    recv = pkg.get("receive") or {}

    req = TradeEvaluateRequest(
        side_a_roster_id=roster_id,
        side_b_roster_id=cp_id,
        side_a_gives=TradeSideInput(
            players=_player_ids(give.get("players") or []),
            picks=[
                TradePickRef(
                    season=str(p["season"]),
                    round=int(p["round"]),
                    original_roster_id=str(p["original_roster_id"]),
                )
                for p in _pick_refs(give.get("picks") or [])
            ],
        ),
        side_b_gives=TradeSideInput(
            players=_player_ids(recv.get("players") or []),
            picks=[
                TradePickRef(
                    season=str(p["season"]),
                    round=int(p["round"]),
                    original_roster_id=str(p["original_roster_id"]),
                )
                for p in _pick_refs(recv.get("picks") or [])
            ],
        ),
    )
    meta = {
        "package_index": idx + 1,
        "package_count": len(packages),
        "counterparty": (pkg.get("counterparty") or {}).get("team_name"),
        "give_summary": _fmt_assets(give),
        "receive_summary": _fmt_assets(recv),
        "fairness": pkg.get("fairness"),
        "net_delta_adjusted_pct": pkg.get("net_delta_adjusted_pct"),
    }
    return req, meta


def _side_snapshot(side: Any) -> dict[str, Any]:
    return {
        "team": side.team_name,
        "accept_likelihood": side.accept_likelihood,
        "grade": side.grade,
        "fairness_view": side.fairness_view,
        "fairness_label": side.fairness_label,
        "would_improve_roster": side.would_improve_roster,
        "reasoning": side.reasoning,
        "blockers": side.blockers,
        "suggested_tweak": side.suggested_tweak,
        "skipped": side.skipped,
        "error": side.error,
    }


def _run_dual(
    db,
    league_id: str,
    req,
    *,
    model: str,
) -> tuple[Any, dict[str, Any]]:
    from backend.services.llm_usage import reset_usage_log, usage_summary
    from backend.services.trade_calculator_service import validate_trade_dual

    reset_usage_log()
    result = validate_trade_dual(db, league_id, req, validation_model=model)
    if result is None:
        raise SystemExit("validate_trade_dual returned None")
    return result, usage_summary()


def _agreement(a: dict[str, Any], b: dict[str, Any]) -> dict[str, bool]:
    return {
        "accept_likelihood": a.get("accept_likelihood") == b.get("accept_likelihood"),
        "grade": a.get("grade") == b.get("grade"),
        "fairness_view": a.get("fairness_view") == b.get("fairness_view"),
        "would_improve_roster": a.get("would_improve_roster") == b.get("would_improve_roster"),
    }


def _print_side(label: str, snap: dict[str, Any]) -> None:
    print(f"  {label} ({snap.get('team') or '?'}):")
    if snap.get("skipped"):
        print(f"    SKIPPED: {snap.get('error')}")
        return
    print(
        f"    accept={snap.get('accept_likelihood')} grade={snap.get('grade')} "
        f"fairness={snap.get('fairness_view')} improves={snap.get('would_improve_roster')}"
    )
    if snap.get("blockers"):
        print(f"    blockers: {snap['blockers']}")
    if snap.get("suggested_tweak"):
        print(f"    tweak: {snap['suggested_tweak']}")
    reasoning = str(snap.get("reasoning") or "")
    print(f"    reasoning: {reasoning[:400]}{'…' if len(reasoning) > 400 else ''}")


def main() -> int:
    parser = argparse.ArgumentParser(description="A/B Haiku vs Sonnet trade validation")
    parser.add_argument("--league", default=DEFAULT_LEAGUE)
    parser.add_argument("--roster", default=DEFAULT_ROSTER)
    parser.add_argument(
        "--package",
        type=int,
        default=1,
        help="Package index from suggest_trades (1-based)",
    )
    parser.add_argument("--api", default=DEFAULT_API, help="API base when loading packages")
    parser.add_argument(
        "--db-only",
        action="store_true",
        help="Use local DB only (default: API fallback if DB has no packages)",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    from backend.config import get_settings
    from backend.db.session import SessionLocal

    if not get_settings().anthropic_api_key:
        raise SystemExit("ANTHROPIC_API_KEY required")

    req, meta = _load_trade_request(
        args.league,
        args.roster,
        package_index=args.package,
        use_api=not args.db_only,
        api_base=args.api,
    )

    print(f"Package {meta['package_index']}/{meta['package_count']} vs {meta['counterparty']}")
    if meta.get("synthetic"):
        print("  (synthetic 1-for-1 — no suggest_trades packages for this roster)")
    print(f"  YOU GIVE:    {meta['give_summary']}")
    print(f"  YOU RECEIVE: {meta['receive_summary']}")
    print(
        f"  TV fairness: {meta['fairness']} "
        f"({meta.get('net_delta_adjusted_pct')}% adj delta)"
    )

    with SessionLocal() as db:
        haiku_result, haiku_usage = _run_dual(
            db, args.league, req, model=HAIKU_MODEL
        )
        sonnet_result, sonnet_usage = _run_dual(
            db, args.league, req, model=SONNET_MODEL
        )

    haiku_a = _side_snapshot(haiku_result.side_a)
    haiku_b = _side_snapshot(haiku_result.side_b)
    sonnet_a = _side_snapshot(sonnet_result.side_a)
    sonnet_b = _side_snapshot(sonnet_result.side_b)

    report = {
        "trade": meta,
        "tv_evaluation": {
            "tv_fairness_grade": haiku_result.evaluation.tv_fairness_grade,
            "net_delta_adjusted_pct": haiku_result.evaluation.net_delta_adjusted_pct,
            "within_band": haiku_result.evaluation.within_band,
        },
        "haiku": {
            "model": HAIKU_MODEL,
            "overall_grade": haiku_result.overall_grade,
            "summary": haiku_result.summary,
            "side_a": haiku_a,
            "side_b": haiku_b,
            "usage": haiku_usage,
        },
        "sonnet": {
            "model": SONNET_MODEL,
            "overall_grade": sonnet_result.overall_grade,
            "summary": sonnet_result.summary,
            "side_a": sonnet_a,
            "side_b": sonnet_b,
            "usage": sonnet_usage,
        },
        "agreement": {
            "side_a": _agreement(haiku_a, sonnet_a),
            "side_b": _agreement(haiku_b, sonnet_b),
            "overall_grade": haiku_result.overall_grade == sonnet_result.overall_grade,
        },
    }

    savings = sonnet_usage["estimated_cost_usd"] - haiku_usage["estimated_cost_usd"]
    print(
        f"\nCOST  haiku: ${haiku_usage['estimated_cost_usd']:.4f} "
        f"({haiku_usage['calls']} calls) | "
        f"sonnet: ${sonnet_usage['estimated_cost_usd']:.4f} "
        f"({sonnet_usage['calls']} calls) | "
        f"saved: ${savings:.4f}"
    )
    print(
        f"\nOVERALL  haiku grade={haiku_result.overall_grade} | "
        f"sonnet grade={sonnet_result.overall_grade} | "
        f"match={report['agreement']['overall_grade']}"
    )

    print(f"\n--- HAIKU ({HAIKU_MODEL}) ---")
    _print_side("Side A (would A accept?)", haiku_a)
    _print_side("Side B (would B accept?)", haiku_b)
    if haiku_result.summary:
        print(f"  summary: {haiku_result.summary}")

    print(f"\n--- SONNET ({SONNET_MODEL}) ---")
    _print_side("Side A (would A accept?)", sonnet_a)
    _print_side("Side B (would B accept?)", sonnet_b)
    if sonnet_result.summary:
        print(f"  summary: {sonnet_result.summary}")

    print("\n--- AGREEMENT ---")
    for side_key in ("side_a", "side_b"):
        agree = report["agreement"][side_key]
        flags = [k for k, v in agree.items() if v]
        disagree = [k for k, v in agree.items() if not v]
        print(f"  {side_key}: agree on {flags or 'nothing'}; differ on {disagree or 'nothing'}")

    if args.json:
        slim = {
            "trade": report["trade"],
            "tv_evaluation": report["tv_evaluation"],
            "haiku": {
                k: v
                for k, v in report["haiku"].items()
                if k != "usage"
            },
            "sonnet": {
                k: v
                for k, v in report["sonnet"].items()
                if k != "usage"
            },
            "agreement": report["agreement"],
            "cost": {
                "haiku_usd": haiku_usage["estimated_cost_usd"],
                "sonnet_usd": sonnet_usage["estimated_cost_usd"],
                "saved_usd": savings,
            },
        }
        print(json.dumps(slim, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
