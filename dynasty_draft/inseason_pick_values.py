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


def slot_in_round(
    original_rank: int | None,
    *,
    league_size: int,
    startup_draft_slot: int | None = None,
) -> int | None:
    """Estimate pick number within the round (1.01 = slot 1).

    Pre-season startup leagues: use startup draft order (Sleeper UI source).
    In-season: use dynasty rank (worst team → 1.01).
    """
    if startup_draft_slot is not None and league_size > 0:
        return league_size + 1 - startup_draft_slot
    if original_rank is None or league_size <= 0:
        return None
    return league_size - original_rank + 1


def infer_slot_tier(
    original_rank: int | None,
    *,
    league_size: int,
    startup_draft_slot: int | None = None,
) -> SlotTier:
    """Map pick slot quality (worst / late startup slot → early pick)."""
    if startup_draft_slot is not None and league_size > 0:
        pct = (startup_draft_slot - 1) / max(league_size - 1, 1)
        if pct >= 0.67:
            return "early"
        if pct <= 0.33:
            return "late"
        return "mid"
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
    return max(0, int(pick_season) - int(current_season))


def value_pick(
    *,
    round_no: int,
    slot_tier: SlotTier,
    seasons_out: int,
    slot_in_round_no: int | None = None,
    is_own_slot: bool = False,
    owner_contender_tier: str | None = None,
    slot_certainty: str = "known",
) -> float:
    """Trade value for a single draft pick."""
    round_vals = _BASE_TV.get(min(round_no, 4), _BASE_TV[4])
    tier = slot_tier
    slot_no = slot_in_round_no

    # Future own picks: slot not locked in — use mid band, no .01 label precision.
    if slot_certainty == "projected" or (is_own_slot and seasons_out > 0):
        tier = "mid"
        slot_no = None

    base = round_vals.get(tier, round_vals["mid"])
    discount = _SEASON_DISCOUNT.get(min(seasons_out, 4), 0.45)
    multiplier = 1.0
    if round_no == 1 and slot_no is not None and tier == "early":
        multiplier = _TOP_SLOT_PREMIUM.get(slot_no, 1.0)
    # Contenders' own future picks: slight bump (still liquid win-now currency).
    if is_own_slot and seasons_out > 0 and owner_contender_tier == "contender":
        multiplier *= 1.06
    return round(base * discount * multiplier, 1)


def pick_label(
    *,
    season: str,
    round_no: int,
    slot_tier: SlotTier,
    slot_in_round_no: int | None = None,
    slot_certainty: str = "known",
) -> str:
    if slot_in_round_no is not None and slot_certainty == "known":
        return f"{season} {round_no}.{slot_in_round_no:02d}"
    if slot_certainty == "projected" or slot_in_round_no is None:
        ordinals = {1: "1st", 2: "2nd", 3: "3rd", 4: "4th"}
        rnd = ordinals.get(round_no, f"{round_no}th")
        return f"{season} {rnd} (proj)"
    tier_tag = {"early": " (early)", "mid": "", "late": " (late)"}[slot_tier]
    ordinals = {1: "1st", 2: "2nd", 3: "3rd", 4: "4th"}
    rnd = ordinals.get(round_no, f"{round_no}th")
    return f"{season} {rnd}{tier_tag}"


def pick_slot_certainty(
    *,
    is_own_slot: bool,
    seasons_out: int,
) -> str:
    if is_own_slot and seasons_out > 0:
        return "projected"
    return "known"
