"""League power rankings from snapshots (§8.1)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from backend.db.models import LeagueSnapshot, LeagueSnapshotHistory, PlayerSnapshot, Roster, RosterPlayer
from backend.services.history_service import attach_team_ovr_to_history
from backend.services.league_context import build_league_scoring_context
from dynasty_draft.draft_context import _assign_lineup, _starter_metric
from dynasty_draft.war_data import WarData
from pathlib import Path


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

    by_dynasty = _rank(teams, "avg_dynasty_rating", "dynasty_rank")
    by_starter_ppg = _rank(teams, "starter_total_ppg", "starter_ppg_rank")
    by_tv = _rank(teams, "total_trade_value", "tv_rank")
    by_win_now = _rank(teams, "win_now_score", "win_rank")

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
            analysis_json={"teams": teams_lineup},
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
