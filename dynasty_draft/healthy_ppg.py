from __future__ import annotations

import csv
import io
import json
import time
from dataclasses import dataclass
from typing import Any

import pandas as pd
import requests

from dynasty_draft.projections import _replacement_index
from dynasty_draft.sleeper_client import CACHE_DIR
from dynasty_draft.war_data import POSITIONS, WarData, normalize_name

HEALTHY_PPG_TTL_SECONDS = 7 * 24 * 60 * 60
SNAP_PCT_MIN = 0.15
SNAP_PCT_RELATIVE_MIN = 0.50
SNAP_PCT_BASELINE_MIN_GAMES = 3
SNAP_MIN = 8
DEFAULT_SEASONS = (2024, 2025)
RECENCY_DECAY = 0.97
_WORP_PER_VOR_PPG = 0.012
_CACHE_VERSION = "v7"

_NFLVERSE = "https://github.com/nflverse/nflverse-data/releases/download"
_USER_AGENT = "pickbook/0.3 (personal dynasty draft tool)"


@dataclass(frozen=True)
class HealthyPpgRow:
    healthy_ppg: float
    worp_ppg: float
    availability: float
    healthy_games: int
    total_games: int
    nfl_team: str | None = None


class HealthyPpgStore:
    """Snap-filtered per-game fantasy rates from nflverse weekly stats."""

    def __init__(
        self,
        *,
        by_sleeper_id: dict[str, HealthyPpgRow],
        by_norm_name: dict[str, HealthyPpgRow],
    ) -> None:
        self._by_sleeper_id = by_sleeper_id
        self._by_norm_name = by_norm_name

    def lookup(self, sleeper_id: str | None, *, name: str | None = None) -> HealthyPpgRow | None:
        if sleeper_id and str(sleeper_id) in self._by_sleeper_id:
            return self._by_sleeper_id[str(sleeper_id)]
        if name:
            return self._by_norm_name.get(normalize_name(name))
        return None

    @classmethod
    def load(
        cls,
        *,
        sleeper_players: dict[str, dict[str, Any]],
        war: WarData,
        seasons: tuple[int, ...] = DEFAULT_SEASONS,
        teams: int = 12,
        roster_positions: list[str] | None = None,
        superflex: bool = False,
        ppr: float = 0.5,
        force_refresh: bool = False,
    ) -> HealthyPpgStore:
        roster_positions = roster_positions or ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX"]
        cache_path = CACHE_DIR / f"healthy_ppg_{_CACHE_VERSION}_{'-'.join(str(s) for s in seasons)}.json"
        now = time.time()
        if not force_refresh and cache_path.exists():
            try:
                payload = json.loads(cache_path.read_text(encoding="utf-8"))
                if now - float(payload.get("fetched_at", 0)) < HEALTHY_PPG_TTL_SECONDS:
                    metrics = payload.get("metrics") or {}
                    by_sleeper_id, by_norm_name = _index_for_sleeper(metrics, sleeper_players)
                    return cls(by_sleeper_id=by_sleeper_id, by_norm_name=by_norm_name)
            except (json.JSONDecodeError, OSError, TypeError, ValueError):
                pass

        metrics = _build_metrics(
            seasons=seasons,
            war=war,
            teams=teams,
            roster_positions=roster_positions,
            superflex=superflex,
            ppr=ppr,
        )
        by_sleeper_id, by_norm_name = _index_for_sleeper(metrics, sleeper_players)

        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(
            json.dumps(
                {
                    "fetched_at": now,
                    "metrics": metrics,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return cls(by_sleeper_id=by_sleeper_id, by_norm_name=by_norm_name)


def _row_from_dict(raw: dict[str, Any]) -> HealthyPpgRow | None:
    try:
        nfl_team = raw.get("nfl_team")
        return HealthyPpgRow(
            healthy_ppg=float(raw["healthy_ppg"]),
            worp_ppg=float(raw["worp_ppg"]),
            availability=float(raw["availability"]),
            healthy_games=int(raw["healthy_games"]),
            total_games=int(raw["total_games"]),
            nfl_team=str(nfl_team).upper() if nfl_team else None,
        )
    except (KeyError, TypeError, ValueError):
        return None


def _session() -> requests.Session:
    session = requests.Session()
    session.headers["User-Agent"] = _USER_AGENT
    return session


def _download_csv(url: str) -> pd.DataFrame:
    response = _session().get(url, timeout=120)
    response.raise_for_status()
    return pd.read_csv(io.StringIO(response.text), low_memory=False)


def _build_metrics(
    *,
    seasons: tuple[int, ...],
    war: WarData,
    teams: int,
    roster_positions: list[str],
    superflex: bool,
    ppr: float,
) -> dict[str, dict[str, Any]]:
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
            lambda row: _half_ppr_points(row, ppr=ppr),
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
        return {}

    keys = ["player_id", "player_display_name", "position"]
    data = _with_health_flags(pd.concat(frames, ignore_index=True), keys)
    team_col = "recent_team" if "recent_team" in data.columns else "team"
    healthy_only = data[data["healthy"]].copy()
    healthy_only = _with_recency_weights(healthy_only, keys)
    grouped = _availability_rows(data, keys, team_col, seasons)
    healthy_stats = _healthy_stats(healthy_only, keys)
    grouped = grouped.merge(healthy_stats, on=keys, how="left")
    grouped["healthy_ppg"] = grouped["healthy_ppg"].fillna(0.0)
    grouped["healthy_games"] = grouped["healthy_games"].fillna(0).astype(int)
    grouped["availability"] = grouped.apply(
        lambda row: (row["healthy_games"] / row["total_games"]) if row["total_games"] else 0.0,
        axis=1,
    )

    replacement_ppg: dict[str, float] = {}
    for pos in POSITIONS:
        pos_rows = grouped[grouped["position"] == pos].sort_values("healthy_ppg", ascending=False)
        if pos_rows.empty:
            replacement_ppg[pos] = 0.0
            continue
        idx = _replacement_index(
            pos,
            teams=teams,
            roster_positions=roster_positions,
            superflex=superflex,
        )
        idx = min(idx, len(pos_rows) - 1)
        replacement_ppg[pos] = float(pos_rows.iloc[idx]["healthy_ppg"])

    worp_per_vor = _calibrate_worp_per_vor(grouped, replacement_ppg, war)

    team_by_gsis: dict[str, str] = {}
    for key_values, group in healthy_only.groupby(keys, dropna=False):
        team = _most_common_team(group, team_col)
        if team:
            gsis_id = key_values[0] if isinstance(key_values, tuple) else str(key_values)
            team_by_gsis[str(gsis_id)] = team

    metrics: dict[str, dict[str, Any]] = {}
    for _, row in grouped.iterrows():
        pos = str(row["position"])
        healthy_ppg = float(row["healthy_ppg"])
        vor_ppg = max(0.0, healthy_ppg - replacement_ppg.get(pos, 0.0))
        worp_ppg = vor_ppg * worp_per_vor.get(pos, _WORP_PER_VOR_PPG)
        nfl_team = team_by_gsis.get(str(row["player_id"]))
        payload = {
            "healthy_ppg": round(healthy_ppg, 2),
            "worp_ppg": round(worp_ppg, 4),
            "availability": round(float(row["availability"]), 3),
            "healthy_games": int(row["healthy_games"]),
            "total_games": int(row["total_games"]),
            "name": str(row["player_display_name"]),
            "gsis_id": str(row["player_id"]),
            "pos": pos,
        }
        if nfl_team:
            payload["nfl_team"] = nfl_team
        metrics[f"gsis:{row['player_id']}"] = payload
        metrics[f"name:{normalize_name(str(row['player_display_name']))}"] = payload
    return metrics


def _weighted_average(values: pd.Series, weights: pd.Series) -> float:
    total_weight = float(weights.sum())
    if total_weight <= 0:
        return 0.0
    return float((values.astype(float) * weights.astype(float)).sum() / total_weight)


def _with_recency_weights(data: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    if data.empty:
        data["recency_weight"] = pd.Series(dtype=float)
        return data

    weighted = data.copy()
    weighted["recency_weight"] = 1.0
    weighted["_game_order"] = pd.to_numeric(weighted["season"], errors="coerce").fillna(0) * 100
    weighted["_game_order"] += pd.to_numeric(weighted["week"], errors="coerce").fillna(0)

    for _, group in weighted.groupby(keys, dropna=False):
        ordered = group.sort_values("_game_order", ascending=False).index
        for age, idx in enumerate(ordered):
            weighted.at[idx, "recency_weight"] = RECENCY_DECAY**age

    return weighted.drop(columns=["_game_order"])


def _healthy_stats(data: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    for key_values, group in data.groupby(keys, dropna=False):
        if not isinstance(key_values, tuple):
            key_values = (key_values,)
        record = dict(zip(keys, key_values, strict=True))
        record["healthy_ppg"] = _weighted_average(group["half_ppr"], group["recency_weight"])
        record["healthy_games"] = int(len(group))
        records.append(record)
    return pd.DataFrame(records, columns=[*keys, "healthy_ppg", "healthy_games"])


def _team_game_counts(seasons: tuple[int, ...]) -> dict[tuple[int, str], int]:
    try:
        schedules = _download_csv(f"{_NFLVERSE}/schedules/games.csv")
    except Exception:
        return {}

    schedules = schedules[
        (schedules["game_type"] == "REG")
        & (schedules["season"].isin(list(seasons)))
    ].copy()

    counts: dict[tuple[int, str], int] = {}
    for _, row in schedules.iterrows():
        season = int(row["season"])
        for col in ("home_team", "away_team"):
            team = row.get(col)
            if pd.isna(team):
                continue
            key = (season, str(team).upper())
            counts[key] = counts.get(key, 0) + 1
    return counts


def _most_common_team(group: pd.DataFrame, team_col: str) -> str | None:
    if team_col not in group.columns:
        return None
    teams = group[team_col].dropna().astype(str).str.upper()
    if teams.empty:
        return None
    return str(teams.mode().iloc[0])


def _availability_rows(
    data: pd.DataFrame,
    keys: list[str],
    team_col: str,
    seasons: tuple[int, ...],
) -> pd.DataFrame:
    team_games = _team_game_counts(seasons)
    records: list[dict[str, Any]] = []
    for key_values, group in data.groupby(keys, dropna=False):
        if not isinstance(key_values, tuple):
            key_values = (key_values,)
        record = dict(zip(keys, key_values, strict=True))

        scheduled_games = 0
        for season_value, season_group in group.groupby("season", dropna=False):
            try:
                season = int(season_value)
            except (TypeError, ValueError):
                scheduled_games += int(len(season_group))
                continue

            team = _most_common_team(season_group, team_col)
            scheduled_games += team_games.get((season, team or ""), int(len(season_group)))

        record["total_games"] = max(int(scheduled_games), int(len(group)))
        records.append(record)

    return pd.DataFrame(records, columns=[*keys, "total_games"])


def _half_ppr_points(row: pd.Series, *, ppr: float) -> float:
    std = float(row.get("fantasy_points") or 0.0)
    full = float(row.get("fantasy_points_ppr") or std)
    if ppr >= 1.0:
        return full
    if ppr <= 0.0:
        return std
    if ppr == 0.5:
        return (std + full) / 2.0
    rec = float(row.get("receptions") or 0.0)
    return std + ppr * rec


def _is_healthy_game(row: pd.Series) -> bool:
    pos = str(row.get("position") or "")
    pts = float(row.get("half_ppr") or 0.0)
    if pos == "QB":
        return float(row.get("attempts") or 0.0) > 0 or pts > 0.0
    snaps = row.get("offense_snaps")
    pct = row.get("offense_pct")
    if pd.isna(snaps) and pd.isna(pct):
        return pts > 1.0
    if pd.notna(snaps) and float(snaps) >= SNAP_MIN:
        return True
    return pd.notna(pct) and float(pct) >= SNAP_PCT_MIN


def _with_health_flags(data: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    flagged = data.copy()
    flagged["healthy"] = flagged.apply(_is_healthy_game, axis=1)
    if flagged.empty or "offense_pct" not in flagged.columns:
        return flagged

    flagged["_offense_pct_num"] = pd.to_numeric(flagged["offense_pct"], errors="coerce")
    for _, group in flagged.groupby(keys, dropna=False):
        pct = flagged.loc[group.index, "_offense_pct_num"]
        baseline = pct[flagged.loc[group.index, "healthy"] & pct.notna()]
        if len(baseline) < SNAP_PCT_BASELINE_MIN_GAMES:
            continue
        typical_pct = float(baseline.quantile(0.75))
        if typical_pct <= 0:
            continue
        min_pct = max(SNAP_PCT_MIN, typical_pct * SNAP_PCT_RELATIVE_MIN)
        low_snap_share = pct.notna() & (pct < min_pct)
        flagged.loc[group.index[low_snap_share], "healthy"] = False

    return flagged.drop(columns=["_offense_pct_num"])


def _calibrate_worp_per_vor(
    grouped: pd.DataFrame,
    replacement_ppg: dict[str, float],
    war: WarData,
) -> dict[str, float]:
    ratios: dict[str, list[float]] = {pos: [] for pos in POSITIONS}
    for player in war.players:
        if player.worp is None or player.worp < 0.15:
            continue
        match = grouped[grouped["player_display_name"].map(normalize_name) == normalize_name(player.name)]
        if match.empty:
            continue
        row = match.iloc[0]
        healthy_ppg = float(row["healthy_ppg"])
        vor_ppg = healthy_ppg - replacement_ppg.get(player.pos, 0.0)
        if vor_ppg <= 0:
            continue
        season_vor_est = vor_ppg * 17.0
        if season_vor_est > 0:
            ratios[player.pos].append(player.worp / season_vor_est)
    calibrated: dict[str, float] = {}
    for pos in POSITIONS:
        vals = sorted(ratios[pos])
        if vals:
            calibrated[pos] = vals[len(vals) // 2]
        else:
            calibrated[pos] = _WORP_PER_VOR_PPG
    return calibrated


def _index_for_sleeper(
    metrics: dict[str, dict[str, Any]],
    sleeper_players: dict[str, dict[str, Any]],
) -> tuple[dict[str, HealthyPpgRow], dict[str, HealthyPpgRow]]:
    by_gsis = {
        key[5:]: payload
        for key, payload in metrics.items()
        if key.startswith("gsis:")
    }
    by_name = {
        key[5:]: payload
        for key, payload in metrics.items()
        if key.startswith("name:")
    }

    by_sleeper_id: dict[str, HealthyPpgRow] = {}
    by_norm_name: dict[str, HealthyPpgRow] = {}
    for sleeper_id, player in sleeper_players.items():
        payload = None
        gsis = player.get("gsis_id")
        if gsis and str(gsis) in by_gsis:
            payload = by_gsis[str(gsis)]
        if payload is None:
            payload = by_name.get(normalize_name(player.get("full_name") or ""))
        if payload is None:
            continue
        row = _row_from_dict(payload)
        if row is None:
            continue
        by_sleeper_id[str(sleeper_id)] = row
        name_key = normalize_name(player.get("full_name") or "")
        if name_key:
            by_norm_name[name_key] = row
    return by_sleeper_id, by_norm_name
