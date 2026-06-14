"""Compare team OVR rankings under spread permutations (read-only)."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Callable

from sqlalchemy import desc, select

from backend.db.models import League, LeagueSnapshotHistory, PlayerSnapshot, Roster, RosterPlayer
from backend.db.session import SessionLocal
from backend.services.analysis_service import (
    LINEUP_PPG_FIELDS,
    TEAM_CORE_BENCH_COUNT,
    TEAM_CORE_BENCH_WEIGHT,
    TEAM_DEPTH_WEIGHT,
    _finalize_team_lineup,
    _player_row_from_snapshot,
)
from backend.services.league_context import build_league_scoring_context
from dynasty_draft.draft_context import _assign_lineup
from dynasty_draft.dynasty_score import RATING_MAX, RATING_MIN, curved_composite_to_rating
from dynasty_draft.war_data import WarData


def _weighted_rating(players: list[tuple[dict[str, Any], float]]) -> int:
    total = 0.0
    weight_total = 0.0
    for player, weight in players:
        rating = player.get("dynasty_rating")
        if rating is None:
            continue
        total += float(rating) * weight
        weight_total += weight
    return round(total / weight_total) if weight_total else 0


def _team_ovr(
    starters: list[dict[str, Any]],
    bench: list[dict[str, Any]],
    *,
    bench_count: int = TEAM_CORE_BENCH_COUNT,
    bench_weight: float = TEAM_CORE_BENCH_WEIGHT,
    depth_weight: float = TEAM_DEPTH_WEIGHT,
) -> int:
    starter_players = [
        row["player"]
        for row in starters
        if row.get("player") and row["player"].get("dynasty_rating") is not None
    ]
    bench_players = [p for p in bench if p.get("dynasty_rating") is not None]
    bench_by_rating = sorted(
        bench_players,
        key=lambda p: float(p.get("dynasty_rating") or 0),
        reverse=True,
    )
    core_bench = bench_by_rating[:bench_count]
    depth = bench_by_rating[bench_count:]
    weighted = (
        [(p, 1.0) for p in starter_players]
        + [(p, bench_weight) for p in core_bench]
        + [(p, depth_weight) for p in depth]
    )
    return _weighted_rating(weighted)


def _starter_avg(starters: list[dict[str, Any]]) -> int:
    ratings = [
        row["player"]["dynasty_rating"]
        for row in starters
        if row.get("player") and row["player"].get("dynasty_rating") is not None
    ]
    return round(sum(ratings) / len(ratings)) if ratings else 0


def _league_stretch_linear(values: dict[str, int], *, lo: int = 58, hi: int = 96) -> dict[str, int]:
    nums = list(values.values())
    if not nums:
        return values
    mn, mx = min(nums), max(nums)
    if mx == mn:
        mid = round((lo + hi) / 2)
        return {k: mid for k in values}
    span = mx - mn
    return {k: round(lo + (v - mn) / span * (hi - lo)) for k, v in values.items()}


def _league_stretch_sqrt(values: dict[str, int], *, lo: int = 58, hi: int = 96) -> dict[str, int]:
    nums = list(values.values())
    if not nums:
        return values
    mn, mx = min(nums), max(nums)
    if mx == mn:
        mid = round((lo + hi) / 2)
        return {k: mid for k in values}
    out: dict[str, int] = {}
    for k, v in values.items():
        p = (v - mn) / (mx - mn)
        out[k] = round(lo + (hi - lo) * math.sqrt(p))
    return out


def _rerate_players(
    snapshots: dict[str, PlayerSnapshot],
    bounds: tuple[float, float],
    exponent: float,
) -> dict[str, int]:
    out: dict[str, int] = {}
    for pid, snap in snapshots.items():
        score = snap.dynasty_score
        if score is None:
            continue
        out[pid] = curved_composite_to_rating(
            float(score),
            raw_min=bounds[0],
            raw_max=bounds[1],
            exponent=exponent,
        )
    return out


def _build_teams(
    db,
    league_id: str,
    war: WarData,
    rating_by_id: dict[str, int] | None = None,
) -> list[dict[str, Any]]:
    league_row = db.get(League, league_id)
    context = build_league_scoring_context(league_row)
    snapshots = {
        row.sleeper_player_id: row
        for row in db.scalars(select(PlayerSnapshot).where(PlayerSnapshot.league_id == league_id)).all()
    }
    teams: list[dict[str, Any]] = []
    for roster in db.scalars(select(Roster).where(Roster.league_id == league_id)).all():
        player_rows = []
        for rp in db.scalars(select(RosterPlayer).where(RosterPlayer.roster_id == roster.id)).all():
            snap = snapshots.get(rp.sleeper_player_id)
            if snap is None:
                continue
            row = _player_row_from_snapshot(snap, war)
            if rating_by_id and rp.sleeper_player_id in rating_by_id:
                row = {**row, "dynasty_rating": rating_by_id[rp.sleeper_player_id]}
            player_rows.append(row)
        lineup = _finalize_team_lineup(player_rows, context.roster_positions)
        teams.append(
            {
                "roster_id": str(roster.sleeper_roster_id),
                "team_name": roster.team_name or f"Team {roster.sleeper_roster_id}",
                "starters": lineup["starters"],
                "bench": lineup["bench"],
                "avg_dynasty_rating": lineup["avg_dynasty_rating"],
                "starter_avg_dynasty_rating": lineup["starter_avg_dynasty_rating"],
            }
        )
    return teams


def _team_scores(
    teams: list[dict[str, Any]],
    scorer: Callable[[list[dict[str, Any]], list[dict[str, Any]]], int],
) -> dict[str, int]:
    return {
        t["roster_id"]: scorer(t["starters"], t["bench"])
        for t in teams
    }


def _rank(scores: dict[str, int]) -> list[tuple[str, int, int]]:
    ordered = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [(rid, ovr, rank) for rank, (rid, ovr) in enumerate(ordered, start=1)]


def main() -> None:
    db = SessionLocal()
    war = WarData(Path("war.csv"))
    try:
        leagues = db.scalars(select(League)).all()
        if not leagues:
            print("No leagues in DB")
            return

        for league in leagues:
            league_id = league.sleeper_league_id
            hist = db.scalar(
                select(LeagueSnapshotHistory)
                .where(LeagueSnapshotHistory.league_id == league_id)
                .order_by(desc(LeagueSnapshotHistory.computed_at))
                .limit(1)
            )
            bounds_raw = (hist.anchors_json or {}).get("rating_bounds") if hist else None
            bounds = (float(bounds_raw[0]), float(bounds_raw[1])) if bounds_raw else (0.0, 1.0)

            snapshots = {
                row.sleeper_player_id: row
                for row in db.scalars(select(PlayerSnapshot).where(PlayerSnapshot.league_id == league_id)).all()
            }

            teams_current = _build_teams(db, league_id, war)
            name_by_id = {t["roster_id"]: t["team_name"] for t in teams_current}

            scenarios: dict[str, dict[str, int]] = {}

            # A: current production formula
            scenarios["A current"] = {
                t["roster_id"]: t["avg_dynasty_rating"] for t in teams_current
            }

            # B/C: higher exponent re-curves player ratings, then standard team weighting
            for label, exp in [("B exp=0.65", 0.65), ("C exp=0.75", 0.75)]:
                rerated = _rerate_players(snapshots, bounds, exp)
                teams = _build_teams(db, league_id, war, rerated)
                scenarios[label] = _team_scores(
                    teams,
                    lambda s, b: _team_ovr(s, b),
                )

            # D: starter average only (current player ratings)
            scenarios["D starter avg"] = {
                t["roster_id"]: t["starter_avg_dynasty_rating"] for t in teams_current
            }

            # E: starters only, no bench contribution
            scenarios["E no bench"] = _team_scores(
                teams_current,
                lambda s, b: _team_ovr(s, b, bench_weight=0.0, depth_weight=0.0),
            )

            # F/G: league-relative stretch on current team OVR
            base = scenarios["A current"]
            scenarios["F stretch 58-96"] = _league_stretch_linear(base)
            scenarios["G stretch sqrt"] = _league_stretch_sqrt(base)

            # H: exp 0.65 then league stretch
            scenarios["H exp0.65+stretch"] = _league_stretch_linear(scenarios["B exp=0.65"])

            print(f"\n{'=' * 72}")
            print(f"League: {league.name} ({league_id})")
            print(f"Teams: {len(teams_current)}  |  rating_bounds: {bounds[0]:.3f} – {bounds[1]:.3f}")
            print(f"{'=' * 72}")

            # Spread summary
            print("\nSpread (max − min OVR):")
            for label, scores in scenarios.items():
                vals = list(scores.values())
                print(f"  {label:22s}  min={min(vals):2d}  max={max(vals):2d}  spread={max(vals)-min(vals):2d}")

            # Rankings table
            roster_ids = [t["roster_id"] for t in teams_current]
            print("\nRankings (team name | OVR per scenario):")
            header = f"{'Team':<22}" + "".join(f"{k[:12]:>13}" for k in scenarios)
            print(header)
            print("-" * len(header))

            # Sort by current rank
            current_rank = {rid: r for rid, _, r in _rank(scenarios["A current"])}
            for rid in sorted(roster_ids, key=lambda r: current_rank[r]):
                name = (name_by_id.get(rid) or rid)[:21]
                row = f"{name:<22}"
                for label, scores in scenarios.items():
                    ovr = scores[rid]
                    rank = next(r for r, (rrid, _, rr) in enumerate(_rank(scores), 1) if rrid == rid)
                    row += f"{ovr:3d} (#{rank:2d})".rjust(13)
                print(row)

            # Rank changes vs current
            print("\nRank changes vs A current:")
            base_rank = {rid: r for rid, _, r in _rank(scenarios["A current"])}
            for label in scenarios:
                if label == "A current":
                    continue
                moves = []
                for rid, _, r in _rank(scenarios[label]):
                    delta = base_rank[rid] - r
                    if delta:
                        moves.append((abs(delta), rid, delta))
                moves.sort(reverse=True)
                if not moves:
                    print(f"  {label}: no rank changes")
                else:
                    parts = [
                        f"{name_by_id[rid][:16]} {'+' if d > 0 else ''}{d}"
                        for _, rid, d in moves[:5]
                    ]
                    print(f"  {label}: {', '.join(parts)}")

    finally:
        db.close()


if __name__ == "__main__":
    main()
