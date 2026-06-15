from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from dynasty_draft.war_data import PlayerValue


@dataclass(frozen=True)
class TradeValueBlend:
    """Blend Dynasty Daddy, KTC, and Dynasty Dealer into one market value."""

    dd_weight: float = 0.25
    ktc_weight: float = 0.25
    dealer_weight: float = 0.5

    @classmethod
    def from_config(cls, config: dict[str, Any], *, ktc_available: bool) -> TradeValueBlend:
        raw = config.get("trade_value_blend") or {}
        dealer_enabled = bool((config.get("dynasty_dealer") or {}).get("enabled", True))
        has_dealer_key = "dealer_weight" in raw
        dealer_weight = float(raw.get("dealer_weight", 0.5 if dealer_enabled else 0.0))
        if not dealer_enabled:
            dealer_weight = 0.0

        dd = float(raw.get("dd_weight", 0.25))
        ktc = float(raw.get("ktc_weight", 0.25))
        if dealer_weight > 0 and not has_dealer_key and abs(dd - 0.5) < 0.01 and abs(ktc - 0.5) < 0.01:
            # Legacy 50/50 DD+KTC configs → 25/25/50 with Dynasty Dealer enabled.
            dd, ktc = 0.25, 0.25

        if not ktc_available:
            # No KTC — split non-dealer weight to DD only.
            if dealer_weight >= 1.0:
                return cls(dd_weight=0.0, ktc_weight=0.0, dealer_weight=1.0)
            remaining = max(0.0, 1.0 - dealer_weight)
            return cls(dd_weight=remaining, ktc_weight=0.0, dealer_weight=dealer_weight)

        return cls(dd_weight=dd, ktc_weight=ktc, dealer_weight=dealer_weight)

    def blend(
        self,
        dd: float | None,
        ktc: int | None,
        *,
        dealer: float | None = None,
    ) -> float | None:
        if dd is not None and dd <= 0:
            dd = None
        if dealer is not None and dealer <= 0:
            dealer = None
        if ktc is not None and ktc <= 0:
            ktc = None

        parts: list[tuple[float, float]] = []
        if dealer is not None and self.dealer_weight > 0:
            parts.append((dealer, self.dealer_weight))
        if dd is not None and self.dd_weight > 0:
            parts.append((float(dd), self.dd_weight))
        if ktc is not None and self.ktc_weight > 0:
            parts.append((float(ktc), self.ktc_weight))

        if not parts:
            return None

        total_weight = sum(weight for _, weight in parts)
        if total_weight <= 0:
            return None
        return sum(value * weight for value, weight in parts) / total_weight

    def apply(
        self,
        player: PlayerValue,
        ktc: int | None,
        *,
        dealer: float | None = None,
    ) -> PlayerValue:
        blended = self.blend(player.trade_value, ktc, dealer=dealer)
        if blended is None or abs(blended - player.trade_value) < 0.5:
            return player
        return replace(player, trade_value=blended)
