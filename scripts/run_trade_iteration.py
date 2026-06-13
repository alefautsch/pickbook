#!/usr/bin/env python3
"""Run trade suggestions locally against live league data (API or local DB).

Usage:
  uv run python scripts/run_trade_iteration.py
  uv run python scripts/run_trade_iteration.py --target 2
  uv run python scripts/run_trade_iteration.py --validate
  uv run python scripts/run_trade_iteration.py --db
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from typing import Any

# Defaults: GLA / The Process
DEFAULT_LEAGUE = "1314731206859853824"
DEFAULT_ROSTER = "3"
DEFAULT_API = os.environ.get(
    "API_BASE",
    os.environ.get("NEXT_PUBLIC_API_URL", "https://dynasty-bb.up.railway.app"),
)


def _get_json(url: str) -> Any:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode())


def _api_get(base: str, path: str) -> Any:
    base = base.rstrip("/")
    if path.startswith("/api/blackbook"):
        url = f"{base}{path}"
    else:
        url = f"{base}/api/blackbook{path}"
    return _get_json(url)


def _player_row(card: dict[str, Any]) -> dict[str, Any]:
    return {
        "player_id": card["player_id"],
        "name": card.get("player_name"),
        "position": card.get("position"),
        "pos": card.get("position"),
        "ovr": card.get("ovr"),
        "tv": card.get("trade_value"),
        "hppg": card.get("hppg"),
        "projected_ppg": card.get("projected_ppg"),
        "age": card.get("age"),
        "trade_tag": card.get("trade_tag"),
        "lineup_delta_ppg": card.get("lineup_delta_ppg"),
    }


def _pick_row(pick: dict[str, Any]) -> dict[str, Any]:
    return {
        "season": pick["season"],
        "round": pick["round"],
        "original_roster_id": pick["original_roster_id"],
        "owner_roster_id": pick.get("owner_roster_id"),
        "slot_tier": pick.get("slot_tier"),
        "trade_value": pick.get("trade_value"),
        "label": pick.get("label"),
        "is_own_slot": pick.get("is_own_slot"),
    }


def load_from_api(
    api_base: str,
    league_id: str,
    my_roster_id: str,
) -> tuple[dict[str, Any], dict[str, list], dict[str, list], dict[str, str]]:
    analysis = _api_get(api_base, f"/leagues/{league_id}/analysis")
    trade_surplus = analysis.get("trade_surplus")
    rankings = _api_get(api_base, f"/leagues/{league_id}/rankings")

    contender_tier_by_roster = {
        str(row["roster_id"]): row.get("contender_tier") or "competitive"
        for row in rankings.get("by_dynasty", [])
    }

    roster_ids = [str(row["roster_id"]) for row in rankings.get("by_dynasty", [])]
    roster_players: dict[str, list[dict[str, Any]]] = {}
    picks_by_roster: dict[str, list[dict[str, Any]]] = {}

    team_names: dict[str, str] = {}

    for rid in roster_ids:
        team = _api_get(api_base, f"/leagues/{league_id}/teams/{rid}")
        team_names[rid] = team.get("team_name") or rid
        roster_players[rid] = [_player_row(p) for p in team.get("roster", [])]
        picks_by_roster[rid] = [_pick_row(p) for p in team.get("draft_picks", [])]

    return trade_surplus, roster_players, picks_by_roster, contender_tier_by_roster, team_names


def load_from_db(league_id: str, my_roster_id: str):
    from sqlalchemy import select

    from backend.db.models import LeagueSnapshot, PlayerSnapshot, Roster
    from backend.db.session import SessionLocal
    from backend.services.advisor_tools import _players_for_roster
    from backend.services.pick_service import get_roster_draft_picks

    with SessionLocal() as db:
        snap = db.scalar(
            select(LeagueSnapshot)
            .where(LeagueSnapshot.league_id == league_id)
            .order_by(LeagueSnapshot.computed_at.desc())
            .limit(1)
        )
        if snap is None:
            raise SystemExit(f"No snapshot for league {league_id}")

        trade_surplus = (snap.analysis_json or {}).get("trade_surplus")
        rankings = snap.rankings_json or {}
        contender_tier_by_roster = {
            str(row["roster_id"]): row.get("contender_tier") or "competitive"
            for row in rankings.get("by_dynasty", [])
        }

        snapshots = {
            row.sleeper_player_id: row
            for row in db.scalars(
                select(PlayerSnapshot).where(PlayerSnapshot.league_id == league_id)
            ).all()
        }

        roster_players: dict[str, list] = {}
        picks_by_roster: dict[str, list] = {}
        team_names: dict[str, str] = {}
        for roster in db.scalars(select(Roster).where(Roster.league_id == league_id)).all():
            rid = roster.sleeper_roster_id
            team_names[rid] = roster.team_name or rid
            from backend.services.advisor_tools import AdvisorTools, AdvisorToolContext

            ctx = AdvisorToolContext(
                db=db, league_id=league_id, my_roster_id=my_roster_id, focused_roster_id=my_roster_id
            )
            tools = AdvisorTools(ctx)
            pids = tools._roster_player_ids(rid)
            roster_players[rid] = _players_for_roster(snapshots, pids)
            picks_by_roster[rid] = get_roster_draft_picks(db, league_id, rid)

    return trade_surplus, roster_players, picks_by_roster, contender_tier_by_roster, team_names


def _fmt_asset(asset: dict[str, Any]) -> str:
    if asset.get("player_id"):
        name = asset.get("name") or asset.get("player_name") or asset["player_id"]
        pos = asset.get("position") or "?"
        tv = asset.get("tv") or asset.get("trade_value")
        tag = asset.get("trade_tag")
        extra = f" [{tag}]" if tag else ""
        return f"{name} ({pos}, TV {tv:.0f}){extra}" if tv else f"{name} ({pos}){extra}"
    label = asset.get("label") or f"{asset.get('season')} R{asset.get('round')}"
    tv = asset.get("trade_value") or asset.get("tv")
    return f"{label} (TV {tv:.0f})" if tv else label


def _print_package(i: int, pkg: dict[str, Any]) -> None:
    cp = pkg.get("counterparty") or {}
    target = cp.get("target_player_name")
    header = cp.get("direction", "?").upper()
    if target:
        header = f"ACQUIRE {target}"
    print(f"\n{'='*72}")
    print(
        f"PACKAGE {i} — {header} {cp.get('position_hook') or ''} vs "
        f"{cp.get('team_name') or 'roster ' + str(cp.get('roster_id'))}"
    )
    tag = cp.get("target_trade_tag")
    if cp.get("target_tv"):
        extra = f" | target TV {cp['target_tv']:.0f}"
        if tag:
            extra += f" [{tag}]"
        if cp.get("target_age") is not None:
            extra += f" age {cp['target_age']}"
        print(f"  Target:{extra}")
    if cp.get("trade_pattern"):
        print(f"  Pattern: {cp['trade_pattern']}")
    if pkg.get("stretch"):
        print("  Note: stretch package (outside normal overpay band — negotiation opener)")
    print(f"  Their tier: {cp.get('contender_tier')} | Fairness: {pkg.get('fairness')} ({pkg.get('net_delta_adjusted_pct')}%)")
    print(f"  Quality: {pkg.get('package_quality')} | Fit: {pkg.get('avg_trade_fit')}")

    give = pkg.get("give") or {}
    recv = pkg.get("receive") or {}
    print("  YOU GIVE:")
    for p in give.get("players") or []:
        print(f"    - {_fmt_asset(p)}")
    for p in give.get("picks") or []:
        print(f"    - {_fmt_asset(p)}")
    print("  YOU RECEIVE:")
    for p in recv.get("players") or []:
        print(f"    - {_fmt_asset(p)}")
    for p in recv.get("picks") or []:
        print(f"    - {_fmt_asset(p)}")
    print(f"  TV: give {pkg.get('give_total_tv')} → recv {pkg.get('receive_total_tv')} | adj {pkg.get('give_adjusted_tv')} → {pkg.get('receive_adjusted_tv')}")
    if pkg.get("give_value_adjustment") or pkg.get("receive_value_adjustment"):
        print(
            f"  KTC adj: give +{pkg.get('give_value_adjustment')} | recv +{pkg.get('receive_value_adjustment')}"
        )
    if pkg.get("rationale"):
        print(f"  Rationale: {pkg['rationale']}")
    cv = pkg.get("counterparty_validation")
    if cv and not cv.get("error") and not cv.get("skipped"):
        score = pkg.get("validation_accept_score")
        score_s = f" ({score:.2f})" if score is not None else ""
        print(
            f"  Validation: accept={cv.get('accept_likelihood')}{score_s} | "
            f"fairness={cv.get('fairness_from_counterparty_view')} | "
            f"improves them={cv.get('would_improve_their_roster')}"
        )
        if cv.get("blockers"):
            print(f"  Blockers: {', '.join(cv['blockers'][:3])}")


def _print_trade_tags(roster: list[dict[str, Any]], label: str) -> None:
    print(f"\n--- {label} trade tags ---")
    for p in sorted(roster, key=lambda x: x.get("tv") or 0, reverse=True):
        tag = p.get("trade_tag")
        if not tag:
            continue
        print(
            f"  {p.get('name')}: {tag} | delta {p.get('lineup_delta_ppg')} | TV {p.get('tv')}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run trade suggestion iterations")
    parser.add_argument("--league", default=DEFAULT_LEAGUE)
    parser.add_argument("--roster", default=DEFAULT_ROSTER)
    parser.add_argument("--api", default=DEFAULT_API)
    parser.add_argument("--db", action="store_true", help="Use local DATABASE_URL")
    parser.add_argument("--picks", action="store_true", help="Show Sleeper pick inventory for your roster")
    parser.add_argument("--target", help="Filter to counterparty roster_id")
    parser.add_argument("--player", help="Target player_id for stud acquisition (e.g. 12507 Hampton)")
    parser.add_argument("--position", help="Acquire key players at position league-wide (RB, WR, …)")
    parser.add_argument("--use-101", action="store_true", help="Allow packages including 2026 1.01 (premium mode)")
    parser.add_argument("--swap", action="store_true", help="Need-swap mode: surplus + depth for stud + depth")
    parser.add_argument("--need", help="Need position for --swap (RB, WR, TE)")
    parser.add_argument("--validate", action="store_true", help="Run validate_trade on package 1")
    parser.add_argument(
        "--rank-validation",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Re-rank packages by counterparty accept_likelihood (default on; needs ANTHROPIC_API_KEY)",
    )
    parser.add_argument("--json", action="store_true", help="Dump raw JSON")
    args = parser.parse_args()

    if args.picks:
        from backend.services.pick_service import build_league_pick_inventory, collect_league_traded_picks
        from dynasty_draft.sleeper_client import SleeperClient

        client = SleeperClient()
        remote = client.get_league(args.league)
        rosters = client.get_rosters(args.league)
        traded = collect_league_traded_picks(client, args.league)
        inv = build_league_pick_inventory(
            league_remote=remote, rosters=rosters, traded_picks=traded
        )
        mine = [r for r in inv if str(r["owner_roster_id"]) == str(args.roster)]
        print(f"Sleeper pick inventory for roster {args.roster} ({len(mine)} slots)")
        for row in sorted(mine, key=lambda r: (r["season"], r["round"], r["original_roster_id"])):
            own = "own" if row["original_roster_id"] == row["owner_roster_id"] else "via"
            print(
                f"  {row['season']} R{row['round']} orig={row['original_roster_id']} ({own})"
            )
        print(f"(merged {len(traded)} traded_picks from league + drafts)")
        return

    from backend.services.advisor_tools import (
        evaluate_trade_package,
        generate_need_swap_packages,
        generate_position_acquisition_packages,
        generate_trade_suggestions,
        rank_packages_by_counterparty_validation,
    )

    if args.db:
        print("Loading from local DB…")
        trade_surplus, roster_players, picks_by_roster, tiers, team_names = load_from_db(
            args.league, args.roster
        )
    else:
        print(f"Loading from API {args.api}…")
        trade_surplus, roster_players, picks_by_roster, tiers, team_names = load_from_api(
            args.api, args.league, args.roster
        )

    my_roster = roster_players.get(str(args.roster), [])
    _print_trade_tags(my_roster, "Your roster")

    ts = trade_surplus or {}
    print("\n--- Trade surplus ---")
    print("  Surplus:", [s["position"] for s in ts.get("surplus") or []])
    print("  Needs:", [n["position"] for n in ts.get("needs") or []])
    print(f"  Counterparty hooks: {len(ts.get('counterparties') or [])}")
    if not args.use_101:
        print("  Mode: lubricant (2026 1.01 reserved — use --use-101 for premium packages)")

    keep_first = not args.use_101
    lubricant = not args.use_101

    if args.swap:
        packages = generate_need_swap_packages(
            my_roster_id=str(args.roster),
            roster_players=roster_players,
            picks_by_roster=picks_by_roster,
            trade_surplus=trade_surplus,
            contender_tier_by_roster=tiers,
            team_names=team_names,
            need_position=args.need or (args.position if args.position else None),
            target_player_id=args.player,
            keep_current_first=keep_first,
            lubricant_mode=lubricant,
        )
    elif args.position and not args.player and not args.target:
        packages = generate_position_acquisition_packages(
            my_roster_id=str(args.roster),
            target_position=args.position,
            roster_players=roster_players,
            picks_by_roster=picks_by_roster,
            trade_surplus=trade_surplus,
            contender_tier_by_roster=tiers,
            team_names=team_names,
            keep_current_first=keep_first,
            lubricant_mode=lubricant,
        )
    else:
        packages = generate_trade_suggestions(
            my_roster_id=str(args.roster),
            trade_surplus=trade_surplus,
            roster_players=roster_players,
            picks_by_roster=picks_by_roster,
            target_roster_id=args.target,
            target_player_id=args.player,
            target_position=args.position,
            contender_tier_by_roster=tiers,
            keep_current_first=keep_first,
            lubricant_mode=lubricant,
        )

    if args.rank_validation and packages:
        from backend.config import get_settings

        def resolve_player(pid: str):
            for rows in roster_players.values():
                for row in rows:
                    if str(row.get("player_id")) == str(pid):
                        return row
            return None

        def resolve_pick(pick: dict):
            owner = picks_by_roster.get(str(args.roster), [])
            key = (str(pick["season"]), int(pick["round"]), str(pick["original_roster_id"]))
            for row in owner:
                rk = (str(row["season"]), int(row["round"]), str(row["original_roster_id"]))
                if rk == key:
                    return row
            cp_id = str(pick.get("counterparty_roster_id") or "")
            for row in picks_by_roster.get(cp_id, []):
                rk = (str(row["season"]), int(row["round"]), str(row["original_roster_id"]))
                if rk == key:
                    return row
            for rows in picks_by_roster.values():
                for row in rows:
                    rk = (str(row["season"]), int(row["round"]), str(row["original_roster_id"]))
                    if rk == key:
                        return row
            return None

        def load_team(rid: str) -> dict[str, Any]:
            if args.db:
                from sqlalchemy import select

                from backend.db.models import LeagueSnapshot, Roster
                from backend.db.session import SessionLocal
                from backend.services.advisor_tools import AdvisorTools, AdvisorToolContext

                with SessionLocal() as db:
                    ctx = AdvisorToolContext(
                        db=db,
                        league_id=args.league,
                        my_roster_id=str(args.roster),
                        focused_roster_id=str(args.roster),
                    )
                    return AdvisorTools(ctx).get_team(rid)
            team = _api_get(args.api, f"/leagues/{args.league}/teams/{rid}")
            return {
                "team_name": team.get("team_name"),
                "contender_tier": team.get("contender_tier"),
                "dynasty_rank": team.get("dynasty_rank"),
                "surplus": [],
                "needs": [],
                "draft_picks": team.get("draft_picks"),
                "players": [_player_row(p) for p in team.get("roster", [])],
            }

        settings = get_settings()
        if settings.anthropic_api_key:
            print("\nRanking top packages by counterparty validation…")
            packages = rank_packages_by_counterparty_validation(
                packages,
                my_roster_id=str(args.roster),
                resolve_player=resolve_player,
                resolve_pick=resolve_pick,
                load_team=load_team,
                trade_surplus=trade_surplus,
                api_key=settings.anthropic_api_key,
            )
        else:
            print("\nSkipping validation ranking (ANTHROPIC_API_KEY not set)")

    mode = (
        f"NEED SWAP{f' ({args.need})' if args.need else ''}"
        if args.swap
        else f"KEY {args.position.upper()} ACQUISITION"
        if args.position and not args.player and not args.target
        else "ACQUISITION"
        if args.player or (args.target and args.position)
        else "SURPLUS"
    )

    print(f"\n{'#'*72}\n{mode} SUGGESTIONS ({len(packages)} packages)\n{'#'*72}")
    if not packages:
        print("  (none — no matching trade hooks or empty give pools)")
    for i, pkg in enumerate(packages, 1):
        _print_package(i, pkg)

    if args.json:
        print("\n--- RAW JSON ---")
        print(json.dumps(packages, indent=2, default=str))

    if args.validate and packages:
        from backend.config import get_settings
        from backend.services.trade_validation_service import (
            build_validation_payload,
            validate_trade_with_llm,
        )
        from backend.services.advisor_tools import evaluate_trade_package

        pkg = packages[0]
        cp_id = str((pkg.get("counterparty") or {}).get("roster_id"))
        give_players = [p["player_id"] for p in (pkg.get("give") or {}).get("players") or []]
        recv_players = [p["player_id"] for p in (pkg.get("receive") or {}).get("players") or []]
        give_picks = [
            {
                "season": p["season"],
                "round": p["round"],
                "original_roster_id": p["original_roster_id"],
            }
            for p in (pkg.get("give") or {}).get("picks") or []
        ]
        recv_picks = [
            {
                "season": p["season"],
                "round": p["round"],
                "original_roster_id": p["original_roster_id"],
            }
            for p in (pkg.get("receive") or {}).get("picks") or []
        ]

        def resolve_player(pid: str):
            for rows in roster_players.values():
                for row in rows:
                    if str(row.get("player_id")) == str(pid):
                        return row
            return None

        def resolve_pick(pick: dict):
            owner = picks_by_roster.get(str(args.roster), [])
            cp = picks_by_roster.get(cp_id, [])
            key = (str(pick["season"]), int(pick["round"]), str(pick["original_roster_id"]))
            for row in owner + cp:
                rk = (str(row["season"]), int(row["round"]), str(row["original_roster_id"]))
                if rk == key:
                    return row
            return None

        eval_result = evaluate_trade_package(
            {"players": give_players, "picks": give_picks},
            {"players": recv_players, "picks": recv_picks},
            resolve_player=resolve_player,
            resolve_pick=resolve_pick,
        )

        my_team_api = _api_get(args.api, f"/leagues/{args.league}/teams/{args.roster}")
        their_team_api = _api_get(args.api, f"/leagues/{args.league}/teams/{cp_id}")

        payload = build_validation_payload(
            proposer_roster_id=str(args.roster),
            counterparty_roster_id=cp_id,
            proposer_team={
                "team_name": my_team_api.get("team_name"),
                "contender_tier": my_team_api.get("contender_tier"),
                "dynasty_rank": my_team_api.get("dynasty_rank"),
                "surplus": ts.get("surplus"),
                "needs": ts.get("needs"),
                "draft_picks": my_team_api.get("draft_picks"),
                "players": [_player_row(p) for p in my_team_api.get("roster", [])],
            },
            counterparty_team={
                "team_name": their_team_api.get("team_name"),
                "contender_tier": their_team_api.get("contender_tier"),
                "dynasty_rank": their_team_api.get("dynasty_rank"),
                "surplus": [],
                "needs": [],
                "draft_picks": their_team_api.get("draft_picks"),
                "players": [_player_row(p) for p in their_team_api.get("roster", [])],
            },
            give=eval_result["give"],
            receive=eval_result["receive"],
            tv_evaluation=eval_result,
        )

        print(f"\n{'#'*72}\nVALIDATION (package 1 vs {their_team_api.get('team_name')})\n{'#'*72}")
        validation = validate_trade_with_llm(
            payload, api_key=get_settings().anthropic_api_key
        )
        print(json.dumps(validation, indent=2))


if __name__ == "__main__":
    main()
