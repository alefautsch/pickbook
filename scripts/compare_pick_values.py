#!/usr/bin/env python3
"""Compare our pick TV vs KTC slot curve and Dynasty Dealer market anchor."""

from __future__ import annotations

import argparse

from backend.services.pick_valuation import apply_market_pick_adjustments, resolve_prospect_tv
from backend.services.rookie_consensus import ROOKIE_PICK_LOCKS
from dynasty_draft.dynasty_dealer import ATTRIBUTION_LABEL, ATTRIBUTION_URL, DynastyDealerStore
from dynasty_draft.inseason_pick_values import value_pick
from dynasty_draft.ktc_values import KtcStore


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--season", default="2026")
    parser.add_argument("--superflex", action="store_true", default=True)
    parser.add_argument("--slots", default="1,2,3,4", help="Comma-separated R1 slots to compare")
    args = parser.parse_args()

    ktc = KtcStore.load(superflex=args.superflex)
    dd = DynastyDealerStore.load(superflex=args.superflex)
    if dd is None:
        print("Dynasty Dealer unavailable — using KTC only")

    def ktc_lookup(season: str, round_no: int, slot_tier: str) -> float | None:
        val = ktc.lookup_pick(season, round_no, slot_tier)
        return float(val) if val is not None else None

    def ktc_slot_lookup(season: str, round_no: int, slot_in_round: int) -> float | None:
        val = ktc.slot_value(season, round_no, slot_in_round, use_rookie_mode=True)
        return float(val) if val is not None else None

    print(f"Pick TV comparison — {args.season} round 1 ({'SF' if args.superflex else '1QB'})")
    print(f"Market anchor: {ATTRIBUTION_LABEL} ({ATTRIBUTION_URL})")
    print()
    print(f"{'Slot':>6} {'KTC base':>10} {'Adjusted':>10} {'DD slot':>10} {'Lock':>18}")
    print("-" * 62)

    for raw in args.slots.split(","):
        slot = int(raw.strip())
        base = value_pick(
            round_no=1,
            slot_tier="early",
            seasons_out=0,
            slot_in_round_no=slot,
            pick_season=args.season,
            ktc_lookup=ktc_lookup,
            ktc_slot_lookup=ktc_slot_lookup,
            league_size=12,
        )
        adjusted, meta = apply_market_pick_adjustments(
            base,
            pick_season=args.season,
            current_season=args.season,
            round_no=1,
            slot_in_round=slot,
            ktc_store=ktc,
            dd_store=dd,
        )
        dd_slot = dd.lookup_slot(args.season, 1, slot) if dd else None
        lock = ROOKIE_PICK_LOCKS.get(slot, "")
        if lock and ktc:
            prospect = resolve_prospect_tv(lock, ktc_store=ktc, dd_store=dd)
            lock = f"{lock} ({prospect:.0f})" if prospect else lock
        print(
            f"{slot:>6} {base:>10.1f} {adjusted:>10.1f} "
            f"{dd_slot or 0:>10.1f} {lock:>18}"
        )
        if meta:
            print(f"         source={meta.get('valuation_source')}")


if __name__ == "__main__":
    main()
