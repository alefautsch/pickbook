from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from dynasty_draft.war_data import PlayerValue

FLEX_PPG_POSITIONS = frozenset({"RB", "WR", "TE"})

# Ideal peak ages for dynasty value (years before decline).
_PEAK_AGE = {"QB": 29, "RB": 25, "WR": 27, "TE": 26}

RATING_MIN = 50
RATING_MAX = 99


def composite_to_rating(composite: float) -> int:
    """Map 0–1 composite to Madden-style 50–99 rating."""
    raw = round(RATING_MIN + composite * (RATING_MAX - RATING_MIN))
    return max(RATING_MIN, min(RATING_MAX, raw))


@dataclass(frozen=True)
class DynastyRatingCurve:
    """Stretch raw composite scores so elites land in the mid/high 90s."""

    exponent: float = 0.62
    # Share of the WORP component replaced by snap-filtered per-game production (W/g + HPPG).
    per_game_tilt: float = 0.73

    @classmethod
    def from_config(cls, raw: dict[str, float] | None) -> DynastyRatingCurve:
        if not raw:
            return cls()
        return cls(
            exponent=float(raw.get("exponent", 0.62)),
            per_game_tilt=float(raw.get("per_game_tilt", 0.73)),
        )


def curved_composite_to_rating(
    composite: float,
    *,
    raw_min: float,
    raw_max: float,
    exponent: float = 0.62,
) -> int:
    """
    Map raw 0–1 composite to 50–99 using board min/max stretch + power curve.
    Top board players (e.g. Josh Allen) land ~96–99; the median shifts up modestly.
    """
    if raw_max <= raw_min:
        stretched = 1.0 if composite >= raw_max else 0.0
    else:
        stretched = (composite - raw_min) / (raw_max - raw_min)
        stretched = max(0.0, min(1.0, stretched))
    if exponent > 0:
        stretched **= exponent
    return composite_to_rating(stretched)


DEFAULT_DYNASTY_WEIGHTS: dict[str, float] = {
    "tv": 0.37,
    "worp": 0.33,
    "upside": 0.15,
    "age": 0.10,
    "trajectory": 0.05,
}


@dataclass(frozen=True)
class DynastyWeights:
    tv: float = 0.37
    worp: float = 0.33
    upside: float = 0.15
    age: float = 0.10
    trajectory: float = 0.05

    @classmethod
    def from_config(cls, raw: dict[str, float] | None) -> DynastyWeights:
        if not raw:
            return cls()
        return cls(
            tv=float(raw.get("tv", DEFAULT_DYNASTY_WEIGHTS["tv"])),
            worp=float(raw.get("worp", DEFAULT_DYNASTY_WEIGHTS["worp"])),
            upside=float(raw.get("upside", DEFAULT_DYNASTY_WEIGHTS["upside"])),
            age=float(raw.get("age", DEFAULT_DYNASTY_WEIGHTS["age"])),
            trajectory=float(raw.get("trajectory", DEFAULT_DYNASTY_WEIGHTS["trajectory"])),
        )


def _age_premium(pos: str, age: int | None) -> float:
    """0–1: youth bonus for dynasty; veterans taper off."""
    if age is None:
        return 0.45
    peak = _PEAK_AGE.get(pos, 27)
    years_to_peak = peak - age
    if years_to_peak >= 5:
        return 1.0
    if years_to_peak >= 2:
        return 0.72
    if years_to_peak >= 0:
        return 0.55
    if years_to_peak >= -3:
        return 0.32
    return 0.12


@dataclass(frozen=True)
class DynastyReferenceAnchors:
    """Fixed TV / WORP ceilings for normalizing dynasty ratings across views."""

    max_tv: float
    max_worp: float


@dataclass(frozen=True)
class PerGameAnchorMaxes:
    """Per-game HPPG / W·g ceilings split by lineup role (§5.4)."""

    qb: tuple[float, float]  # (max_worp_ppg, max_hppg)
    flex: tuple[float, float]  # RB/WR/TE shared flex pool
    qb_replacement_ppg: float | None = None


def _ppg_anchor_group(pos: str) -> str:
    return "qb" if pos == "QB" else "flex"


