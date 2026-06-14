"""Volume/opportunity → projected PPG at sync (§16, Phase 5)."""

from __future__ import annotations

import io
import json
import time
from dataclasses import dataclass
from typing import Any

import pandas as pd
import requests

from dynasty_draft.dynasty_score import _PEAK_AGE, DynastyRatingCurve, curved_composite_to_rating
from dynasty_draft.healthy_ppg import (
    DEFAULT_SEASONS,
    _half_ppr_points,
    _with_health_flags,
)
from dynasty_draft.projections import SleeperProjectionStore
from dynasty_draft.sleeper_client import CACHE_DIR
from dynasty_draft.war_data import POSITIONS, normalize_name

OPPORTUNITY_TTL_SECONDS = 7 * 24 * 60 * 60
_NFLVERSE = "https://github.com/nflverse/nflverse-data/releases/download"
_USER_AGENT = "blackbook/0.1 (dynasty portfolio tool)"
RECENCY_DECAY = 0.97
_CACHE_VERSION = "v8"
_YOUNG_UPSIDE_TV_MIN = 3000.0


@dataclass(frozen=True)
class OpportunityRow:
    opportunity_score: float
    target_share: float | None
    rush_share: float | None
    team_plays_per_game: float | None
    volume_per_game: float | None
    efficiency: float | None
    nflverse_ppg: float | None
    sample_games: int | None
    nfl_team: str | None = None


@dataclass(frozen=True)
class ProjectionResult:
    opportunity_score: float | None
    projected_ppg: float | None
    projection_source: str | None
    outlook: dict[str, Any]


class OpportunityStore:
    """Trailing nflverse volume + team pace, keyed by Sleeper player id."""

    def __init__(
        self,
        *,
        by_sleeper_id: dict[str, OpportunityRow],
        by_norm_name: dict[str, OpportunityRow],
    ) -> None:
        self._by_sleeper_id = by_sleeper_id
        self._by_norm_name = by_norm_name

    def lookup(self, sleeper_id: str | None, *, name: str | None = None) -> OpportunityRow | None:
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
        seasons: tuple[int, ...] = DEFAULT_SEASONS,
        ppr: float = 0.5,
        te_premium: float = 0.0,
        force_refresh: bool = False,
    ) -> OpportunityStore:
        cache_path = (
            CACHE_DIR
            / f"opportunity_{_CACHE_VERSION}_{'-'.join(str(s) for s in seasons)}_p{ppr}_te{te_premium}.json"
        )
        now = time.time()
        if not force_refresh and cache_path.exists():
            try:
                payload = json.loads(cache_path.read_text(encoding="utf-8"))
                if now - float(payload.get("fetched_at", 0)) < OPPORTUNITY_TTL_SECONDS:
                    metrics = payload.get("metrics") or {}
                    by_sleeper_id, by_norm_name = _index_for_sleeper(metrics, sleeper_players)
                    return cls(by_sleeper_id=by_sleeper_id, by_norm_name=by_norm_name)
            except (json.JSONDecodeError, OSError, TypeError, ValueError):
                pass

        metrics = _build_opportunity_metrics(seasons=seasons, ppr=ppr, te_premium=te_premium)
        by_sleeper_id, by_norm_name = _index_for_sleeper(metrics, sleeper_players)

        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(
            json.dumps({"fetched_at": now, "metrics": metrics}, indent=2),
            encoding="utf-8",
        )
        return cls(by_sleeper_id=by_sleeper_id, by_norm_name=by_norm_name)


def _session() -> requests.Session:
    session = requests.Session()
    session.headers["User-Agent"] = _USER_AGENT
    return session


def _download_csv(url: str) -> pd.DataFrame:
    response = _session().get(url, timeout=120)
    response.raise_for_status()
    return pd.read_csv(io.StringIO(response.text), low_memory=False)


