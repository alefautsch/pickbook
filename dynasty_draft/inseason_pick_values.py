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

# Discount by seasons until the pick (0 = current draft year, 1 = next rookie draft).
_SEASON_DISCOUNT: dict[int, float] = {
    0: 1.0,
    1: 1.0,
    2: 0.82,
    3: 0.68,
    4: 0.55,
}

# Premium for specific round-1 slots (1.01 ≈ elite rookie QB/RB class).
_TOP_SLOT_PREMIUM: dict[int, float] = {
    1: 1.28,
    2: 1.18,
    3: 1.10,
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


def slot_in_round(
    original_rank: int | None,
    *,
    league_size: int,
) -> int | None:
    """Estimate pick number within the round (1.01 = slot 1)."""
    if original_rank is None or league_size <= 0:
        return None
    return league_size - original_rank + 1


def seasons_until(current_season: str | int, pick_season: str | int) -> int:
    return max(0, int(pick_season) - int(current_season))


def value_pick(
    *,
    round_no: int,
    slot_tier: SlotTier,
    seasons_out: int,
    slot_in_round_no: int | None = None,
) -> float:
    """Trade value for a single draft pick."""
    round_vals = _BASE_TV.get(min(round_no, 4), _BASE_TV[4])
    base = round_vals.get(slot_tier, round_vals["mid"])
    discount = _SEASON_DISCOUNT.get(min(seasons_out, 4), 0.45)
    multiplier = 1.0
    if round_no == 1 and slot_in_round_no is not None and slot_tier == "early":
        multiplier = _TOP_SLOT_PREMIUM.get(slot_in_round_no, 1.0)
    return round(base * discount * multiplier, 1)


def pick_label(
    *,
    season: str,
    round_no: int,
    slot_tier: SlotTier,
    slot_in_round_no: int | None = None,
) -> str:
    if slot_in_round_no is not None:
        return f"{season} {round_no}.{slot_in_round_no:02d}"
    tier_tag = {"early": " (early)", "mid": "", "late": " (late)"}[slot_tier]
    ordinals = {1: "1st", 2: "2nd", 3: "3rd", 4: "4th"}
    rnd = ordinals.get(round_no, f"{round_no}th")
    return f"{season} {rnd}{tier_tag}"
