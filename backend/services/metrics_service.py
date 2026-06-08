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
from backend.services.opportunity_service import (
    OpportunityStore,
    compute_projection,
    position_percentiles,
    win_now_relative_ratings,
)
from backend.services.sync_service import _resolve_my_user_id
from dynasty_draft.sleeper_client import SleeperClient

_FLEX_POSITIONS = frozenset({"RB", "WR", "TE"})


def _bio_from_sleeper(sleeper: dict[str, Any]) -> dict[str, Any]:
    years_exp = sleeper.get("years_exp")
    return {
        "height": str(sleeper["height"]) if sleeper.get("height") is not None else None,
        "weight": str(sleeper["weight"]) if sleeper.get("weight") is not None else None,
        "college": sleeper.get("college"),
        "years_exp": int(years_exp) if years_exp is not None else None,
        "injury_status": sleeper.get("injury_status"),
        "injury_body_part": sleeper.get("injury_body_part"),
    }


def _resolve_worp_ppg_for_snapshot(
    state,
    player_id: str,
    war_player,
    healthy: dict[str, Any],
) -> float | None:
    """Persisted W/G for UI — nflverse VOR can be 0 below SF replacement; fall back to season WORP."""
    worp_ppg = healthy.get("worp_ppg")
    if worp_ppg is not None and worp_ppg > 0:
        return float(worp_ppg)
    if war_player.worp is not None and war_player.worp > 0:
        return round(float(war_player.worp) / 17.0, 4)
    blended = state.with_blended_tv(war_player)
    eff, _ = state._effective_worp(player_id, blended)
    if eff is not None and eff > 0:
        return round(float(eff) / 17.0, 4)
    return float(worp_ppg) if worp_ppg is not None else None


