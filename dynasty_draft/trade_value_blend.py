from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from dynasty_draft.war_data import PlayerValue


@dataclass(frozen=True)
class TradeValueBlend:
    """Blend dynasty-daddy (war.csv) and KeepTradeCut into one market value."""

    dd_weight: float = 0.5
    ktc_weight: float = 0.5

    @classmethod
    def from_config(cls, config: dict[str, Any], *, ktc_available: bool) -> TradeValueBlend:
        if not ktc_available:
            return cls(dd_weight=1.0, ktc_weight=0.0)
        raw = config.get("trade_value_blend") or {}
        dd = float(raw.get("dd_weight", 0.5))
        ktc = float(raw.get("ktc_weight", 0.5))
        return cls(dd_weight=dd, ktc_weight=ktc)

    def blend(self, dd: float | None, ktc: int | None) -> float | None:
        if dd is not None and dd <= 0:
            dd = None
        if dd is None and ktc is None:
            return None
        if dd is None:
            return float(ktc)
        if ktc is None:
            return float(dd)
        total = self.dd_weight + self.ktc_weight
        if total <= 0:
            return float(dd)
        return (dd * self.dd_weight + ktc * self.ktc_weight) / total

    def apply(self, player: PlayerValue, ktc: int | None) -> PlayerValue:
        blended = self.blend(player.trade_value, ktc)
        if blended is None or abs(blended - player.trade_value) < 0.5:
            return player
        return replace(player, trade_value=blended)
