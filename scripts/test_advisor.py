#!/usr/bin/env python3
"""
Audit advisor context and optionally call the live LLM for bookend advice.

Usage:
  python scripts/test_advisor.py              # context audit only
  python scripts/test_advisor.py --call-llm   # audit + Anthropic reply + rubric
  python scripts/test_advisor.py --json         # machine-readable audit
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dynasty_draft.builder import build_state
from dynasty_draft.config import load_config
from dynasty_draft.llm_advisor import (
    DEFAULT_MODEL,
    advisor_model_by_id,
    build_advisor_context,
    evaluate_picks,
)
from dynasty_draft.recommender import DraftState


def _bookend_question(state: DraftState) -> str:
    info = state.next_pick_info()
    picks = info.get("consecutive_picks") or []
    gone = ", ".join(
        f"{(p.get('metadata') or {}).get('first_name', '')} {(p.get('metadata') or {}).get('last_name', '')}".strip()
        for p in sorted(state.picks, key=lambda row: row.get("pick_no", 0))
    )
    if len(picks) >= 2:
        return (
            f"I have picks {picks[0]} and {picks[1]} back-to-back. Already drafted: {gone}. "
            f"Reserving Jeremiyah Love in rookie draft. Superflex startup — lead with "
            f"bookend_dynasty_targets and dynasty_rating (age + WORP* + TV), not TV-only sim. "
            f"Best two-pick plan at this bookend. Favor young upside at QB over aging win-now vets."
        )
    return (
        f"Already drafted: {gone}. Superflex startup — use bookend_dynasty_targets and dynasty_rating. "
        f"Best plan at my next bookend?"
    )


def _player_row(pool: list[dict[str, Any]], needle: str) -> dict[str, Any] | None:
    key = needle.lower()
    for row in pool:
        if key in (row.get("name") or "").lower():
            return row
    return None


def audit_context(state: DraftState, context: dict[str, Any]) -> dict[str, Any]:
    """Structured checks on context data (no LLM)."""
    info = state.next_pick_info()
    bookend = info.get("consecutive_picks") or []
    adp = state._adp_index()
    findings: list[dict[str, Any]] = []
    warnings: list[str] = []

    targets = context.get("bookend_dynasty_targets") or {}
    dynasty_qbs = (targets.get("by_position") or {}).get("QB") or []
    contingency_qbs = [
        row
        for row in (targets.get("if_they_fall_from_current_board") or [])
        if row.get("pos") == "QB"
    ][:6]
    top_dyn_qb = dynasty_qbs[0] if dynasty_qbs else None

    dak_dyn = _player_row(targets.get("top_by_dynasty_rating") or [], "Dak Prescott")
    law_dyn = _player_row(
        (targets.get("top_by_dynasty_rating") or [])
        + (targets.get("if_they_fall_from_current_board") or []),
        "Trevor Lawrence",
    )

    for pick_no in bookend:
        fall_block = next(
            (b for b in (context.get("falls_to_you") or {}).get("at_each_pick") or [] if b.get("pick_no") == pick_no),
            None,
        )
        if not fall_block:
            continue
        sim_top = (fall_block.get("top_available_sim") or [])[:5]
        dyn_top = (fall_block.get("top_by_dynasty_rating") or [])[:5]
        sim_qb = next((r for r in sim_top if r.get("pos") == "QB"), None)
        dyn_qb = next((r for r in dyn_top if r.get("pos") == "QB"), None)
        if sim_qb and dyn_qb and sim_qb.get("name") != dyn_qb.get("name"):
            warnings.append(
                f"Pick #{pick_no}: TV sim QB #{1} is {sim_qb['name']} but dynasty QB #1 is {dyn_qb['name']} "
                f"(Dyn {dyn_qb.get('dynasty_rating')} vs {sim_qb.get('dynasty_rating')})"
            )
        if sim_qb and "Dak" in (sim_qb.get("name") or ""):
            delta = adp.delta(sim_qb["name"], pick_no)
            findings.append(
                {
                    "pick_no": pick_no,
                    "check": "dak_sim_leader_adp",
                    "sim_qb": sim_qb["name"],
                    "adp_pick": adp.pick_no(sim_qb["name"]),
                    "adp_delta": delta,
                    "adp_class": adp.adp_class(delta),
                    "dynasty_rating": sim_qb.get("dynasty_rating"),
                    "expect": "reach (negative delta), not a steal",
                }
            )

    if dak_dyn and law_dyn and law_dyn.get("dynasty_rating", 0) > dak_dyn.get("dynasty_rating", 0):
        findings.append(
            {
                "check": "lawrence_vs_dak_dynasty",
                "lawrence": {
                    "dynasty_rating": law_dyn.get("dynasty_rating"),
                    "age": law_dyn.get("age"),
                    "adp_pick": law_dyn.get("adp_pick"),
                },
                "dak": {
                    "dynasty_rating": dak_dyn.get("dynasty_rating"),
                    "age": dak_dyn.get("age"),
                    "adp_pick": dak_dyn.get("adp_pick"),
                },
                "expect": "advisor should prefer Lawrence profile for startup SF",
            }
        )

    planned = (context.get("pick_projection") or {}).get("current_bookend", {}).get("planned_picks") or []
    planned_names = [p.get("name") for p in planned]
    if any("Dak" in (n or "") for n in planned_names):
        warnings.append(f"pick_projection planned pair includes Dak: {planned_names}")

    framework = context.get("decision_framework") or {}
    return {
        "pick_no": info.get("pick_no"),
        "bookend_picks": bookend,
        "picks_until_mine": info.get("picks_until_mine"),
        "top_dynasty_qb": top_dyn_qb,
        "dynasty_qbs_top6": dynasty_qbs[:6],
        "fall_contingency_qbs_top6": contingency_qbs,
        "current_planned_pair": planned,
        "findings": findings,
        "warnings": warnings,
        "decision_primary_lens": framework.get("primary_lens"),
        "has_bookend_dynasty_targets": bool(targets.get("top_by_dynasty_rating")),
    }


def evaluate_response(response: str, state: DraftState, context: dict[str, Any]) -> dict[str, Any]:
    """Rubric-based scoring of advisor prose."""
    text = response.lower()
    bookend = (state.next_pick_info().get("consecutive_picks") or [None])[0]
    adp = state._adp_index()
    dak_delta = adp.delta("Dak Prescott", bookend) if bookend else None

    issues: list[str] = []
    passes: list[str] = []

    # Outdated weighting
    if re.search(r"65\s*%|65/35|trade value 65", text):
        issues.append("Mentions outdated 65/35 (or 65%) trade/WORP framing")
    else:
        passes.append("No outdated 65/35 weighting")

    if any(k in text for k in ("dynasty_rating", "dynasty rating", "dynasty ovr", "bookend_dynasty")):
        passes.append("References dynasty rating / dynasty targets")
    else:
        issues.append("Does not mention dynasty_rating or bookend_dynasty_targets")

    dak_negated = bool(re.search(r"(don't|do not|avoid|never|not)\s+(take|draft|grab|target|pick)\s+dak", text))
    dak_primary = bool(
        not dak_negated
        and (
            re.search(r"(take|draft|grab|target|pick)\s+dak", text)
            or re.search(r"dak\s+prescott.*(first|pick\s*1|with your (first|1st))", text)
        )
    )
    if dak_primary:
        issues.append("Recommends Dak as a primary bookend pick")
    elif dak_negated:
        passes.append("Explicitly warns against Dak at bookend")

    if re.search(r"dak.*(steal|value|great value|smash)", text) and not dak_negated:
        issues.append("Calls Dak a steal/value (likely wrong at early bookend)")
    elif "dak" in text and dak_delta is not None and dak_delta < 0:
        if re.search(r"dak.*(reach|early|aggressive|over-rank|32|age|do not|don't)", text):
            passes.append("Correctly frames Dak as reach or aging when mentioned")
        elif "dak" in text and not dak_negated:
            issues.append(f"Mentions Dak without reach/age caveat (delta={dak_delta})")

    law_available = _player_row(
        ((context.get("bookend_dynasty_targets") or {}).get("top_by_dynasty_rating") or [])
        + ((context.get("bookend_dynasty_targets") or {}).get("if_they_fall_from_current_board") or []),
        "Trevor Lawrence",
    )
    if law_available and "lawrence" in text:
        passes.append("Discusses Trevor Lawrence")
    elif law_available and dak_primary:
        issues.append("Pushes Dak while Lawrence is available with higher dynasty OVR")

    if re.search(r"falls_to_you|top_available_sim", text) and not re.search(
        r"sim|informational|might be on the board|not.*recommend", text
    ):
        issues.append("Cites falls_to_you / sim board without qualifying it as informational")

    if re.search(r"(younger|youth|age|26|27).*(qb|quarterback)", text):
        passes.append("Discusses youth/age at QB")

    score = max(0, 10 - 2 * len(issues) + min(3, len(passes)))
    return {
        "score_0_10": min(10, score),
        "passes": passes,
        "issues": issues,
        "recommends_dak_primary": dak_primary,
    }


def _print_audit(audit: dict[str, Any]) -> None:
    print("=== Context audit ===")
    print(f"Next pick: #{audit.get('pick_no')} | Bookend: {audit.get('bookend_picks')} | Until yours: {audit.get('picks_until_mine')}")
    print(f"Primary lens: {audit.get('decision_primary_lens')}")
    tq = audit.get("top_dynasty_qb")
    if tq:
        print(f"Top projected dynasty QB: {tq['name']} (Dyn {tq.get('dynasty_rating')}, age {tq.get('age')})")
    planned = audit.get("current_planned_pair") or []
    if planned:
        pair = ", ".join(
            f"{p['name']} ({p.get('pos')}, Dyn {p.get('dynasty_rating')}, ADP {p.get('adp_pick')})"
            for p in planned
        )
        print(f"Projected current pair: {pair}")
    print("\nDynasty QBs (top 6):")
    for q in audit.get("dynasty_qbs_top6") or []:
        print(f"  {q['name']:<22} Dyn={q.get('dynasty_rating')} age={q.get('age')} ADP={q.get('adp_pick')}")
    contingency = audit.get("fall_contingency_qbs_top6") or []
    if contingency:
        print("\nIf current-board QBs fall:")
        for q in contingency:
            print(f"  {q['name']:<22} Dyn={q.get('dynasty_rating')} age={q.get('age')} ADP={q.get('adp_pick')}")
    for w in audit.get("warnings") or []:
        print(f"\n⚠ {w}")
    for f in audit.get("findings") or []:
        print(f"\nFinding: {json.dumps(f, indent=2)}")


def main() -> int:
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(description="Audit and optionally call the Pickbook advisor.")
    parser.add_argument("--call-llm", action="store_true", help="Call Anthropic advisor after audit")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Advisor model id")
    parser.add_argument("--question", default="", help="Override user question")
    parser.add_argument("--json", action="store_true", help="Print JSON report only")
    args = parser.parse_args()

    config = load_config()
    state = build_state(config, exit_on_error=False)
    context = build_advisor_context(state)
    question = args.question.strip() or _bookend_question(state)
    audit = audit_context(state, context)

    report: dict[str, Any] = {
        "question": question,
        "audit": audit,
    }

    if args.call_llm:
        api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
        if not api_key:
            print("ANTHROPIC_API_KEY not set; skipping LLM call.", file=sys.stderr)
        else:
            model_row = advisor_model_by_id(args.model)
            print(f"Calling {model_row['label']}…", file=sys.stderr)
            reply = evaluate_picks(state, api_key, user_question=question, model=args.model)
            report["llm"] = {
                "model": args.model,
                "reply": reply,
                "evaluation": evaluate_response(reply, state, context),
            }

    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        _print_audit(audit)
        if "llm" in report:
            ev = report["llm"]["evaluation"]
            print("\n=== Advisor reply (excerpt) ===")
            reply = report["llm"]["reply"]
            print(reply[:2500] + ("…" if len(reply) > 2500 else ""))
            print(f"\n=== Response rubric (score {ev['score_0_10']}/10) ===")
            for p in ev["passes"]:
                print(f"  ✓ {p}")
            for i in ev["issues"]:
                print(f"  ✗ {i}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
