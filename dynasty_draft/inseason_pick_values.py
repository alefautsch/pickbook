"""In-season draft pick trade values — KTC-backed when available, static fallback."""

from __future__ import annotations

from typing import Callable, Literal

SlotTier = Literal["early", "mid", "late"]

# Fallback round×tier chart when KTC pick cache is unavailable.
# Scaled to approximate KTC crowdsourced pick values (not elite-player TV).
_BASE_TV: dict[int, dict[SlotTier, float]] = {
    1: {"early": 5600, "mid": 4550, "late": 3900},
    2: {"early": 3300, "mid": 2500, "late": 1800},
    3: {"early": 1500, "mid": 1100, "late": 800},
    4: {"early": 700, "mid": 500, "late": 350},
}

# Discount by seasons until the pick (0 = current draft year, 1 = next rookie draft).
# Not applied when using KTC per-season pick values.
_SEASON_DISCOUNT: dict[int, float] = {
    0: 1.0,
    1: 1.0,
    2: 0.82,
    3: 0.68,
    4: 0.55,
}

# Small 1.01 premium within early tier when using static fallback only.
_TOP_SLOT_PREMIUM: dict[int, float] = {
    1: 1.08,
    2: 1.04,
    3: 1.02,
}


def slot_in_round(
    original_rank: int | None,
    *,
    league_size: int,
    startup_draft_slot: int | None = None,
    startup_is_rookie_order: bool = False,
) -> int | None:
    """Estimate pick number within the round (1.01 = slot 1).

    Pre-season startup leagues: startup draft order is the rookie slot (1.04 = slot 4).
    Post-startup: invert startup order as a proxy until standings exist (slot 1 → late pick).
    In-season: use dynasty rank (worst team → 1.01).
    """
    if startup_draft_slot is not None and league_size > 0:
        if startup_is_rookie_order:
            return startup_draft_slot
        return league_size + 1 - startup_draft_slot
    if original_rank is None or league_size <= 0:
        return None
    return league_size - original_rank + 1


def infer_slot_tier(
    original_rank: int | None,
    *,
    league_size: int,
    startup_draft_slot: int | None = None,
    startup_is_rookie_order: bool = False,
) -> SlotTier:
    """Map pick slot quality (worst / late startup slot → early pick)."""
    if startup_draft_slot is not None and league_size > 0:
        pct = (startup_draft_slot - 1) / max(league_size - 1, 1)
        if startup_is_rookie_order:
            if pct <= 0.33:
                return "early"
            if pct >= 0.67:
                return "late"
            return "mid"
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


def _early_slots_in_round(league_size: int) -> int:
    return max(league_size // 3, 1)


def _slot_adjust_within_early_tier(
    tier_value: float,
    *,
    slot_in_round_no: int | None,
    mid_tier_value: float | None,
    league_size: int,
) -> float:
    """Spread early-tier picks between KTC early and mid (1.01 high, 1.04 low in 12-team)."""
    if slot_in_round_no is None:
        return tier_value
    early_slots = _early_slots_in_round(league_size)
    if slot_in_round_no > early_slots:
        return tier_value
    if early_slots <= 1 or mid_tier_value is None:
        if slot_in_round_no == 1:
            return tier_value * 1.04
        return tier_value
    pct = (slot_in_round_no - 1) / (early_slots - 1)
    return tier_value * (1.0 - pct) + mid_tier_value * pct


def value_pick(
    *,
    round_no: int,
    slot_tier: SlotTier,
    seasons_out: int,
    slot_in_round_no: int | None = None,
    is_own_slot: bool = False,
    owner_contender_tier: str | None = None,
    slot_certainty: str = "known",
    pick_season: str | int | None = None,
    ktc_lookup: Callable[[str, int, SlotTier], float | None] | None = None,
    ktc_slot_lookup: Callable[[str, int, int], float | None] | None = None,
    league_size: int = 12,
) -> float:
    """Trade value for a single draft pick."""
    tier = slot_tier
    slot_no = slot_in_round_no

    # Future own picks: slot not locked in — use mid band, no .01 label precision.
    if slot_certainty == "projected" or (is_own_slot and seasons_out > 0):
        tier = "mid"
        slot_no = None

    # Slot-specific KTC values (2026 Pick 1.03) when the slot is known.
    if (
        ktc_slot_lookup is not None
        and pick_season is not None
        and slot_no is not None
        and slot_certainty == "known"
    ):
        slot_val = ktc_slot_lookup(str(pick_season), round_no, slot_no)
        if slot_val is not None:
            value = float(slot_val)
            if is_own_slot and seasons_out > 0 and owner_contender_tier == "contender":
                value *= 1.03
            return round(value, 1)

    ktc_base: float | None = None
    if ktc_lookup is not None and pick_season is not None:
        raw = ktc_lookup(str(pick_season), round_no, tier)
        if raw is not None:
            ktc_base = float(raw)

    if ktc_base is not None:
        value = ktc_base
        if round_no == 1 and tier == "early" and slot_no is not None:
            mid_val = ktc_lookup(str(pick_season), round_no, "mid") if ktc_lookup else None
            value = _slot_adjust_within_early_tier(
                ktc_base,
                slot_in_round_no=slot_no,
                mid_tier_value=float(mid_val) if mid_val is not None else None,
                league_size=league_size,
            )
        if is_own_slot and seasons_out > 0 and owner_contender_tier == "contender":
            value *= 1.03
        return round(value, 1)

    round_vals = _BASE_TV.get(min(round_no, 4), _BASE_TV[4])
    base = round_vals.get(tier, round_vals["mid"])
    discount = _SEASON_DISCOUNT.get(min(seasons_out, 4), 0.45)
    multiplier = 1.0
    if round_no == 1 and slot_no is not None and tier == "early":
        multiplier = _TOP_SLOT_PREMIUM.get(slot_no, 1.0)
    if is_own_slot and seasons_out > 0 and owner_contender_tier == "contender":
        multiplier *= 1.03
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
    league_pre_draft: bool = False,
) -> str:
    if seasons_out > 0:
        if league_pre_draft or is_own_slot:
            return "projected"
    return "known"
