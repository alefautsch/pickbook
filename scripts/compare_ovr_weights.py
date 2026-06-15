#!/usr/bin/env python3
"""Compare dynasty OVR under weight / per-game tilt permutations for a league."""

from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import replace
from typing import Any

from sqlalchemy import desc, select

from backend.api.settings import _read_settings
from backend.db.models import League, PlayerSnapshot, Roster, RosterPlayer
from backend.db.session import SessionLocal
from backend.services.league_engine import build_league_scoring_state
from backend.services.sync_service import _resolve_my_user_id
from dynasty_draft.dynasty_score import DynastyRatingCurve, DynastyWeights
from dynasty_draft.sleeper_client import SleeperClient


def _collect_rostered_player_ids(db, league_id: str) -> set[str]:
    rows = db.execute(
        select(RosterPlayer.sleeper_player_id)
        .join(Roster, Roster.id == RosterPlayer.roster_id)
        .where(Roster.league_id == league_id)
    ).all()
    return {str(r[0]) for r in rows}


def _score_with_overrides(state, *, weights: DynastyWeights, curve: DynastyRatingCurve) -> dict[str, dict[str, Any]]:
    state.dynasty_weights = weights
    state.dynasty_rating_curve = curve
    state._cached_dynasty_scorer = None  # noqa: SLF001
    return state.dynasty_scores()


def _fmt_row(name: str, pos: str, before: int, after: int, comps: dict[str, Any] | None = None) -> str:
    delta = after - before
    sign = f"+{delta}" if delta > 0 else str(delta)
    line = f"{name:<24} {pos:2s}  {before:3d} → {after:3d}  ({sign:>3s})"
    if comps:
        line += (
            f"  tv={comps.get('tv', 0):.2f} worp={comps.get('worp', 0):.2f}"
            f" pg={comps.get('per_game')}"
        )
    return line


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--league-id", default="1314731206859853824")
    parser.add_argument(
        "--names",
        nargs="*",
        help="Player names (default: top 25 by current OVR + named extras)",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        league = db.get(League, args.league_id)
        if league is None:
            raise SystemExit(f"League not found: {args.league_id}")

        settings = dict(_read_settings(db))
        client = SleeperClient()
        roster_ids = _collect_rostered_player_ids(db, args.league_id)
        user_id = _resolve_my_user_id(client, settings)
        state = build_league_scoring_state(
            league_row=league,
            roster_player_ids=roster_ids,
            user_id=user_id,
            settings=settings,
            client=client,
        )

        baseline_weights = DynastyWeights.from_config(settings.get("dynasty_weights"))
        baseline_curve = DynastyRatingCurve.from_config(settings.get("dynasty_rating_curve"))
        prod_weights = replace(baseline_weights, tv=0.38, worp=0.32)
        prod_curve = replace(baseline_curve, per_game_tilt=0.72)

        baseline = _score_with_overrides(state, weights=baseline_weights, curve=baseline_curve)
        adjusted = _score_with_overrides(state, weights=prod_weights, curve=prod_curve)

        if args.names:
            name_filter = {n.lower() for n in args.names}
            pool = [
                (pid, p)
                for pid, p in state.snapshot_pool()
                if p.name.lower() in name_filter
                or any(n in p.name.lower() for n in name_filter)
            ]
        else:
            snaps = db.scalars(
                select(PlayerSnapshot)
                .where(PlayerSnapshot.league_id == args.league_id)
                .order_by(desc(PlayerSnapshot.dynasty_rating))
                .limit(25)
            ).all()
            name_filter = {s.player_name.lower() for s in snaps}
            pool = [
                (pid, p)
                for pid, p in state.snapshot_pool()
                if p.name.lower() in name_filter
            ]

        pool.sort(
            key=lambda item: baseline.get(item[0], {}).get("dynasty_rating") or 0,
            reverse=True,
        )

        print(f"League: {league.name} ({args.league_id})")
        print(
            f"Baseline: tv={baseline_weights.tv} worp={baseline_weights.worp} "
            f"tilt={baseline_curve.per_game_tilt}  |  "
            f"Adjusted: tv={prod_weights.tv} worp={prod_weights.worp} "
            f"tilt={prod_curve.per_game_tilt}"
        )
        print()
        print(f"{'Player':<24} {'Pos':2s}  {'Before':>6}   {'After':>5}  {'Δ':>4}")
        print("-" * 52)

        deltas: list[tuple[str, int]] = []
        for player_id, player in pool:
            b = baseline.get(player_id) or {}
            a = adjusted.get(player_id) or {}
            br = int(b.get("dynasty_rating") or 0)
            ar = int(a.get("dynasty_rating") or 0)
            if br == 0 and ar == 0:
                continue
            deltas.append((player.name, ar - br))
            print(_fmt_row(player.name, player.pos, br, ar, a.get("dynasty_components")))

        if deltas:
            avg_delta = sum(d for _, d in deltas) / len(deltas)
            print()
            print(f"Avg Δ across {len(deltas)} players: {avg_delta:+.1f}")
            biggest_up = max(deltas, key=lambda x: x[1])
            biggest_down = min(deltas, key=lambda x: x[1])
            print(f"Largest rise: {biggest_up[0]} ({biggest_up[1]:+d})")
            print(f"Largest drop: {biggest_down[0]} ({biggest_down[1]:+d})")
    finally:
        db.close()


if __name__ == "__main__":
    main()