def _assign_snapshot_ranks(rows: list[dict[str, Any]]) -> None:
    """Overall and positional dynasty ranks within the league snapshot pool."""
    rated = [row for row in rows if row.get("dynasty_rating") is not None]
    rated.sort(key=lambda row: row["dynasty_rating"], reverse=True)
    for rank, row in enumerate(rated, start=1):
        row["overall_rank"] = rank

    by_pos: dict[str, list[dict[str, Any]]] = {}
    for row in rated:
        pos = row.get("position") or "UNK"
        by_pos.setdefault(pos, []).append(row)
    for pos_rows in by_pos.values():
        pos_rows.sort(key=lambda row: row["dynasty_rating"], reverse=True)
        for rank, row in enumerate(pos_rows, start=1):
            row["position_rank"] = rank


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
    force_refresh: bool = False,
) -> dict[str, Any]:
    """Score the league roster pool, upsert player_snapshots, append history rows."""
    client = client or SleeperClient()
    league_row = db.get(League, league_id)
    if league_row is None:
        raise ValueError(f"League not found: {league_id}")

    settings = dict(_read_settings(db))
    if force_refresh:
        settings["_force_metric_refresh"] = True
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

    try:
        opportunity_store = OpportunityStore.load(
            sleeper_players=state.sleeper_players,
            ppr=context.ppr,
            force_refresh=force_refresh,
        )
    except Exception:
        opportunity_store = None

    projections = getattr(state, "projection_store", None)
    computed_at = datetime.now(timezone.utc)
    snapshot_date = computed_at.date()

    league_history = db.scalar(
        select(LeagueSnapshotHistory).where(
            LeagueSnapshotHistory.league_id == league_id,
            LeagueSnapshotHistory.snapshot_date == snapshot_date,
        )
    )
    if league_history is None:
        league_history = LeagueSnapshotHistory(
            league_id=league_id,
            snapshot_date=snapshot_date,
        )
        db.add(league_history)

    league_history.sync_run_id = sync_run_id
    league_history.context_hash = context.context_hash
    league_history.formula_version = formula_version
    league_history.anchors_json = anchors
    league_history.team_ovr_json = {}
    league_history.computed_at = computed_at
    db.flush()

    db.execute(delete(PlayerSnapshot).where(PlayerSnapshot.league_id == league_id))
    db.execute(
        delete(PlayerSnapshotHistory).where(
            PlayerSnapshotHistory.league_id == league_id,
            PlayerSnapshotHistory.snapshot_date == snapshot_date,
        )
    )

    roster_ids_in_pool = {player_id for player_id, _ in roster_pool}
    upserted = 0
    fa_scored = 0

    base_rows: list[dict[str, Any]] = []
    for player_id, war_player in pool:
        scored = dynasty_by_id.get(player_id) or {}
        flex = flex_by_id.get(player_id) or {}
        healthy = state._healthy_ppg_metrics(player_id, war_player) or {}
        blended = state.with_blended_tv(war_player)
        sleeper = state.sleeper_players.get(player_id) or {}
        age = state._player_age(player_id)
        bio = _bio_from_sleeper(sleeper)
        worp_ppg = _resolve_worp_ppg_for_snapshot(state, player_id, war_player, healthy)

        base_rows.append(
            {
                "player_id": player_id,
                "player_name": war_player.name,
                "position": war_player.pos,
                "nfl_team": (war_player.team or sleeper.get("team") or "").upper() or None,
                "age": age,
                "dynasty_rating": scored.get("dynasty_rating"),
                "dynasty_score": scored.get("dynasty_score"),
                "dynasty_rookie": bool(scored.get("dynasty_rookie")),
                "components_json": scored.get("dynasty_components") or {},
                "value_inputs_json": state.value_inputs(war_player, blended),
                "hppg": healthy.get("healthy_ppg"),
                "worp_ppg": worp_ppg,
                "availability": healthy.get("availability"),
                "healthy_games": healthy.get("healthy_games"),
                "total_games": healthy.get("total_games"),
                "hppg_expected": bool(healthy.get("hppg_expected")),
                "trade_value": round(blended.trade_value, 2),
                "flex_rating": flex.get("flex_rating"),
                "season_worp": war_player.worp,
                "porp": war_player.porp,
                **bio,
            }
        )

    _assign_snapshot_ranks(base_rows)

    percentile_by_id = position_percentiles(base_rows)

    projection_by_id: dict[str, Any] = {}
    for row in base_rows:
        player_id = row["player_id"]
        projection_by_id[player_id] = compute_projection(
            player_id=player_id,
            player_name=row["player_name"],
            position=row["position"],
            age=row["age"],
            trade_value=row["trade_value"],
            hppg=row["hppg"],
            worp_ppg=row["worp_ppg"],
            dynasty_rookie=row["dynasty_rookie"],
            opportunity_store=opportunity_store,
            projections=projections,
            years_exp=row.get("years_exp"),
            hppg_expected=row["hppg_expected"],
            percentile_row=percentile_by_id.get(player_id),
        )

    win_now_pool = [
        (
            row["player_id"],
            {
                **row,
                "projected_ppg": projection_by_id[row["player_id"]].projected_ppg,
            },
        )
        for row in base_rows
    ]
    win_now_by_id = win_now_relative_ratings(
        win_now_pool,
        curve=state.dynasty_rating_curve,
    )

    war_by_id = {player_id: war_player for player_id, war_player in pool}

    for row in base_rows:
        player_id = row["player_id"]
        proj = projection_by_id[player_id]

        snapshot_fields = dict(
            league_id=league_id,
            sleeper_player_id=player_id,
            player_name=row["player_name"],
            position=row["position"],
            nfl_team=row["nfl_team"],
            age=row["age"],
            dynasty_rating=row["dynasty_rating"],
            dynasty_score=row["dynasty_score"],
            dynasty_rookie=row["dynasty_rookie"],
            components_json=row["components_json"],
            value_inputs_json=row["value_inputs_json"],
            hppg=row["hppg"],
            worp_ppg=row["worp_ppg"],
            availability=row["availability"],
            hppg_expected=row["hppg_expected"],
            trade_value=row["trade_value"],
            flex_rating=row["flex_rating"],
            win_now_rating=win_now_by_id.get(player_id),
            opportunity_score=proj.opportunity_score,
            projected_ppg=proj.projected_ppg,
            projection_source=proj.projection_source,
            outlook_json=proj.outlook,
            season_worp=row["season_worp"],
            porp=row["porp"],
            healthy_games=row.get("healthy_games"),
            total_games=row.get("total_games"),
            injury_status=row.get("injury_status"),
            injury_body_part=row.get("injury_body_part"),
            height=row.get("height"),
            weight=row.get("weight"),
            college=row.get("college"),
            years_exp=row.get("years_exp"),
            position_rank=row.get("position_rank"),
            overall_rank=row.get("overall_rank"),
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
                value_inputs_json=snapshot_fields["value_inputs_json"],
                hppg=snapshot_fields["hppg"],
                worp_ppg=snapshot_fields["worp_ppg"],
                availability=snapshot_fields["availability"],
                hppg_expected=snapshot_fields["hppg_expected"],
                trade_value=snapshot_fields["trade_value"],
                flex_rating=snapshot_fields["flex_rating"],
                win_now_rating=snapshot_fields["win_now_rating"],
                opportunity_score=snapshot_fields["opportunity_score"],
                projected_ppg=snapshot_fields["projected_ppg"],
                projection_source=snapshot_fields["projection_source"],
                outlook_json=snapshot_fields["outlook_json"],
                season_worp=snapshot_fields["season_worp"],
                porp=snapshot_fields["porp"],
                healthy_games=snapshot_fields["healthy_games"],
                total_games=snapshot_fields["total_games"],
                injury_status=snapshot_fields["injury_status"],
                injury_body_part=snapshot_fields["injury_body_part"],
                height=snapshot_fields["height"],
                weight=snapshot_fields["weight"],
                college=snapshot_fields["college"],
                years_exp=snapshot_fields["years_exp"],
                position_rank=snapshot_fields["position_rank"],
                overall_rank=snapshot_fields["overall_rank"],
                context_hash=snapshot_fields["context_hash"],
                formula_version=formula_version,
                snapshot_date=snapshot_date,
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