def compute_per_game_anchor_maxes(
    per_game_by_id: dict[str, dict[str, float]],
    pos_by_id: dict[str, str],
) -> PerGameAnchorMaxes:
    """Fixed per-game ceilings: QBs vs flex-eligible skill positions."""
    maxes = {
        "qb": [0.0, 0.0],
        "flex": [0.0, 0.0],
    }
    for player_id, metrics in per_game_by_id.items():
        group = _ppg_anchor_group((pos_by_id.get(player_id) or "").upper())
        if metrics.get("worp_ppg"):
            maxes[group][0] = max(maxes[group][0], float(metrics["worp_ppg"]))
        if metrics.get("healthy_ppg"):
            maxes[group][1] = max(maxes[group][1], float(metrics["healthy_ppg"]))

    def _pair(group: str) -> tuple[float, float]:
        worp, hppg = maxes[group]
        return (worp or 1.0, hppg or 1.0)

    return PerGameAnchorMaxes(qb=_pair("qb"), flex=_pair("flex"))


def compute_reference_anchors(
    players: list[tuple[str, PlayerValue]],
    effective_worp: Callable[[str, PlayerValue], tuple[float | None, bool]],
) -> DynastyReferenceAnchors:
    trade_vals = [player.trade_value for _, player in players]
    effective: list[float] = []
    for player_id, player in players:
        eff, _ = effective_worp(player_id, player)
        if eff is not None:
            effective.append(max(eff, 0.0))
    return DynastyReferenceAnchors(
        max_tv=max(trade_vals) if trade_vals else 1.0,
        max_worp=max(effective) if effective else 1.0,
    )


def _per_game_production_norm(
    metrics: dict[str, float],
    *,
    max_worp_ppg: float,
    max_hppg: float,
    position: str | None = None,
    replacement_ppg: float | None = None,
) -> float:
    """0–1: healthy-week W/g + HPPG vs pool, lightly discounted for low availability."""
    worp_ppg = metrics.get("worp_ppg")
    hppg = metrics.get("healthy_ppg")
    has_worp = worp_ppg is not None and float(worp_ppg) > 0
    has_hppg = hppg is not None and float(hppg) > 0
    if not has_worp and not has_hppg:
        return 0.0
    w_norm = (float(worp_ppg) / max_worp_ppg) if has_worp and max_worp_ppg > 0 else 0.0
    h_norm = (float(hppg) / max_hppg) if has_hppg and max_hppg > 0 else 0.0
    # QBs: blend peak-relative and replacement-relative so ~12 PPG isn't "half of Allen"
    # but also isn't zeroed out entirely in superflex (replacement ~16 PPG).
    if (position or "").upper() == "QB" and has_hppg and replacement_ppg is not None:
        span = max_hppg - replacement_ppg
        vor_norm = max(0.0, min(1.0, (float(hppg) - replacement_ppg) / span)) if span > 0 else 0.0
        peak_norm = (float(hppg) / max_hppg) if max_hppg > 0 else 0.0
        h_norm = 0.40 * peak_norm + 0.60 * vor_norm
    # Ignore noise-level W/g — a tiny positive W/g must not dilute a strong HPPG signal.
    # Absolute floor (0.02) plus 10% of HPPG norm so deep-league replacement noise
    # (e.g. 0.006 W/g with 10.5 HPPG) is treated like zero.
    worp_floor = 0.02
    if has_hppg:
        worp_floor = max(worp_floor, 0.10 * h_norm)
    has_material_worp = has_worp and w_norm >= worp_floor
    if has_material_worp and has_hppg:
        raw = 0.55 * w_norm + 0.45 * h_norm
    elif has_material_worp:
        raw = w_norm
    elif has_hppg:
        raw = h_norm
    else:
        raw = 0.0
    avail = float(metrics.get("availability", 1.0))
    durability = 0.82 + 0.18 * max(0.0, min(1.0, avail))
    return min(1.0, raw * durability)


