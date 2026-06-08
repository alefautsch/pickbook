"""In-season draft pick trade values — static chart aligned to player TV scale."""

from __future__ import annotations

from typing import Literal

SlotTier = Literal["early", "mid", "late"]

# Round × tier base TV for picks in the next draft season (year+1).
# Calibrated to dynasty-daddy / KTC player scale (~8500 ≈ low-end elite asset).
_BASE_TV: dict[int, dict[SlotTier, float]] = {
    1: {"early": 8500, "mid": 6200, "late": 4200},
    2: {"early": 3200, "mid": 2400, "late": 1700},
    3: {"early": 1500, "mid": 1100, "late": 800},
    4: {"early": 700, "mid": 500, "late": 350},
}

# Discount by seasons until the pick (1 = next rookie draft).
_SEASON_DISCOUNT: dict[int, float] = {
    1: 1.0,
    2: 0.82,
    3: 0.68,
    4: 0.55,
}


def infer_slot_tier(
    original_rank: int | None,
    *,
    league_size: int,
) -> SlotTier:
    """Map original owner's dynasty rank to pick slot quality (worst team → early)."""
    if original_rank is None or league_size <= 0:
        return "mid"
    # Rank 1 = best team → late pick; rank N = worst → early pick.
    pct = (original_rank - 1) / max(league_size - 1, 1)
    if pct >= 0.67:
        return "early"
    if pct <= 0.33:
        return "late"
    return "mid"


def seasons_until(current_season: str | int, pick_season: str | int) -> int:
    return max(1, int(pick_season) - int(current_season))


def value_pick(
    *,
    round_no: int,
    slot_tier: SlotTier,
    seasons_out: int,
) -> float:
    """Trade value for a single draft pick."""
    round_vals = _BASE_TV.get(min(round_no, 4), _BASE_TV[4])
    base = round_vals.get(slot_tier, round_vals["mid"])
    discount = _SEASON_DISCOUNT.get(min(seasons_out, 4), 0.45)
    return round(base * discount, 1)


def pick_label(*, season: str, round_no: int, slot_tier: SlotTier) -> str:
    tier_tag = {"early": " (early)", "mid": "", "late": " (late)"}[slot_tier]
    ordinals = {1: "1st", 2: "2nd", 3: "3rd", 4: "4th"}
    rnd = ordinals.get(round_no, f"{round_no}th")
    return f"{season} {rnd}{tier_tag}"
