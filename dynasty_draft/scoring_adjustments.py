"""League-scoring adjustments shared across sync and UI."""

from __future__ import annotations


def tep_adjusted_trade_value(
    trade_value: float,
    *,
    position: str | None,
    te_premium: float,
    hppg: float | None,
    receptions_per_game: float | None,
) -> float:
    """Scale market TV for TEs when league scoring adds reception premium."""
    if (
        position != "TE"
        or te_premium <= 0
        or not trade_value
        or hppg is None
        or not receptions_per_game
    ):
        return trade_value
    base_hppg = float(hppg) - te_premium * float(receptions_per_game)
    if base_hppg <= 0:
        return trade_value
    return round(trade_value * (float(hppg) / base_hppg), 2)
