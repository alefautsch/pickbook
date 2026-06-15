"""Current-season R1 pick floors — lock premium + Dynasty Dealer market anchor."""

from __future__ import annotations

from typing import Any

from backend.services.rookie_consensus import ROOKIE_PICK_LOCKS
from dynasty_draft.dynasty_dealer import DynastyDealerStore
from dynasty_draft.ktc_values import KtcStore

LOCK_DISCOUNT = 0.95
PREMIUM_R1_MAX_SLOT = 4


def resolve_prospect_tv(
    name: str,
    *,
    ktc_store: KtcStore | None,
    dd_store: DynastyDealerStore | None,
) -> float | None:
    """Dynamic prospect TV from KTC and Dynasty Dealer (whichever is higher)."""
    values: list[float] = []
    if ktc_store is not None:
        ktc_val = ktc_store.lookup(name)
        if ktc_val is not None and ktc_val > 0:
            values.append(float(ktc_val))
    if dd_store is not None:
        dd_val = dd_store.lookup_player(name)
        if dd_val is not None and dd_val > 0:
            values.append(float(dd_val))
    if not values:
        return None
    return max(values)


def apply_market_pick_adjustments(
    base_tv: float,
    *,
    pick_season: str,
    current_season: str,
    round_no: int,
    slot_in_round: int | None,
    ktc_store: KtcStore | None,
    dd_store: DynastyDealerStore | None,
) -> tuple[float, dict[str, Any] | None]:
    """Option C blend for current-season round-1 known slots."""
    if str(pick_season) != str(current_season) or int(round_no) != 1:
        return round(base_tv, 1), None
    if slot_in_round is None:
        return round(base_tv, 1), None

    slot = int(slot_in_round)
    dd_slot = dd_store.lookup_slot(pick_season, round_no, slot) if dd_store else None
    locked_name = ROOKIE_PICK_LOCKS.get(slot)

    if locked_name:
        floors = [base_tv]
        meta: dict[str, Any] = {
            "valuation_source": "lock_blend",
            "locked_prospect": locked_name,
            "base_tv": base_tv,
        }
        prospect_tv = resolve_prospect_tv(
            locked_name,
            ktc_store=ktc_store,
            dd_store=dd_store,
        )
        if prospect_tv is not None:
            discounted = round(prospect_tv * LOCK_DISCOUNT, 1)
            floors.append(discounted)
            meta["prospect_tv"] = prospect_tv
            meta["prospect_floor"] = discounted
        if dd_slot is not None:
            floors.append(dd_slot)
            meta["dynasty_dealer_slot_tv"] = dd_slot
        adjusted = round(max(floors), 1)
        if adjusted > base_tv:
            meta["trade_value"] = adjusted
            return adjusted, meta
        return round(base_tv, 1), None

    if 2 <= slot <= PREMIUM_R1_MAX_SLOT and dd_slot is not None:
        adjusted = round(max(base_tv, dd_slot), 1)
        if adjusted > base_tv:
            return adjusted, {
                "valuation_source": "dynasty_dealer_slot",
                "base_tv": base_tv,
                "dynasty_dealer_slot_tv": dd_slot,
                "trade_value": adjusted,
            }

    return round(base_tv, 1), None
