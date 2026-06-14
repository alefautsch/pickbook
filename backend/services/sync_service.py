"""Sleeper → Postgres sync (§10)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from backend.api.settings import _read_settings
from backend.config import get_settings
from backend.db.models import League, Roster, RosterPlayer, SyncRun
from backend.services.pick_service import sync_league_draft_picks
from dynasty_draft.sleeper_client import SleeperClient


def _superflex_from_roster(roster_positions: list[str]) -> bool:
    return any(pos.upper() in {"SUPER_FLEX", "SUPERFLEX", "QB_WR_RB_TE"} for pos in roster_positions)


def _team_display_name(user: dict[str, Any] | None, roster_id: int | str) -> str:
    if not user:
        return f"Team {roster_id}"
    meta = user.get("metadata") or {}
    return meta.get("team_name") or user.get("display_name") or f"Team {roster_id}"


def _draft_picks_by_roster(
    client: SleeperClient,
    league: dict[str, Any],
) -> dict[str, list[str]]:
    """When Sleeper rosters are empty (startup draft), use completed draft picks."""
    draft_id = league.get("draft_id")
    if not draft_id:
        return {}
    picks = client.get_draft_picks(str(draft_id))
    by_roster: dict[str, list[str]] = {}
    for pick in picks:
        player_id = pick.get("player_id")
        roster_id = pick.get("roster_id")
        if not player_id or roster_id is None:
            continue
        key = str(roster_id)
        by_roster.setdefault(key, []).append(str(player_id))
    return by_roster


def _resolve_my_user_id(client: SleeperClient, settings: dict[str, Any]) -> str:
    username = (settings.get("sleeper_username") or get_settings().sleeper_username or "").strip()
    if not username:
        raise RuntimeError("sleeper_username not configured")
    user = client.get_user(username)
    return str(user["user_id"])


def sync_league_from_sleeper(
    db: Session,
    league_id: str,
    *,
    client: SleeperClient | None = None,
) -> dict[str, Any]:
    """Pull league settings, users, rosters from Sleeper; upsert DB rows."""
    client = client or SleeperClient()
    settings = _read_settings(db)
    my_user_id = _resolve_my_user_id(client, settings)

    sync_run = SyncRun(league_id=league_id, status="running")
    db.add(sync_run)
    db.flush()

    counts: dict[str, int] = {}
    errors: list[str] = []
    started = datetime.now(timezone.utc)

    try:
        remote = client.get_league(league_id)
        users = client.get_league_users(league_id)
        rosters = client.get_rosters(league_id)

        users_by_id = {str(u.get("user_id")): u for u in users}
        roster_positions = remote.get("roster_positions") or []
        scoring = remote.get("scoring_settings") or {}
        total_rosters = int(remote.get("total_rosters") or 0)

        row = db.get(League, league_id)
        if row is None:
            row = League(sleeper_league_id=league_id)
            db.add(row)

        row.name = str(remote.get("name") or league_id)
        row.season = str(remote.get("season") or settings.get("season") or "2026")
        row.total_rosters = total_rosters
        row.superflex = _superflex_from_roster(roster_positions)
        row.scoring_json = scoring
        row.roster_positions_json = roster_positions

        existing_rosters = {
            r.sleeper_roster_id: r
            for r in db.scalars(select(Roster).where(Roster.league_id == league_id)).all()
        }
        seen_roster_ids: set[str] = set()
        roster_count = 0
        player_count = 0

        sleeper_players = client.get_players()
        draft_players_by_roster = _draft_picks_by_roster(client, remote)

        for sleeper_roster in rosters:
            sleeper_roster_id = str(sleeper_roster.get("roster_id"))
            seen_roster_ids.add(sleeper_roster_id)
            owner_id = str(sleeper_roster.get("owner_id") or "")
            user = users_by_id.get(owner_id)

            roster_row = existing_rosters.get(sleeper_roster_id)
            if roster_row is None:
                roster_row = Roster(
                    league_id=league_id,
                    sleeper_roster_id=sleeper_roster_id,
                )
                db.add(roster_row)
                db.flush()

            roster_row.owner_user_id = owner_id or None
            roster_row.owner_name = (user or {}).get("display_name")
            roster_row.owner_avatar = (user or {}).get("avatar")
            roster_row.team_name = _team_display_name(user, sleeper_roster_id)
            roster_row.is_me = owner_id == my_user_id
            roster_count += 1

            db.execute(delete(RosterPlayer).where(RosterPlayer.roster_id == roster_row.id))

            roster_player_ids = sleeper_roster.get("players") or []
            if not roster_player_ids and draft_players_by_roster:
                roster_player_ids = draft_players_by_roster.get(sleeper_roster_id, [])

            for player_id in roster_player_ids:
                pid = str(player_id)
                sleeper = sleeper_players.get(pid) or {}
                db.add(
                    RosterPlayer(
                        roster_id=roster_row.id,
                        sleeper_player_id=pid,
                        player_name=sleeper.get("full_name"),
                        position=(sleeper.get("position") or "").upper() or None,
                        nfl_team=(sleeper.get("team") or "").upper() or None,
                    )
                )
                player_count += 1

        stale_ids = set(existing_rosters.keys()) - seen_roster_ids
        for stale_id in stale_ids:
            db.delete(existing_rosters[stale_id])

        pick_count = sync_league_draft_picks(
            db,
            league_id,
            client=client,
            league_remote=remote,
            rosters_remote=rosters,
        )

        counts = {
            "rosters": roster_count,
            "roster_players": player_count,
            "users": len(users),
            "draft_picks": pick_count,
        }

        sync_run.status = "success"
        sync_run.counts_json = counts
        sync_run.finished_at = datetime.now(timezone.utc)
        db.commit()

        duration_ms = int((sync_run.finished_at - started).total_seconds() * 1000)
        return {
            "league_id": league_id,
            "league_name": row.name,
            "status": "success",
            "counts": counts,
            "duration_ms": duration_ms,
            "sync_run_id": sync_run.id,
            "errors": errors,
        }

    except Exception as exc:
        db.rollback()
        failed_run = SyncRun(league_id=league_id, status="failed")
        db.add(failed_run)
        failed_run.errors_json = [str(exc)]
        failed_run.finished_at = datetime.now(timezone.utc)
        failed_run.counts_json = counts
        db.commit()
        raise


def sync_all_leagues(db: Session, *, client: SleeperClient | None = None) -> list[dict[str, Any]]:
    """Sync every league row in the DB."""
    client = client or SleeperClient()
    league_ids = list(db.scalars(select(League.sleeper_league_id).order_by(League.name)).all())
    results: list[dict[str, Any]] = []
    for league_id in league_ids:
        try:
            results.append(sync_league_from_sleeper(db, league_id, client=client))
        except Exception as exc:
            results.append(
                {
                    "league_id": league_id,
                    "status": "failed",
                    "errors": [str(exc)],
                }
            )
    return results
