"""Snapshot history reads and formula re-grade (§15)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import desc, select, update
from sqlalchemy.orm import Session, joinedload

from backend.api.settings import _read_settings
from backend.db.models import LeagueSnapshotHistory, PlayerSnapshotHistory
from backend.schemas.player import DynastyComponents, PlayerHistoryPoint, PlayerHistorySeries
from backend.services.formula_version import compute_formula_version
from dynasty_draft.dynasty_score import DynastyRatingCurve, DynastyWeights, curved_composite_to_rating


def _display_ovr(row: PlayerSnapshotHistory, current_formula: str) -> int | None:
    if row.dynasty_rating_recomputed is not None and row.recomputed_formula_version == current_formula:
        return row.dynasty_rating_recomputed
    return row.dynasty_rating


def _history_point(row: PlayerSnapshotHistory, current_formula: str) -> PlayerHistoryPoint:
    components_raw = row.components_json or {}
    return PlayerHistoryPoint(
        computed_at=row.computed_at,
        snapshot_date=row.snapshot_date,
        ovr=_display_ovr(row, current_formula),
        ovr_original=row.dynasty_rating,
        ovr_recomputed=row.dynasty_rating_recomputed,
        formula_version=row.formula_version,
        recomputed_formula_version=row.recomputed_formula_version,
        dynasty_score=row.dynasty_score,
        hppg=row.hppg,
        worp_ppg=row.worp_ppg,
        availability=row.availability,
        trade_value=row.trade_value,
        components=DynastyComponents(
            tv=components_raw.get("tv"),
            worp=components_raw.get("worp"),
            per_game=components_raw.get("per_game"),
            upside=components_raw.get("upside"),
            age=components_raw.get("age"),
            trajectory=components_raw.get("trajectory"),
        ),
    )


def get_player_history(
    db: Session,
    player_id: str,
    league_id: str,
    *,
    limit: int = 90,
) -> PlayerHistorySeries | None:
    settings = _read_settings(db)
    current_formula = compute_formula_version(settings)

    rows = db.scalars(
        select(PlayerSnapshotHistory)
        .where(
            PlayerSnapshotHistory.league_id == league_id,
            PlayerSnapshotHistory.sleeper_player_id == player_id,
        )
        .order_by(PlayerSnapshotHistory.snapshot_date.asc())
        .limit(limit)
    ).all()

    if not rows:
        return None

    return PlayerHistorySeries(
        player_id=player_id,
        league_id=league_id,
        current_formula_version=current_formula,
        points=[_history_point(row, current_formula) for row in rows],
    )


def _composite_from_components(components: dict[str, Any], weights: DynastyWeights) -> float:
    def _val(key: str) -> float:
        raw = components.get(key)
        return float(raw) if raw is not None else 0.0

    return (
        weights.tv * _val("tv")
        + weights.worp * _val("worp")
        + weights.upside * _val("upside")
        + weights.age * _val("age")
        + weights.trajectory * _val("trajectory")
    )


def recompute_history(
    db: Session,
    *,
    league_id: str | None = None,
) -> dict[str, Any]:
    """Re-apply current weights/curve to stored components + anchors (§15.1)."""
    settings = _read_settings(db)
    formula_version = compute_formula_version(settings)
    weights = DynastyWeights.from_config(settings.get("dynasty_weights"))
    curve = DynastyRatingCurve.from_config(settings.get("dynasty_rating_curve"))

    stmt = (
        select(PlayerSnapshotHistory)
        .options(joinedload(PlayerSnapshotHistory.league_snapshot))
        .order_by(PlayerSnapshotHistory.id)
    )
    if league_id:
        stmt = stmt.where(PlayerSnapshotHistory.league_id == league_id)

    rows = db.scalars(stmt).all()
    updated = 0

    for row in rows:
        league_snap = row.league_snapshot
        if league_snap is None:
            continue
        bounds = (league_snap.anchors_json or {}).get("rating_bounds")
        if not bounds or len(bounds) != 2:
            continue

        composite = _composite_from_components(row.components_json or {}, weights)
        new_rating = curved_composite_to_rating(
            composite,
            raw_min=float(bounds[0]),
            raw_max=float(bounds[1]),
            exponent=curve.exponent,
        )
        row.dynasty_rating_recomputed = new_rating
        row.recomputed_formula_version = formula_version
        updated += 1

    db.commit()
    return {
        "updated": updated,
        "formula_version": formula_version,
        "league_id": league_id,
    }


def attach_team_ovr_to_history(
    db: Session,
    league_id: str,
    history_id: int,
    team_ovr: dict[str, int | float | None],
) -> None:
    db.execute(
        update(LeagueSnapshotHistory)
        .where(
            LeagueSnapshotHistory.id == history_id,
            LeagueSnapshotHistory.league_id == league_id,
        )
        .values(team_ovr_json=team_ovr)
    )


def team_ovr_delta(
    db: Session,
    league_id: str,
    roster_id: str,
    current_ovr: int | float | None,
) -> int | None:
    """Δ OVR vs prior sync for hub tiles (§15.2)."""
    if current_ovr is None:
        return None

    rows = db.scalars(
        select(LeagueSnapshotHistory)
        .where(LeagueSnapshotHistory.league_id == league_id)
        .order_by(desc(LeagueSnapshotHistory.snapshot_date))
        .limit(2)
    ).all()
    if len(rows) < 2:
        return None

    current_formula = compute_formula_version(_read_settings(db))
    if rows[0].formula_version != current_formula or rows[1].formula_version != current_formula:
        return None

    prev = (rows[1].team_ovr_json or {}).get(str(roster_id))
    if prev is None:
        return None

    return int(round(float(current_ovr) - float(prev)))
