from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from dynasty_draft.war_data import PlayerValue

# Ideal peak ages for dynasty value (years before decline).
_PEAK_AGE = {"QB": 29, "RB": 25, "WR": 27, "TE": 26}

RATING_MIN = 50
RATING_MAX = 99


def composite_to_rating(composite: float) -> int:
    """Map 0–1 composite to Madden-style 50–99 rating."""
    raw = round(RATING_MIN + composite * (RATING_MAX - RATING_MIN))
    return max(RATING_MIN, min(RATING_MAX, raw))


DEFAULT_DYNASTY_WEIGHTS: dict[str, float] = {
    "tv": 0.45,
    "worp": 0.25,
    "upside": 0.15,
    "age": 0.10,
    "trajectory": 0.05,
}


@dataclass(frozen=True)
class DynastyWeights:
    tv: float = 0.45
    worp: float = 0.25
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


def _trajectory_signal(tv_norm: float, worp_norm: float, years_exp: int | None) -> float:
    """
    Market (TV) ahead of production (WORP) on young players — development bet.
    Loveland pattern: high dynasty capital, low historical WORP.
    """
    if years_exp is None or years_exp > 2:
        return 0.0
    gap = tv_norm - worp_norm
    return max(0.0, min(1.0, gap * 1.4))


class DynastyScorer:
    def __init__(self, weights: DynastyWeights | None = None) -> None:
        self.weights = weights or DynastyWeights()

    def score_pool(
        self,
        players: list[tuple[str, PlayerValue]],
        *,
        age_by_id: dict[str, int | None],
        years_exp_by_id: dict[str, int | None],
        effective_worp: Callable[[str, PlayerValue], tuple[float | None, bool]],
    ) -> dict[str, dict[str, Any]]:
        if not players:
            return {}

        trade_vals = [p.trade_value for _, p in players]
        max_tv = max(trade_vals) if trade_vals else 1.0

        effective: dict[str, float] = {}
        for player_id, player in players:
            eff, _ = effective_worp(player_id, player)
            if eff is not None:
                effective[player_id] = max(eff, 0.0)
        max_worp = max(effective.values()) if effective else 1.0

        w = self.weights
        results: dict[str, dict[str, Any]] = {}
        for player_id, player in players:
            tv_norm = player.trade_value / max_tv if max_tv else 0.0
            eff = effective.get(player_id)
            if eff is not None and max_worp:
                worp_norm = eff / max_worp
            else:
                worp_norm = tv_norm * 0.85
            upside_norm = min(player.upside, 1.0)
            age = age_by_id.get(player_id)
            years_exp = years_exp_by_id.get(player_id)
            age_norm = _age_premium(player.pos, age)
            traj_norm = _trajectory_signal(tv_norm, worp_norm, years_exp)

            composite = (
                w.tv * tv_norm
                + w.worp * worp_norm
                + w.upside * upside_norm
                + w.age * age_norm
                + w.trajectory * traj_norm
            )
            rating = composite_to_rating(composite)
            results[player_id] = {
                "dynasty_score": composite,
                "dynasty_rating": rating,
                "dynasty_components": {
                    "tv": round(tv_norm, 3),
                    "worp": round(worp_norm, 3),
                    "upside": round(upside_norm, 3),
                    "age": round(age_norm, 3),
                    "trajectory": round(traj_norm, 3),
                },
                "age": age,
            }
        return results
