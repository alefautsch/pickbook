from __future__ import annotations

from collections import defaultdict

from dynasty_draft.war_data import PlayerValue, WarData

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


class WorpProjector:
    def __init__(self, war: WarData) -> None:
        self._slopes = _tv_to_worp_slopes(war)

    def effective_worp(
        self,
        player: PlayerValue,
        *,
        years_exp: int | None,
    ) -> tuple[float | None, bool]:
        """
        Return (worp_for_scoring, is_projected).

        Dynasty-daddy WORP is backward-looking. For rookies and thin-sample
        sophomores (negative WORP, low PORP), blend trade value, PORP, and spike upside.
        """
        if years_exp is None:
            years_exp = 2 if player.worp is not None else 0

        slope = self._slopes.get(player.pos, _DEFAULT_SLOPE)
        tv_worp = player.trade_value * slope
        upside = player.upside

        if years_exp >= 2:
            return player.worp, False

        if years_exp == 0:
            projected = max(tv_worp * 0.85, upside * 0.4)
            return projected, True

        # Second-year / limited sample
        historical = player.worp
        porp = player.porp or 0.0
        if historical is not None and historical >= 0.2 and porp >= 20:
            return historical, False

        porp_bump = porp / 100.0
        upside_bump = upside * 0.35
        hist_part = max(historical or 0.0, 0.0) * 0.15
        projected = hist_part + 0.55 * tv_worp + 0.30 * max(porp_bump, upside_bump)
        return projected, True
