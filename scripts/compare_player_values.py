#!/usr/bin/env python3
"""Compare blended player TV vs individual market sources."""

from __future__ import annotations

import argparse

from dynasty_draft.dynasty_dealer import ATTRIBUTION_LABEL, ATTRIBUTION_URL, DynastyDealerStore
from dynasty_draft.ktc_values import KtcStore
from dynasty_draft.trade_value_blend import TradeValueBlend


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("names", nargs="+", help="Player names to compare")
    parser.add_argument("--superflex", action="store_true", default=True)
    parser.add_argument("--dd-tv", type=float, default=None, help="Dynasty Daddy TV override for demo")
    args = parser.parse_args()

    ktc = KtcStore.load(superflex=args.superflex)
    dealer = DynastyDealerStore.load(superflex=args.superflex)
    blend = TradeValueBlend.from_config(
        {"dynasty_dealer": {"enabled": True}},
        ktc_available=True,
    )

    print(f"Player TV comparison ({'SF' if args.superflex else '1QB'})")
    print(f"Blend weights: dealer={blend.dealer_weight}, dd={blend.dd_weight}, ktc={blend.ktc_weight}")
    print(f"Market anchor: {ATTRIBUTION_LABEL} ({ATTRIBUTION_URL})")
    print()
    print(f"{'Player':<22} {'DD':>8} {'KTC':>8} {'Dealer':>8} {'Blended':>8}")
    print("-" * 58)

    for name in args.names:
        ktc_tv = ktc.lookup(name)
        dealer_tv = dealer.lookup_player(name) if dealer else None
        dd_tv = args.dd_tv
        if dd_tv is None:
            dd_tv = float(ktc_tv or dealer_tv or 0)
        blended = blend.blend(dd_tv, ktc_tv, dealer=dealer_tv)
        print(
            f"{name:<22} "
            f"{dd_tv:>8.0f} "
            f"{(ktc_tv or 0):>8} "
            f"{(dealer_tv or 0):>8.0f} "
            f"{(blended or 0):>8.0f}"
        )


if __name__ == "__main__":
    main()