def _build_opportunity_metrics(
    *,
    seasons: tuple[int, ...],
    ppr: float,
    te_premium: float = 0.0,
) -> dict[str, dict[str, Any]]:
    players = _download_csv(f"{_NFLVERSE}/players/players.csv")
    gsis_to_pfr = {
        str(row["gsis_id"]): str(row["pfr_id"])
        for _, row in players.iterrows()
        if pd.notna(row.get("gsis_id")) and pd.notna(row.get("pfr_id"))
    }

    weekly_frames: list[pd.DataFrame] = []
    team_frames: list[pd.DataFrame] = []

    for season in seasons:
        weekly = _download_csv(f"{_NFLVERSE}/stats_player/stats_player_week_{season}.csv")
        weekly = weekly[
            (weekly["season_type"] == "REG") & (weekly["position"].isin(POSITIONS))
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
        weekly_frames.append(merged)

        try:
            team_week = _download_csv(f"{_NFLVERSE}/stats_team/stats_team_week_{season}.csv")
            team_week = team_week[team_week["season_type"] == "REG"].copy()
            team_frames.append(team_week)
        except Exception:
            pass

    if not weekly_frames:
        return {}

    data = pd.concat(weekly_frames, ignore_index=True)
    player_team_col = "recent_team" if "recent_team" in data.columns else "team"
    data = _with_health_flags(data, ["player_id", "player_display_name", "position"])
    healthy = data[data["healthy"]].copy()

    for col in ("targets", "carries", "attempts", "receptions"):
        if col not in healthy.columns:
            healthy[col] = 0.0
        healthy[col] = pd.to_numeric(healthy[col], errors="coerce").fillna(0.0)

    team_pace: dict[str, float] = {}
    if team_frames:
        team_data = pd.concat(team_frames, ignore_index=True)
        pass_col = "pass_attempts" if "pass_attempts" in team_data.columns else None
        rush_col = next(
            (c for c in ("rush_attempts", "carries", "rushing_attempts") if c in team_data.columns),
            None,
        )
        if pass_col or rush_col:
            passes = (
                pd.to_numeric(team_data[pass_col], errors="coerce").fillna(0)
                if pass_col
                else 0.0
            )
            rushes = (
                pd.to_numeric(team_data[rush_col], errors="coerce").fillna(0)
                if rush_col
                else 0.0
            )
            team_data["off_plays"] = passes + rushes
        else:
            team_data["off_plays"] = 60.0
        team_pace_col = "team_abbr" if "team_abbr" in team_data.columns else "team"
        pace = team_data.groupby(team_pace_col, dropna=False)["off_plays"].mean().to_dict()
        team_pace = {str(k): float(v) for k, v in pace.items() if k and pd.notna(k)}

    team_weekly = (
        healthy.groupby([player_team_col, "season", "week"], dropna=False)
        .agg(
            team_targets=("targets", "sum"),
            team_carries=("carries", "sum"),
            team_attempts=("attempts", "sum"),
        )
        .reset_index()
    )
    healthy = healthy.merge(
        team_weekly,
        on=[player_team_col, "season", "week"],
        how="left",
    )
    keys = ["player_id", "player_display_name", "position", player_team_col]
    healthy = _with_recency_weights(healthy, keys)

    grouped = _opportunity_rows(healthy, keys)

    metrics: dict[str, dict[str, Any]] = {}
    for _, row in grouped.iterrows():
        pos = str(row["position"])
        team = str(row.get(player_team_col) or "")
        targets_pg = float(row["targets_pg"])
        carries_pg = float(row["carries_pg"])
        attempts_pg = float(row["attempts_pg"])
        fp_pg = float(row["fp_pg"])
        team_targets = float(row["team_targets_pg"] or 0)
        team_carries = float(row["team_carries_pg"] or 0)
        team_attempts = float(row["team_attempts_pg"] or 0)

        target_share = (targets_pg / team_targets) if team_targets > 0 else None
        rush_share = (carries_pg / team_carries) if team_carries > 0 else None
        attempt_share = (attempts_pg / team_attempts) if team_attempts > 0 else None

        team_plays_pg = team_pace.get(team)
        if team_plays_pg is None:
            team_plays_pg = max(team_targets, team_carries, team_attempts, 55.0)

        if pos == "QB":
            volume_pg = attempts_pg
            share = attempt_share or 0.0
            team_vol = team_attempts or team_plays_pg * 0.55
            opportunity_score = round(min(100.0, max(0.0, share * 100.0)), 1)
        elif pos == "RB":
            volume_pg = carries_pg + targets_pg * 0.25
            share = rush_share or 0.0
            team_vol = team_carries or team_plays_pg * 0.42
        else:
            volume_pg = targets_pg + carries_pg * 0.15
            share = target_share or 0.0
            team_vol = team_targets or team_plays_pg * 0.58

        efficiency = (fp_pg / volume_pg) if volume_pg > 0.05 else None
        nflverse_ppg = None
        if efficiency is not None and share > 0 and team_vol > 0:
            nflverse_ppg = round(share * team_vol * efficiency, 2)

        if pos != "QB":
            opportunity_score = round(min(100.0, max(0.0, share * 100.0)), 1)

        payload = {
            "opportunity_score": opportunity_score,
            "target_share": round(target_share, 4) if target_share is not None else None,
            "rush_share": round(rush_share, 4) if rush_share is not None else None,
            "team_plays_per_game": round(team_plays_pg, 2),
            "volume_per_game": round(volume_pg, 2),
            "efficiency": round(efficiency, 4) if efficiency is not None else None,
            "nflverse_ppg": nflverse_ppg,
            "sample_games": int(row["games"]),
            "name": str(row["player_display_name"]),
            "gsis_id": str(row["player_id"]),
            "pos": pos,
        }
        if team:
            payload["nfl_team"] = team.upper()
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


def _opportunity_rows(data: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    metric_cols = [
        "targets",
        "carries",
        "attempts",
        "half_ppr",
        "team_targets",
        "team_carries",
        "team_attempts",
    ]
    records: list[dict[str, Any]] = []
    for key_values, group in data.groupby(keys, dropna=False):
        if not isinstance(key_values, tuple):
            key_values = (key_values,)
        record = dict(zip(keys, key_values, strict=True))
        weights = group["recency_weight"]
        for col in metric_cols:
            record[col] = _weighted_average(group[col], weights)
        record["games"] = int(len(group))
        records.append(record)

    rows = []
    for record in records:
        rows.append(
            {
                **{key: record[key] for key in keys},
                "targets_pg": record["targets"],
                "carries_pg": record["carries"],
                "attempts_pg": record["attempts"],
                "fp_pg": record["half_ppr"],
                "team_targets_pg": record["team_targets"],
                "team_carries_pg": record["team_carries"],
                "team_attempts_pg": record["team_attempts"],
                "games": record["games"],
            }
        )
    return pd.DataFrame(
        rows,
        columns=[
            *keys,
            "targets_pg",
            "carries_pg",
            "attempts_pg",
            "fp_pg",
            "team_targets_pg",
            "team_carries_pg",
            "team_attempts_pg",
            "games",
        ],
    )


def _row_from_dict(raw: dict[str, Any]) -> OpportunityRow | None:
    try:
        nfl_team = raw.get("nfl_team")
        return OpportunityRow(
            opportunity_score=float(raw["opportunity_score"]),
            target_share=raw.get("target_share"),
            rush_share=raw.get("rush_share"),
            team_plays_per_game=raw.get("team_plays_per_game"),
            volume_per_game=raw.get("volume_per_game"),
            efficiency=raw.get("efficiency"),
            nflverse_ppg=raw.get("nflverse_ppg"),
            sample_games=raw.get("sample_games"),
            nfl_team=str(nfl_team).upper() if nfl_team else None,
        )
    except (KeyError, TypeError, ValueError):
        return None


def _index_for_sleeper(
    metrics: dict[str, dict[str, Any]],
    sleeper_players: dict[str, dict[str, Any]],
) -> tuple[dict[str, OpportunityRow], dict[str, OpportunityRow]]:
    by_gsis = {key[5:]: payload for key, payload in metrics.items() if key.startswith("gsis:")}
    by_name = {key[5:]: payload for key, payload in metrics.items() if key.startswith("name:")}

    by_sleeper_id: dict[str, OpportunityRow] = {}
    by_norm_name: dict[str, OpportunityRow] = {}
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


def _sleeper_ppg(
    player_id: str,
    *,
    projections: SleeperProjectionStore | None,
) -> float | None:
    if projections is None:
        return None
    season_pts = projections.projected_points(player_id)
    if season_pts is None:
        return None
    return round(season_pts / 17.0, 2)


def _blend_projected_ppg(
    nflverse_ppg: float | None,
    sleeper_ppg: float | None,
    *,
    sample_games: int | None = None,
    dynasty_rookie: bool = False,
    years_exp: int | None = None,
    trade_value: float | None = None,
) -> tuple[float | None, str | None]:
    if nflverse_ppg is not None and sleeper_ppg is not None:
        sample_factor = min(max(float(sample_games or 0) / 12.0, 0.0), 1.0)
        nflverse_weight = 0.25 + 0.45 * sample_factor
        if dynasty_rookie:
            nflverse_weight *= 0.5
        if _is_young_upside_profile(years_exp=years_exp, trade_value=trade_value):
            nflverse_weight = min(nflverse_weight, 0.45)
        nflverse_weight = min(max(nflverse_weight, 0.15), 0.70)
        blended = round(
            nflverse_weight * nflverse_ppg + (1.0 - nflverse_weight) * sleeper_ppg,
            2,
        )
        return blended, "nflverse_blend"
    if nflverse_ppg is not None:
        return nflverse_ppg, "custom"
    if sleeper_ppg is not None:
        return sleeper_ppg, "sleeper"
    return None, None


def _apply_historical_ppg_adjustment(
    projected_ppg: float | None,
    projection_source: str | None,
    *,
    hppg: float | None,
    hppg_expected: bool,
    sample_games: int | None,
    dynasty_rookie: bool,
    years_exp: int | None = None,
    trade_value: float | None = None,
) -> tuple[float | None, str | None]:
    if (
        projected_ppg is None
        or hppg is None
        or hppg_expected
        or dynasty_rookie
    ):
        return projected_ppg, projection_source

    sample_factor = min(max(float(sample_games or 0) / 12.0, 0.0), 1.0)
    historical_weight = 0.15 + 0.15 * sample_factor
    if (
        _is_young_upside_profile(years_exp=years_exp, trade_value=trade_value)
        and float(hppg) < projected_ppg
    ):
        historical_weight = min(historical_weight, 0.10)
    adjusted = round(
        historical_weight * float(hppg) + (1.0 - historical_weight) * projected_ppg,
        2,
    )
    return adjusted, "historical_blend"


def _is_young_upside_profile(
    *,
    years_exp: int | None,
    trade_value: float | None,
) -> bool:
    if years_exp is None or trade_value is None:
        return False
    return years_exp <= 1 and trade_value >= _YOUNG_UPSIDE_TV_MIN


def classify_archetype(
    *,
    position: str | None,
    trade_value: float | None,
    worp_ppg: float | None,
    hppg: float | None,
    target_share: float | None,
    rush_share: float | None,
    dynasty_rookie: bool,
) -> str | None:
    pos = (position or "").upper()
    tv = trade_value or 0.0
    worp = worp_ppg or 0.0
    hppg_val = hppg or 0.0

    if dynasty_rookie and tv > 4000 and worp < 0.08:
        return "developmental"
    if hppg_val >= 12 and tv < 3500:
        return "undervalued_producer"
    if pos == "WR":
        if (target_share or 0) >= 0.24:
            return "alpha_wr"
        if (target_share or 0) >= 0.14:
            return "slot_volume"
        return "depth_wr"
    if pos == "RB":
        if (rush_share or 0) >= 0.45:
            return "workhorse_rb"
        if (rush_share or 0) >= 0.22:
            return "committee_rb"
        return "pass_catching_rb" if (target_share or 0) >= 0.08 else "depth_rb"
    if pos == "TE":
        if (target_share or 0) >= 0.18:
            return "alpha_te"
        return "blocking_te"
    if pos == "QB":
        if hppg_val >= 18:
            return "elite_qb"
        if hppg_val >= 14:
            return "starter_qb"
        return "developmental_qb"
    return None


def peak_outlook(position: str | None, age: int | None) -> dict[str, int | None]:
    peak = _PEAK_AGE.get((position or "").upper(), 27)
    if age is None:
        return {"years_to_peak": None, "peak_window_end": peak + 2}
    return {
        "years_to_peak": peak - age,
        "peak_window_end": peak + 2,
    }


def position_percentiles(
    pool_rows: list[dict[str, Any]],
) -> dict[str, dict[str, float | None]]:
    """Percentile ranks within position for hppg, worp_ppg, trade_value (0–100)."""
    by_pos: dict[str, list[dict[str, Any]]] = {}
    for row in pool_rows:
        pos = (row.get("position") or "").upper()
        if not pos:
            continue
        by_pos.setdefault(pos, []).append(row)

    result: dict[str, dict[str, float | None]] = {}
    for player_id, row in ((r["player_id"], r) for r in pool_rows):
        pos = (row.get("position") or "").upper()
        peers = by_pos.get(pos, [])
        if len(peers) < 2:
            result[player_id] = {"hppg_pct": None, "worp_ppg_pct": None, "tv_pct": None}
            continue

        def _pct(field: str) -> float | None:
            vals = sorted(float(p[field]) for p in peers if p.get(field) is not None)
            mine = row.get(field)
            if mine is None or not vals:
                return None
            below = sum(1 for v in vals if v < float(mine))
            return round(100.0 * below / max(len(vals) - 1, 1), 1)

        result[player_id] = {
            "hppg_pct": _pct("hppg"),
            "worp_ppg_pct": _pct("worp_ppg"),
            "tv_pct": _pct("trade_value"),
        }
    return result


def compute_projection(
    *,
    player_id: str,
    player_name: str | None,
    position: str | None,
    age: int | None,
    trade_value: float | None,
    hppg: float | None,
    worp_ppg: float | None,
    dynasty_rookie: bool,
    opportunity_store: OpportunityStore | None,
    projections: SleeperProjectionStore | None,
    years_exp: int | None = None,
    hppg_expected: bool = False,
    percentile_row: dict[str, float | None] | None = None,
) -> ProjectionResult:
    opp = None
    if opportunity_store is not None:
        opp = opportunity_store.lookup(player_id, name=player_name)

    sleeper_ppg = _sleeper_ppg(player_id, projections=projections)
    nflverse_ppg = opp.nflverse_ppg if opp else None
    projected_ppg, projection_source = _blend_projected_ppg(
        nflverse_ppg,
        sleeper_ppg,
        sample_games=opp.sample_games if opp else None,
        dynasty_rookie=dynasty_rookie,
        years_exp=years_exp,
        trade_value=trade_value,
    )
    projected_ppg, projection_source = _apply_historical_ppg_adjustment(
        projected_ppg,
        projection_source,
        hppg=hppg,
        hppg_expected=hppg_expected,
        sample_games=opp.sample_games if opp else None,
        dynasty_rookie=dynasty_rookie,
        years_exp=years_exp,
        trade_value=trade_value,
    )

    if projected_ppg is None and hppg is not None:
        projected_ppg = round(float(hppg), 2)
        projection_source = "sleeper" if dynasty_rookie else "custom"

    archetype = classify_archetype(
        position=position,
        trade_value=trade_value,
        worp_ppg=worp_ppg,
        hppg=hppg,
        target_share=opp.target_share if opp else None,
        rush_share=opp.rush_share if opp else None,
        dynasty_rookie=dynasty_rookie,
    )
    peak = peak_outlook(position, age)

    outlook: dict[str, Any] = {
        "archetype": archetype,
        "peak_window": peak,
        "opportunity_score": opp.opportunity_score if opp else None,
    }
    if percentile_row:
        outlook["percentiles"] = percentile_row
    if opp:
        outlook["volume"] = {
            "target_share": opp.target_share,
            "rush_share": opp.rush_share,
            "team_plays_per_game": opp.team_plays_per_game,
        }

    return ProjectionResult(
        opportunity_score=opp.opportunity_score if opp else None,
        projected_ppg=projected_ppg,
        projection_source=projection_source,
        outlook=outlook,
    )


def win_now_relative_ratings(
    pool: list[tuple[str, dict[str, Any]]],
    *,
    curve: DynastyRatingCurve | None = None,
) -> dict[str, int]:
    """
    Win-now rating: composite of projected_ppg (50%), worp_ppg (25%), porp (25%),
    then rank-mapped within position so rank-1 → 99, rank-10 → 82, rank-20 → 77.
    Formula: max(35, round(99 - 7.5 * ln(rank))).
    """
    import math

    _WIN_NOW_WEIGHTS = (
        ("projected_ppg", 0.50),
        ("worp_ppg", 0.25),
        ("porp", 0.25),
    )

    def _get(row: dict[str, Any], key: str) -> float | None:
        v = row.get(key)
        if v is None and key == "projected_ppg":
            v = row.get("hppg")
        return float(v) if v is not None else None

    def _normalize(vals: list[float]) -> list[float]:
        mn, mx = min(vals), max(vals)
        if mx == mn:
            return [1.0] * len(vals)
        return [(v - mn) / (mx - mn) for v in vals]

    by_pos: dict[str, list[tuple[str, dict[str, float | None]]]] = {}
    for player_id, row in pool:
        pos = (row.get("position") or "").upper()
        if pos not in POSITIONS:
            continue
        metrics = {key: _get(row, key) for key, _ in _WIN_NOW_WEIGHTS}
        by_pos.setdefault(pos, []).append((player_id, metrics))

    ratings: dict[str, int] = {}
    for pos_rows in by_pos.values():
        if not pos_rows:
            continue

        norm: dict[str, list[float]] = {}
        for key, _ in _WIN_NOW_WEIGHTS:
            raw_vals = [m[key] for _, m in pos_rows]
            present = [(i, v) for i, v in enumerate(raw_vals) if v is not None]
            if not present:
                norm[key] = [0.0] * len(pos_rows)
                continue
            indices, values = zip(*present)
            normed = _normalize(list(values))
            col = [0.0] * len(pos_rows)
            for idx, nv in zip(indices, normed):
                col[idx] = nv
            norm[key] = col

        composites: list[tuple[str, float]] = []
        for i, (player_id, metrics) in enumerate(pos_rows):
            total_weight = 0.0
            composite = 0.0
            for key, weight in _WIN_NOW_WEIGHTS:
                if metrics[key] is not None:
                    composite += weight * norm[key][i]
                    total_weight += weight
            composites.append((player_id, composite / total_weight if total_weight > 0 else 0.0))

        # Percentile-based rating: p=1 is best in pool, p=0 is worst.
        # Formula: 99 - 40*sqrt(1-p) gives proper spread —
        #   top 1-2 → 90s, top 10 → ~82, top 20 → ~74, worst → ~59.
        vals = [c for _, c in composites]
        min_c, max_c = min(vals), max(vals)
        for player_id, composite in composites:
            p = (composite - min_c) / (max_c - min_c) if max_c > min_c else 1.0
            raw = round(99 - 40 * math.sqrt(1.0 - p))
            ratings[player_id] = max(35, min(99, raw))
    return ratings