def _pool_per_game_norms(
    per_game_by_id: dict[str, dict[str, float]],
    *,
    pos_by_id: dict[str, str] | None = None,
    anchor_maxes: PerGameAnchorMaxes | None = None,
    max_worp_ppg: float | None = None,
    max_hppg: float | None = None,
) -> dict[str, float]:
    if anchor_maxes is None and (max_worp_ppg is None or max_hppg is None):
        max_worp_ppg = 0.0
        max_hppg = 0.0
        for metrics in per_game_by_id.values():
            if metrics.get("worp_ppg"):
                max_worp_ppg = max(max_worp_ppg, float(metrics["worp_ppg"]))
            if metrics.get("healthy_ppg"):
                max_hppg = max(max_hppg, float(metrics["healthy_ppg"]))
        max_worp_ppg = max_worp_ppg or 1.0
        max_hppg = max_hppg or 1.0

    norms: dict[str, float] = {}
    for player_id, metrics in per_game_by_id.items():
        if anchor_maxes is not None:
            group = _ppg_anchor_group((pos_by_id or {}).get(player_id, "").upper())
            max_worp_ppg, max_hppg = anchor_maxes.qb if group == "qb" else anchor_maxes.flex
            replacement_ppg = (
                anchor_maxes.qb_replacement_ppg if group == "qb" else None
            )
        else:
            replacement_ppg = None
        norms[player_id] = _per_game_production_norm(
            metrics,
            max_worp_ppg=max_worp_ppg or 1.0,
            max_hppg=max_hppg or 1.0,
            position=(pos_by_id or {}).get(player_id),
            replacement_ppg=replacement_ppg,
        )
    return norms


def _smoothstep(edge0: float, edge1: float, x: float) -> float:
    """0→1 smooth ramp between edge0 and edge1 (Hermite ease)."""
    if edge1 <= edge0:
        return 1.0 if x >= edge1 else 0.0
    t = max(0.0, min(1.0, (x - edge0) / (edge1 - edge0)))
    return t * t * (3.0 - 2.0 * t)


def _blend_toward_one(low_factor: float, prove_out: float) -> float:
    """Interpolate dampening factor toward 1.0 as production proves out."""
    return low_factor * (1.0 - prove_out) + prove_out


def _trajectory_signal(
    tv_norm: float,
    production_norm: float,
    years_exp: int | None,
    *,
    pg_norm: float | None = None,
) -> float:
    """
    Market (TV) ahead of production on young players — development bet.
    Production proof ramps in smoothly (~0.28–0.52 per-game) instead of a hard cliff.
    """
    if years_exp is None or years_exp > 2:
        return 0.0
    gap = max(0.0, min(1.0, (tv_norm - production_norm) * 1.4))
    pg_weight = _smoothstep(0.28, 0.52, pg_norm if pg_norm is not None else 0.0)
    return gap * pg_weight


def _ovr_tv_norm(pos: str, tv_norm: float, pg_norm: float | None) -> float:
    """Dampen market TV in OVR when production hasn't backed up the price."""
    if pg_norm is None:
        return tv_norm
    pos_u = (pos or "").upper()
    if pos_u == "QB":
        prove_out = _smoothstep(0.22, 0.34, pg_norm)
        low_factor = 0.65 + pg_norm * 1.167
        return tv_norm * _blend_toward_one(low_factor, prove_out)
    prove_out = _smoothstep(0.30, 0.48, pg_norm)
    low_factor = 0.62 + pg_norm * 0.90
    return tv_norm * _blend_toward_one(low_factor, prove_out)


def _ovr_age_norm(pos: str, age_norm: float, pg_norm: float | None) -> float:
    """Youth premium requires some on-field production (smooth ramp)."""
    if pg_norm is None:
        return age_norm
    pos_u = (pos or "").upper()
    if pos_u == "QB":
        prove_out = _smoothstep(0.20, 0.32, pg_norm)
        low_factor = 0.70 + pg_norm * 1.07
        return age_norm * _blend_toward_one(low_factor, prove_out)
    prove_out = _smoothstep(0.28, 0.45, pg_norm)
    low_factor = 0.78 + pg_norm * 0.70
    return age_norm * _blend_toward_one(low_factor, prove_out)


