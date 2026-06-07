from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

from dynasty_draft.war_data import PlayerValue, WarData
from dynasty_draft.worp_blend import WorpBlend

if TYPE_CHECKING:
    from dynasty_draft.healthy_ppg import HealthyPpgStore
    from dynasty_draft.projections import SleeperProjectionStore

# Calibrated from dynasty-daddy export: WORP per trade-value point for established producers.
_DEFAULT_SLOPE = 0.00005


def _tv_to_worp_slopes(war: WarData) -> dict[str, float]:
    by_pos: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for player in war.players:
        if player.worp is None or player.worp < 0.2:
            continue
        by_pos[player.pos].append((player.trade_value, player.worp))

    slopes: dict[str, float] = {}
    for pos, pairs in by_pos.items():
        if not pairs:
            slopes[pos] = _DEFAULT_SLOPE
            continue
        pairs.sort(key=lambda row: row[0], reverse=True)
        top = pairs[: max(5, len(pairs) // 2)]
        slopes[pos] = sum(worp / tv for tv, worp in top if tv > 0) / len(top)
    for pos in ("QB", "RB", "WR", "TE"):
        slopes.setdefault(pos, _DEFAULT_SLOPE)
    return slopes


def _needs_projection(
    player: PlayerValue,
    *,
    years_exp: int | None,
) -> bool:
    if years_exp is not None and years_exp == 0:
        return True
    if player.worp is None:
        return True
    if years_exp is not None and years_exp <= 1:
        if player.worp < 0.15:
            return True
        if (player.porp or 0.0) < 20:
            return True
    return False


def _fallback_projection(
    player: PlayerValue,
    *,
    years_exp: int | None,
    slopes: dict[str, float],
) -> float:
    if years_exp is None:
        years_exp = 2 if player.worp is not None else 0

    slope = slopes.get(player.pos, _DEFAULT_SLOPE)
    tv_worp = player.trade_value * slope
    upside = player.upside

    if years_exp == 0:
        return max(tv_worp * 0.92, upside * 0.45, 0.15)

    historical = player.worp
    porp = player.porp or 0.0
    porp_bump = porp / 100.0
    upside_bump = upside * 0.35
    hist_part = max(historical or 0.0, 0.0) * 0.15
    return hist_part + 0.55 * tv_worp + 0.30 * max(porp_bump, upside_bump)


class WorpProjector:
    def __init__(
        self,
        war: WarData,
        projections: SleeperProjectionStore | None = None,
        worp_blend: WorpBlend | None = None,
        healthy_ppg_store: HealthyPpgStore | None = None,
    ) -> None:
        self._slopes = _tv_to_worp_slopes(war)
        self._projections = projections
        self._blend = worp_blend or WorpBlend()
        self._healthy_ppg = healthy_ppg_store

    def _projected_worp(
        self,
        player: PlayerValue,
        *,
        years_exp: int,
        player_id: str | None,
    ) -> float | None:
        if self._healthy_ppg is not None:
            healthy = self._healthy_ppg.lookup(player_id, name=player.name)
            if healthy is not None and healthy.worp_ppg > 0:
                return healthy.worp_ppg * 17.0
        if self._projections is not None and player_id:
            sleeper_worp = self._projections.projected_worp(player_id, player.pos)
            if sleeper_worp is not None:
                return sleeper_worp
        if _needs_projection(player, years_exp=years_exp):
            return _fallback_projection(player, years_exp=years_exp, slopes=self._slopes)
        return None

    def effective_worp(
        self,
        player: PlayerValue,
        *,
        years_exp: int | None,
        player_id: str | None = None,
    ) -> tuple[float | None, bool]:
        """
        Return (blended WORP for scoring, uses_projection).

        Blends dynasty-daddy historical WORP with Sleeper VOR → WORP (or TV imputation).
        Weight on historical rises with years of experience; rookies lean on projection.
        """
        if years_exp is None:
            years_exp = 2 if player.worp is not None else 0

        historical = player.worp
        thin_sample = _needs_projection(player, years_exp=years_exp)
        projected = self._projected_worp(player, years_exp=years_exp, player_id=player_id)

        alpha = self._blend.historical_alpha(
            years_exp=years_exp,
            thin_sample=thin_sample,
            has_historical=historical is not None,
            has_projected=projected is not None,
        )
        blended = self._blend.blend(historical, projected, alpha)
        uses_projection = self._blend.uses_projection(alpha, has_projected=projected is not None)
        return blended, uses_projection
