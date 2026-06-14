from __future__ import annotations

from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models import League, PlayerSnapshot
from backend.schemas.player import PlayerGameLog, PlayerGameLogEntry
from backend.services.league_context import build_league_scoring_context
from dynasty_draft.healthy_ppg import (
    DEFAULT_SEASONS,
    _download_csv,
    _half_ppr_points,
    _with_health_flags,
)
from dynasty_draft.sleeper_client import CACHE_DIR
from dynasty_draft.war_data import POSITIONS, normalize_name

_NFLVERSE = "https://github.com/nflverse/nflverse-data/releases/download"
_GAME_LOG_TTL_SECONDS = 7 * 24 * 60 * 60


def _num(row: pd.Series, field: str) -> int:
    value = row.get(field)
    if pd.isna(value):
        return 0
    return int(value)


def _float_or_none(row: pd.Series, field: str) -> float | None:
    value = row.get(field)
    if pd.isna(value):
        return None
    return float(value)


def _game_log_cache_path(seasons: tuple[int, ...], ppr: float, te_premium: float) -> Any:
    ppr_key = str(ppr).replace(".", "_")
    te_key = str(te_premium).replace(".", "_")
    return CACHE_DIR / f"player_game_log_v4_{'-'.join(str(s) for s in seasons)}_{ppr_key}_te{te_key}.json"


def _load_game_log_rows(
    *,
    seasons: tuple[int, ...],
    ppr: float,
    te_premium: float = 0.0,
    force_refresh: bool = False,
) -> list[dict[str, Any]]:
    cache_path = _game_log_cache_path(seasons, ppr, te_premium)
    if not force_refresh and cache_path.exists():
        try:
            import json
            import time

            payload = json.loads(cache_path.read_text(encoding="utf-8"))
            if time.time() - float(payload.get("fetched_at", 0)) < _GAME_LOG_TTL_SECONDS:
                return list(payload.get("rows") or [])
        except (OSError, TypeError, ValueError):
            pass

    players = _download_csv(f"{_NFLVERSE}/players/players.csv")
    gsis_to_pfr = {
        str(row["gsis_id"]): str(row["pfr_id"])
        for _, row in players.iterrows()
        if pd.notna(row.get("gsis_id")) and pd.notna(row.get("pfr_id"))
    }

    frames: list[pd.DataFrame] = []
    for season in seasons:
        weekly = _download_csv(f"{_NFLVERSE}/stats_player/stats_player_week_{season}.csv")
        weekly = weekly[
            (weekly["season_type"] == "REG")
            & (weekly["position"].isin(POSITIONS))
        ].copy()
        weekly["half_ppr"] = weekly.apply(
            lambda row: _half_ppr_points(row, ppr=ppr, te_premium=te_premium),
            axis=1,
        )
        weekly["pfr_id"] = weekly["player_id"].map(gsis_to_pfr)

        snaps = _download_csv(f"{_NFLVERSE}/snap_counts/snap_counts_{season}.csv")
        snaps = snaps[snaps["position"].isin(POSITIONS)].copy()
        snaps = snaps.rename(columns={"pfr_player_id": "pfr_id"})

        merged = weekly.merge(
            snaps[["season", "week", "pfr_id", "offense_snaps", "offense_pct"]],
            on=["season", "week", "pfr_id"],
            how="left",
        )
        frames.append(merged)

    if not frames:
        return []

    data = _with_health_flags(
        pd.concat(frames, ignore_index=True),
        ["player_id", "player_display_name", "position"],
    )
    data["included"] = data["healthy"]
    rows = data.to_dict("records")

    try:
        import json
        import time

        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(
            json.dumps({"fetched_at": time.time(), "rows": rows}, default=str),
            encoding="utf-8",
        )
    except OSError:
        pass

    return rows


def _entries_for_player(rows: list[dict[str, Any]], player_name: str) -> list[PlayerGameLogEntry]:
    key = normalize_name(player_name)
    data = pd.DataFrame(rows)
    if data.empty:
        return []
    matches = data[data["player_display_name"].map(normalize_name) == key].copy()
    if matches.empty:
        return []
    matches = matches.sort_values(["season", "week"], ascending=[False, False])

    entries: list[PlayerGameLogEntry] = []
    for _, row in matches.iterrows():
        entries.append(
            PlayerGameLogEntry(
                season=int(row["season"]),
                week=int(row["week"]),
                team=str(row.get("team")) if pd.notna(row.get("team")) else None,
                opponent=(
                    str(row.get("opponent_team"))
                    if pd.notna(row.get("opponent_team"))
                    else None
                ),
                points=round(float(row.get("half_ppr") or 0.0), 2),
                healthy=bool(row.get("healthy")),
                included=bool(row.get("included")),
                offense_snaps=_num(row, "offense_snaps") if pd.notna(row.get("offense_snaps")) else None,
                offense_pct=_float_or_none(row, "offense_pct"),
                targets=_num(row, "targets"),
                receptions=_num(row, "receptions"),
                receiving_yards=_num(row, "receiving_yards"),
                receiving_tds=_num(row, "receiving_tds"),
                carries=_num(row, "carries"),
                rushing_yards=_num(row, "rushing_yards"),
                rushing_tds=_num(row, "rushing_tds"),
                attempts=_num(row, "attempts"),
                passing_yards=_num(row, "passing_yards"),
                passing_tds=_num(row, "passing_tds"),
                interceptions=_num(row, "passing_interceptions"),
            )
        )
    return entries


def get_player_game_log(
    db: Session,
    player_id: str,
    league_id: str,
    *,
    force_refresh: bool = False,
) -> PlayerGameLog | None:
    league = db.get(League, league_id)
    if league is None:
        return None

    snapshot = db.scalar(
        select(PlayerSnapshot).where(
            PlayerSnapshot.league_id == league_id,
            PlayerSnapshot.sleeper_player_id == player_id,
        )
    )
    if snapshot is None or not snapshot.player_name:
        return None

    scoring = build_league_scoring_context(league)
    rows = _load_game_log_rows(
        seasons=DEFAULT_SEASONS,
        ppr=scoring.ppr,
        te_premium=scoring.te_premium,
        force_refresh=force_refresh,
    )
    entries = _entries_for_player(rows, snapshot.player_name)
    return PlayerGameLog(
        player_id=player_id,
        league_id=league_id,
        player_name=snapshot.player_name,
        seasons=list(DEFAULT_SEASONS),
        entries=entries,
    )
