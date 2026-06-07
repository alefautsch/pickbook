"""League power rankings + analysis heuristics from snapshots (§8)."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from backend.db.models import LeagueSnapshot, LeagueSnapshotHistory, PlayerSnapshot, Roster, RosterPlayer
from backend.services.history_service import attach_team_ovr_to_history
from backend.services.league_context import build_league_scoring_context
from dynasty_draft.draft_context import _assign_lineup, _starter_metric
from dynasty_draft.dynasty_score import _PEAK_AGE
from dynasty_draft.war_data import WarData

# Calibrated against seeded 10-team leagues (§14.4): starter quality + weekly ceiling + youth.
CONTENDER_WEIGHTS: dict[str, float] = {
    "starter_ovr": 0.40,
    "starter_ppg": 0.35,
    "age_depth": 0.25,
}
TRADE_SURPLUS_TOP_N = 3
TRADE_SURPLUS_BOTTOM_N = 3


def _player_row_from_snapshot(snapshot: PlayerSnapshot, war: WarData) -> dict[str, Any]:
    war_player = war.lookup(snapshot.player_name or "")
    worp = war_player.worp if war_player else None
    porp = war_player.porp if war_player else None
    return {
        "player_id": snapshot.sleeper_player_id,
        "name": snapshot.player_name,
        "pos": snapshot.position,
        "team": snapshot.nfl_team,
        "age": snapshot.age,
        "trade_value": snapshot.trade_value,
        "worp": worp,
        "porp": porp,
        "dynasty_rating": snapshot.dynasty_rating,
        "dynasty_score": snapshot.dynasty_score,
        "healthy_ppg": snapshot.hppg,
        "hppg_expected": snapshot.hppg_expected,
        "flex_rating": snapshot.flex_rating,
    }


def _finalize_team_lineup(
    players: list[dict[str, Any]],
    roster_positions: list[str],
) -> dict[str, Any]:
    starters, bench = _assign_lineup(players, roster_positions)
    bench = sorted(bench, key=lambda row: row.get("trade_value") or 0, reverse=True)
    all_players = [row["player"] for row in starters if row.get("player")] + bench
    total_tv = sum(player.get("trade_value") or 0 for player in all_players)
    worp_values = [player.get("worp") for player in all_players if player.get("worp") is not None]
    starter_worp = _starter_metric(starters, "worp")
    starter_porp = _starter_metric(starters, "porp")
    win_now_score = None
    if starter_worp is not None or starter_porp is not None:
        win_now_score = (starter_worp or 0.0) + (starter_porp or 0.0) / 100.0

    starter_ratings = [
        row["player"]["dynasty_rating"]
        for row in starters
        if row.get("player") and row["player"].get("dynasty_rating") is not None
    ]
    all_ratings = [
        player.get("dynasty_rating")
        for player in all_players
        if player.get("dynasty_rating") is not None
    ]
    starter_ppg_values = [
        float(row["player"]["healthy_ppg"])
        for row in starters
        if row.get("player") and row["player"].get("healthy_ppg") is not None
    ]

    return {
        "starters": starters,
        "bench": bench,
        "total_trade_value": total_tv,
        "total_worp": sum(worp_values) if worp_values else None,
        "starter_worp": starter_worp,
        "starter_porp": starter_porp,
        "win_now_score": win_now_score,
        "avg_dynasty_rating": round(sum(all_ratings) / len(all_ratings)) if all_ratings else 0,
        "starter_avg_dynasty_rating": (
            round(sum(starter_ratings) / len(starter_ratings)) if starter_ratings else 0
        ),
        "starter_total_ppg": (
            round(sum(starter_ppg_values), 1) if starter_ppg_values else None
        ),
        "starter_ppg_slots": len(starter_ppg_values),
    }


def _normalize_league(values: list[float | None]) -> list[float | None]:
    """Min-max scale to 0–100 within league; flat field → 50 for all."""
    nums = [v for v in values if v is not None]
    if not nums:
        return [None for _ in values]
    lo, hi = min(nums), max(nums)
    if math.isclose(lo, hi):
        return [50.0 if v is not None else None for v in values]
    span = hi - lo
    return [round((v - lo) / span * 100, 1) if v is not None else None for v in values]


def _youth_factor(age: float | None, position: str | None) -> float | None:
    if age is None:
        return None
    peak = _PEAK_AGE.get(position or "", 27)
    # 1.0 at ~3 years before peak; fades toward 0 past peak + 2.
    return max(0.0, min(1.0, (peak - age + 3.0) / 6.0))


def _weighted_avg(
    rows: list[tuple[float | None, float | None]],
) -> float | None:
    """Average of values weighted by weights; skips rows with missing value or weight."""
    total_w = 0.0
    total_v = 0.0
    for value, weight in rows:
        if value is None or weight is None or weight <= 0:
            continue
        total_v += value * weight
        total_w += weight
    return round(total_v / total_w, 3) if total_w > 0 else None


def _age_depth_score(team: dict[str, Any]) -> float | None:
    starter_rows: list[tuple[float | None, float | None]] = []
    for row in team.get("starters", []):
        player = row.get("player") or {}
        youth = _youth_factor(player.get("age"), player.get("pos"))
        weight = player.get("dynasty_rating")
        starter_rows.append((youth, float(weight) if weight is not None else None))

    bench_rows: list[tuple[float | None, float | None]] = []
    for player in sorted(team.get("bench", []), key=lambda p: p.get("trade_value") or 0, reverse=True)[:4]:
        youth = _youth_factor(player.get("age"), player.get("pos"))
        weight = player.get("trade_value") or player.get("dynasty_rating")
        bench_rows.append((youth, float(weight) if weight is not None else None))

    starter_youth = _weighted_avg(starter_rows)
    bench_youth = _weighted_avg(bench_rows)
    if starter_youth is None and bench_youth is None:
        return None
    if starter_youth is None:
        return bench_youth
    if bench_youth is None:
        return starter_youth
    return round(0.65 * starter_youth + 0.35 * bench_youth, 3)


def _position_group_for_slot(slot: str) -> str:
    slot_upper = (slot or "").upper()
    if slot_upper in {"QB", "RB", "WR", "TE"}:
        return slot_upper
    if slot_upper in {"FLEX", "SUPER_FLEX", "SF"}:
        return "FLEX"
    return slot_upper


def _compute_contender_index(teams: list[dict[str, Any]]) -> dict[str, Any]:
    starter_ovrs = [float(t.get("starter_avg_dynasty_rating") or 0) or None for t in teams]
    starter_ppgs = [t.get("starter_total_ppg") for t in teams]
    age_depths = [_age_depth_score(t) for t in teams]

    ovr_norm = _normalize_league(starter_ovrs)
    ppg_norm = _normalize_league(starter_ppgs)
    age_norm = _normalize_league(age_depths)

    scored: list[dict[str, Any]] = []
    for idx, team in enumerate(teams):
        parts = [
            (CONTENDER_WEIGHTS["starter_ovr"], ovr_norm[idx]),
            (CONTENDER_WEIGHTS["starter_ppg"], ppg_norm[idx]),
            (CONTENDER_WEIGHTS["age_depth"], age_norm[idx]),
        ]
        if all(p[1] is None for p in parts):
            composite = None
        else:
            weight_sum = sum(w for w, v in parts if v is not None)
            composite = (
                round(sum(w * v for w, v in parts if v is not None) / weight_sum, 1)
                if weight_sum > 0
                else None
            )
        scored.append(
            {
                "roster_id": str(team["roster_id"]),
                "team_name": team.get("team_name"),
                "is_me": bool(team.get("is_me")),
                "composite_score": composite,
                "inputs": {
                    "starter_avg_ovr": team.get("starter_avg_dynasty_rating"),
                    "starter_total_ppg": team.get("starter_total_ppg"),
                    "age_depth_score": age_depths[idx],
                    "starter_ovr_norm": ovr_norm[idx],
                    "starter_ppg_norm": ppg_norm[idx],
                    "age_depth_norm": age_norm[idx],
                },
            }
        )

    ranked = sorted(
        scored,
        key=lambda row: (row["composite_score"] is not None, row["composite_score"] or -1),
        reverse=True,
    )
    n = len(ranked)
    contender_cut = max(1, math.ceil(n / 3))
    rebuild_cut = max(1, math.floor(n / 3))

    result_teams: list[dict[str, Any]] = []
    for rank, row in enumerate(ranked, start=1):
        if rank <= contender_cut:
            tier = "contender"
        elif rank > n - rebuild_cut:
            tier = "rebuild"
        else:
            tier = "competitive"
        result_teams.append({**row, "tier": tier, "contender_rank": rank})

    tier_by_roster = {row["roster_id"]: row["tier"] for row in result_teams}
    for team in teams:
        team["contender_tier"] = tier_by_roster.get(str(team["roster_id"]))

    return {"weights": CONTENDER_WEIGHTS, "teams": result_teams}


def _heatmap_positions(roster_positions: list[str]) -> list[str]:
    seen: set[str] = set()
    positions: list[str] = []
    for slot in roster_positions:
        if slot == "BN":
            break
        group = _position_group_for_slot(slot)
        if group not in seen:
            seen.add(group)
            positions.append(group)
    return positions


def _compute_position_strength(
    teams: list[dict[str, Any]],
    roster_positions: list[str],
) -> dict[str, Any]:
    positions = _heatmap_positions(roster_positions)
    result_teams: list[dict[str, Any]] = []

    for team in teams:
        by_group: dict[str, list[int]] = {pos: [] for pos in positions}
        for row in team.get("starters", []):
            player = row.get("player") or {}
            ovr = player.get("dynasty_rating")
            if ovr is None:
                continue
            group = _position_group_for_slot(row.get("slot") or row.get("pos") or "")
            if group in by_group:
                by_group[group].append(int(ovr))

        by_position = {
            pos: round(sum(vals) / len(vals)) if vals else None for pos, vals in by_group.items()
        }
        result_teams.append(
            {
                "roster_id": str(team["roster_id"]),
                "team_name": team.get("team_name"),
                "is_me": bool(team.get("is_me")),
                "by_position": by_position,
            }
        )

    return {"positions": positions, "teams": result_teams}


def _compute_age_profiles(
    teams: list[dict[str, Any]],
    league_avg_starter_age: float | None,
) -> list[dict[str, Any]]:
    profiles: list[dict[str, Any]] = []
    for team in teams:
        starter_ages: list[dict[str, Any]] = []
        starter_rows: list[tuple[float | None, float | None]] = []
        for row in team.get("starters", []):
            player = row.get("player") or {}
            age = player.get("age")
            ovr = player.get("dynasty_rating")
            if age is not None:
                starter_ages.append(
                    {
                        "player_id": player.get("player_id"),
                        "name": player.get("name"),
                        "pos": player.get("pos"),
                        "age": age,
                        "ovr": ovr,
                        "slot": row.get("slot"),
                    }
                )
                starter_rows.append((float(age), float(ovr) if ovr is not None else None))

        bench_rows: list[tuple[float | None, float | None]] = []
        for player in sorted(team.get("bench", []), key=lambda p: p.get("trade_value") or 0, reverse=True)[:5]:
            age = player.get("age")
            if age is not None:
                weight = player.get("trade_value") or player.get("dynasty_rating")
                bench_rows.append((float(age), float(weight) if weight is not None else None))

        starter_avg = _weighted_avg(starter_rows)
        bench_avg = _weighted_avg(bench_rows)
        age_delta = (
            round(starter_avg - league_avg_starter_age, 2)
            if starter_avg is not None and league_avg_starter_age is not None
            else None
        )
        window = None
        if age_delta is not None:
            if age_delta <= -1.0:
                window = "rising"
            elif age_delta >= 1.0:
                window = "closing"
            else:
                window = "peak"

        profiles.append(
            {
                "roster_id": str(team["roster_id"]),
                "team_name": team.get("team_name"),
                "is_me": bool(team.get("is_me")),
                "starter_avg_age": starter_avg,
                "bench_avg_age": bench_avg,
                "league_avg_starter_age": league_avg_starter_age,
                "age_delta": age_delta,
                "window": window,
                "starter_ages": starter_ages,
            }
        )
    return profiles


def _league_avg_starter_age(teams: list[dict[str, Any]]) -> float | None:
    rows: list[tuple[float | None, float | None]] = []
    for team in teams:
        for row in team.get("starters", []):
            player = row.get("player") or {}
            age = player.get("age")
            ovr = player.get("dynasty_rating")
            if age is not None:
                rows.append((float(age), float(ovr) if ovr is not None else None))
    return _weighted_avg(rows)


def _compute_trade_surplus(
    position_strength: dict[str, Any],
    *,
    top_n: int = TRADE_SURPLUS_TOP_N,
    bottom_n: int = TRADE_SURPLUS_BOTTOM_N,
) -> dict[str, Any] | None:
    teams = position_strength.get("teams", [])
    positions = position_strength.get("positions", [])
    my_team = next((t for t in teams if t.get("is_me")), None)
    if my_team is None:
        return None

    league_size = len(teams)
    surplus: list[dict[str, Any]] = []
    needs: list[dict[str, Any]] = []
    counterparties: list[dict[str, Any]] = []

    for pos in positions:
        ranked = sorted(
            [
                {
                    "roster_id": t["roster_id"],
                    "team_name": t.get("team_name"),
                    "is_me": t.get("is_me"),
                    "avg_ovr": (t.get("by_position") or {}).get(pos),
                }
                for t in teams
                if (t.get("by_position") or {}).get(pos) is not None
            ],
            key=lambda row: row["avg_ovr"] or 0,
            reverse=True,
        )
        if not ranked:
            continue

        rank_by_roster = {row["roster_id"]: idx + 1 for idx, row in enumerate(ranked)}
        my_rank = rank_by_roster.get(my_team["roster_id"])
        my_ovr = (my_team.get("by_position") or {}).get(pos)
        if my_rank is None:
            continue

        item = {
            "position": pos,
            "avg_ovr": my_ovr,
            "league_rank": my_rank,
            "league_size": len(ranked),
        }
        if my_rank <= top_n:
            surplus.append(item)
            for other in ranked[-bottom_n:]:
                if other["roster_id"] == my_team["roster_id"]:
                    continue
                counterparties.append(
                    {
                        "position": pos,
                        "direction": "sell",
                        "roster_id": other["roster_id"],
                        "team_name": other.get("team_name"),
                        "my_rank": my_rank,
                        "their_rank": rank_by_roster[other["roster_id"]],
                        "their_avg_ovr": other.get("avg_ovr"),
                    }
                )
        if my_rank > len(ranked) - bottom_n:
            needs.append(item)
            for other in ranked[:top_n]:
                if other["roster_id"] == my_team["roster_id"]:
                    continue
                counterparties.append(
                    {
                        "position": pos,
                        "direction": "buy",
                        "roster_id": other["roster_id"],
                        "team_name": other.get("team_name"),
                        "my_rank": my_rank,
                        "their_rank": rank_by_roster[other["roster_id"]],
                        "their_avg_ovr": other.get("avg_ovr"),
                    }
                )

    return {
        "roster_id": my_team["roster_id"],
        "team_name": my_team.get("team_name"),
        "surplus": surplus,
        "needs": needs,
        "counterparties": counterparties,
    }


def _compact_team_row(team_meta: dict[str, Any], lineup: dict[str, Any]) -> dict[str, Any]:
    return {
        "roster_id": team_meta["sleeper_roster_id"],
        "team_name": team_meta["team_name"],
        "owner": team_meta.get("owner_name"),
        "is_me": team_meta.get("is_me", False),
        "avg_dynasty_rating": lineup.get("avg_dynasty_rating"),
        "starter_avg_dynasty_rating": lineup.get("starter_avg_dynasty_rating"),
        "total_trade_value": lineup.get("total_trade_value"),
        "win_now_score": lineup.get("win_now_score"),
        "starter_total_ppg": lineup.get("starter_total_ppg"),
        "starter_ppg_slots": lineup.get("starter_ppg_slots"),
    }


def compute_league_rankings(db: Session, league_id: str, *, war_csv: str = "war.csv") -> dict[str, Any]:
    """Build 4 power rankings → league_snapshots.rankings_json."""
    from backend.db.models import League

    league_row = db.get(League, league_id)
    if league_row is None:
        raise ValueError(f"League not found: {league_id}")

    context = build_league_scoring_context(league_row)
    roster_positions = context.roster_positions
    war = WarData(Path(war_csv))

    snapshots = {
        row.sleeper_player_id: row
        for row in db.scalars(
            select(PlayerSnapshot).where(PlayerSnapshot.league_id == league_id)
        ).all()
    }

    rosters = db.scalars(select(Roster).where(Roster.league_id == league_id)).all()
    teams: list[dict[str, Any]] = []

    for roster in rosters:
        players = db.scalars(
            select(RosterPlayer).where(RosterPlayer.roster_id == roster.id)
        ).all()
        player_rows = []
        for rp in players:
            snap = snapshots.get(rp.sleeper_player_id)
            if snap is None:
                continue
            player_rows.append(_player_row_from_snapshot(snap, war))

        lineup = _finalize_team_lineup(player_rows, roster_positions)
        team_meta = {
            "sleeper_roster_id": roster.sleeper_roster_id,
            "team_name": roster.team_name or f"Team {roster.sleeper_roster_id}",
            "owner_name": roster.owner_name,
            "is_me": roster.is_me,
        }
        teams.append({**_compact_team_row(team_meta, lineup), **lineup})

    def _rank(teams_list: list[dict[str, Any]], key: str, rank_field: str) -> list[dict[str, Any]]:
        ranked = sorted(teams_list, key=lambda row: float(row.get(key) or -1), reverse=True)
        result = []
        for idx, row in enumerate(ranked, start=1):
            compact = {k: v for k, v in row.items() if k not in {"starters", "bench"}}
            compact[rank_field] = idx
            result.append(compact)
        return result

    contender_index = _compute_contender_index(teams)
    position_strength = _compute_position_strength(teams, roster_positions)
    league_avg_age = _league_avg_starter_age(teams)
    age_profiles = _compute_age_profiles(teams, league_avg_age)
    trade_surplus = _compute_trade_surplus(position_strength)

    contender_by_roster = {
        row["roster_id"]: row for row in contender_index.get("teams", [])
    }

    def _with_contender(compact: dict[str, Any]) -> dict[str, Any]:
        info = contender_by_roster.get(str(compact.get("roster_id")), {})
        compact["contender_tier"] = info.get("tier")
        compact["contender_rank"] = info.get("contender_rank")
        compact["contender_score"] = info.get("composite_score")
        return compact

    by_dynasty = [_with_contender(row) for row in _rank(teams, "avg_dynasty_rating", "dynasty_rank")]
    by_starter_ppg = [_with_contender(row) for row in _rank(teams, "starter_total_ppg", "starter_ppg_rank")]
    by_tv = [_with_contender(row) for row in _rank(teams, "total_trade_value", "tv_rank")]
    by_win_now = [_with_contender(row) for row in _rank(teams, "win_now_score", "win_rank")]

    rankings = {
        "by_dynasty": by_dynasty,
        "by_starter_ppg": by_starter_ppg,
        "by_tv": by_tv,
        "by_win_now": by_win_now,
    }

    teams_lineup: dict[str, Any] = {}
    for team in teams:
        roster_id = str(team["roster_id"])
        teams_lineup[roster_id] = {
            "starters": [
                {
                    "slot": row.get("pos") or "BN",
                    "player_id": (row.get("player") or {}).get("player_id"),
                }
                for row in team.get("starters", [])
            ],
            "bench": [
                (row.get("player_id") if isinstance(row, dict) else None)
                or (row.get("player") or {}).get("player_id")
                for row in team.get("bench", [])
            ],
        }

    computed_at = datetime.now(timezone.utc)
    db.add(
        LeagueSnapshot(
            league_id=league_id,
            rankings_json=rankings,
            analysis_json={
                "teams": teams_lineup,
                "contender_index": contender_index,
                "position_strength": position_strength,
                "age_profiles": age_profiles,
                "trade_surplus": trade_surplus,
            },
            context_hash=context.context_hash,
            computed_at=computed_at,
        )
    )

    history_row = db.scalar(
        select(LeagueSnapshotHistory)
        .where(LeagueSnapshotHistory.league_id == league_id)
        .order_by(desc(LeagueSnapshotHistory.computed_at))
        .limit(1)
    )
    if history_row is not None:
        team_ovr = {
            str(team["roster_id"]): team.get("avg_dynasty_rating")
            for team in by_dynasty
        }
        attach_team_ovr_to_history(db, league_id, history_row.id, team_ovr)

    db.commit()

    return {
        "league_id": league_id,
        "context_hash": context.context_hash,
        "team_count": len(teams),
        "computed_at": computed_at.isoformat(),
    }