class DynastyScorer:
    def __init__(
        self,
        weights: DynastyWeights | None = None,
        rating_curve: DynastyRatingCurve | None = None,
    ) -> None:
        self.weights = weights or DynastyWeights()
        self.rating_curve = rating_curve or DynastyRatingCurve()

    def score_pool(
        self,
        players: list[tuple[str, PlayerValue]],
        *,
        age_by_id: dict[str, int | None],
        years_exp_by_id: dict[str, int | None],
        effective_worp: Callable[[str, PlayerValue], tuple[float | None, bool]],
        reference: DynastyReferenceAnchors | None = None,
        rating_bounds: tuple[float, float] | None = None,
        per_game_by_id: dict[str, dict[str, float]] | None = None,
        per_game_max: PerGameAnchorMaxes | tuple[float, float] | None = None,
        pos_by_id: dict[str, str] | None = None,
    ) -> dict[str, dict[str, Any]]:
        if not players:
            return {}

        if reference is not None:
            max_tv = reference.max_tv
            max_worp = reference.max_worp
        else:
            trade_vals = [p.trade_value for _, p in players]
            max_tv = max(trade_vals) if trade_vals else 1.0
            effective_vals: list[float] = []
            for player_id, player in players:
                eff, _ = effective_worp(player_id, player)
                if eff is not None:
                    effective_vals.append(max(eff, 0.0))
            max_worp = max(effective_vals) if effective_vals else 1.0

        effective: dict[str, float] = {}
        for player_id, player in players:
            eff, _ = effective_worp(player_id, player)
            if eff is not None:
                effective[player_id] = max(eff, 0.0)

        per_game_norms: dict[str, float] = {}
        if per_game_by_id:
            if isinstance(per_game_max, PerGameAnchorMaxes):
                per_game_norms = _pool_per_game_norms(
                    per_game_by_id,
                    pos_by_id=pos_by_id,
                    anchor_maxes=per_game_max,
                )
            else:
                per_game_norms = _pool_per_game_norms(
                    per_game_by_id,
                    max_worp_ppg=per_game_max[0] if per_game_max else None,
                    max_hppg=per_game_max[1] if per_game_max else None,
                )
        tilt = max(0.0, min(1.0, self.rating_curve.per_game_tilt))
        w = self.weights
        results: dict[str, dict[str, Any]] = {}
        for player_id, player in players:
            tv_norm = player.trade_value / max_tv if max_tv else 0.0
            eff = effective.get(player_id)
            if eff is not None and max_worp:
                season_worp_norm = eff / max_worp
            else:
                season_worp_norm = tv_norm * 0.85
            pg_norm = per_game_norms.get(player_id)
            production_norm = season_worp_norm
            if pg_norm is not None and pg_norm > 0:
                production_norm = (1.0 - tilt) * season_worp_norm + tilt * pg_norm
            upside_norm = min(player.upside, 1.0)
            age = age_by_id.get(player_id)
            years_exp = years_exp_by_id.get(player_id)
            tv_norm_adj = _ovr_tv_norm(player.pos, tv_norm, pg_norm)
            age_norm = _ovr_age_norm(player.pos, _age_premium(player.pos, age), pg_norm)
            traj_norm = _trajectory_signal(
                tv_norm_adj, production_norm, years_exp, pg_norm=pg_norm
            )

            composite = (
                w.tv * tv_norm_adj
                + w.worp * production_norm
                + w.upside * upside_norm
                + w.age * age_norm
                + w.trajectory * traj_norm
            )
            if rating_bounds is not None:
                rating = curved_composite_to_rating(
                    composite,
                    raw_min=rating_bounds[0],
                    raw_max=rating_bounds[1],
                    exponent=self.rating_curve.exponent,
                )
            else:
                rating = composite_to_rating(composite)
            is_rookie = years_exp == 0 if years_exp is not None else player.worp is None
            results[player_id] = {
                "dynasty_score": composite,
                "dynasty_rating": rating,
                "dynasty_rookie": is_rookie,
                "dynasty_components": {
                    "tv": round(tv_norm, 3),
                    "production": round(production_norm, 3),
                    "worp": round(production_norm, 3),
                    "per_game": round(pg_norm, 3) if pg_norm is not None else None,
                    "production_detail": {
                        "season_worp": round(season_worp_norm, 3),
                        "per_game": round(pg_norm, 3) if pg_norm is not None else None,
                        "tilt": round(tilt, 3),
                    },
                    "upside": round(upside_norm, 3),
                    "age": round(age_norm, 3),
                    "trajectory": round(traj_norm, 3),
                },
                "age": age,
            }
        return results
