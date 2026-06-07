"""Roster pool → engine → player_snapshots + history ledger (§5.7, §10, §15)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from backend.api.settings import _read_settings
from backend.config import get_settings
from backend.db.models import League, LeagueSnapshotHistory, PlayerSnapshot, PlayerSnapshotHistory, Roster, RosterPlayer
from backend.services.formula_version import compute_formula_version
from backend.services.league_engine import build_league_scoring_state
from backend.services.sync_service import _resolve_my_user_id
from dynasty_draft.sleeper_client import SleeperClient

_FLEX_POSITIONS = frozenset({"RB", "WR", "TE"})


def _collect_rostered_player_ids(db: Session, league_id: str) -> set[str]:
    rows = db.execute(
        select(RosterPlayer.sleeper_player_id)
        .join(Roster, Roster.id == RosterPlayer.roster_id)
        .where(Roster.league_id == league_id)
    ).all()
    return {str(row[0]) for row in rows}


def _anchors_blob(state) -> dict[str, Any]:
    """Serialize league anchor board for history / re-curve (§15.1)."""
    ref_anchors, rating_bounds = state._dynasty_curve_context()
    per_game = state._dynasty_per_game_reference()
    return {
        "max_tv": ref_anchors.max_tv,
        "max_worp": ref_anchors.max_worp,
        "per_game_maxes": {
            "qb": list(per_game.qb),
            "flex": list(per_game.flex),
        },
        "rating_bounds": list(rating_bounds),
    }


def compute_player_snapshots(
    db: Session,
    league_id: str,
    *,
    client: SleeperClient | None = None,
    sync_run_id: int | None = None,
) -> dict[str, Any]:
    """Score the league roster pool, upsert player_snapshots, append history rows."""
    client = client or SleeperClient()
    league_row = db.get(League, league_id)
    if league_row is None:
        raise ValueError(f"League not found: {league_id}")

    settings = _read_settings(db)
    formula_version = compute_formula_version(settings)
    my_user_id = _resolve_my_user_id(client, settings)
    roster_player_ids = _collect_rostered_player_ids(db, league_id)
    if not roster_player_ids:
        raise ValueError(f"No rostered players for league {league_id}")

    fa_pool_size = get_settings().fa_pool_size

    state = build_league_scoring_state(
        league_row=league_row,
        roster_player_ids=roster_player_ids,
        user_id=my_user_id,
        settings=settings,
        client=client,
    )
    context = state.scoring_context
    roster_pool = state.scoring_pool()
    fa_pool = state.fa_scoring_pool(fa_pool_size)
    pool = state.snapshot_pool(fa_pool_size)
    anchors = _anchors_blob(state)

    dynasty_by_id = state.dynasty_scores(pool)
    roster_flex = state.flex_pool()
    roster_flex_ids = {player_id for player_id, _ in roster_flex}
    fa_flex = [
        (player_id, war_player)
        for player_id, war_player in fa_pool
        if war_player.pos in _FLEX_POSITIONS and player_id not in roster_flex_ids
    ]
    flex_by_id = state.flex_relative_ratings(roster_flex + fa_flex)

    computed_at = datetime.now(timezone.utc)

    league_history = LeagueSnapshotHistory(
        league_id=league_id,
        sync_run_id=sync_run_id,
        context_hash=context.context_hash,
        formula_version=formula_version,
        anchors_json=anchors,
        team_ovr_json={},
        computed_at=computed_at,
    )
    db.add(league_history)
    db.flush()

    db.execute(delete(PlayerSnapshot).where(PlayerSnapshot.league_id == league_id))

    roster_ids_in_pool = {player_id for player_id, _ in roster_pool}
    upserted = 0
    fa_scored = 0
    for player_id, war_player in pool:
        scored = dynasty_by_id.get(player_id) or {}
        flex = flex_by_id.get(player_id) or {}
        healthy = state._healthy_ppg_metrics(player_id, war_player) or {}
        blended = state.with_blended_tv(war_player)
        sleeper = state.sleeper_players.get(player_id) or {}
        age = state._player_age(player_id)

        snapshot_fields = dict(
            league_id=league_id,
            sleeper_player_id=player_id,
            player_name=war_player.name,
            position=war_player.pos,
            nfl_team=(war_player.team or sleeper.get("team") or "").upper() or None,
            age=age,
            dynasty_rating=scored.get("dynasty_rating"),
            dynasty_score=scored.get("dynasty_score"),
            dynasty_rookie=bool(scored.get("dynasty_rookie")),
            components_json=scored.get("dynasty_components") or {},
            hppg=healthy.get("healthy_ppg"),
            worp_ppg=healthy.get("worp_ppg"),
            availability=healthy.get("availability"),
            hppg_expected=bool(healthy.get("hppg_expected")),
            trade_value=round(blended.trade_value, 2),
            flex_rating=flex.get("flex_rating"),
            win_now_rating=None,
            context_hash=context.context_hash,
            computed_at=computed_at,
        )

        db.add(PlayerSnapshot(**snapshot_fields))
        db.add(
            PlayerSnapshotHistory(
                league_id=league_id,
                sleeper_player_id=player_id,
                league_snapshot_history_id=league_history.id,
                player_name=snapshot_fields["player_name"],
                position=snapshot_fields["position"],
                nfl_team=snapshot_fields["nfl_team"],
                age=snapshot_fields["age"],
                dynasty_rating=snapshot_fields["dynasty_rating"],
                dynasty_score=snapshot_fields["dynasty_score"],
                dynasty_rookie=snapshot_fields["dynasty_rookie"],
                components_json=snapshot_fields["components_json"],
                hppg=snapshot_fields["hppg"],
                worp_ppg=snapshot_fields["worp_ppg"],
                availability=snapshot_fields["availability"],
                hppg_expected=snapshot_fields["hppg_expected"],
                trade_value=snapshot_fields["trade_value"],
                flex_rating=snapshot_fields["flex_rating"],
                season_worp=war_player.worp,
                context_hash=snapshot_fields["context_hash"],
                formula_version=formula_version,
                computed_at=computed_at,
            )
        )
        upserted += 1
        if player_id not in roster_ids_in_pool:
            fa_scored += 1

    db.commit()
    return {
        "league_id": league_id,
        "context_hash": context.context_hash,
        "formula_version": formula_version,
        "players_scored": upserted,
        "rostered_scored": len(roster_ids_in_pool),
        "fa_scored": fa_scored,
        "fa_pool_size": fa_pool_size,
        "computed_at": computed_at.isoformat(),
        "league_snapshot_history_id": league_history.id,
    }
