from __future__ import annotations

from collections.abc import Callable

from dynasty_draft.external_adp import AdpStore
from dynasty_draft.war_data import PlayerValue, WarData, normalize_name


class AdpIndex:
    """Draft slot consensus with optional external ADP and trade-value fallback."""

    def __init__(
        self,
        war: WarData,
        tv_getter: Callable[[PlayerValue], float] | None = None,
        external: AdpStore | None = None,
    ) -> None:
        getter = tv_getter or (lambda player: player.trade_value)
        ranked = sorted(war.players, key=getter, reverse=True)
        self._tv_by_name: dict[str, int] = {}
        for index, player in enumerate(ranked, start=1):
            key = normalize_name(player.name)
            if key not in self._tv_by_name:
                self._tv_by_name[key] = index
        self.external = external
        self.source = external.source if external else "trade_value"
        self.source_label = external.label if external else "Trade value rank"
        external_max = external.max_pick if external else 0
        tv_max = max(self._tv_by_name.values(), default=0)
        self.max_pick = max(external_max, tv_max)

    def pick_no(self, name: str) -> int | None:
        if self.external is not None:
            external_pick = self.external.lookup(name)
            if external_pick is not None:
                return external_pick
        return self._tv_by_name.get(normalize_name(name))

    def delta(self, name: str, reference_pick: int) -> int | None:
        """reference_pick - adp. Positive = fell past ADP (value); negative = reach."""
        adp = self.pick_no(name)
        if adp is None:
            return None
        return reference_pick - adp

    def adp_class(self, delta: int | None) -> str:
        if delta is None:
            return "adp-unknown"
        if delta >= 6:
            return "adp-steal"
        if delta <= -6:
            return "adp-reach"
        return "adp-fair"

    def adp_norm(self, name: str, *, fallback_tv: float = 0.0, max_tv: float = 0.0) -> float:
        """Higher = goes earlier. Uses inverse ADP rank when known."""
        adp_pick = self.pick_no(name)
        if adp_pick is not None and self.max_pick > 1:
            return max(0.0, 1.0 - (adp_pick - 1) / (self.max_pick - 1))
        if max_tv > 0 and fallback_tv > 0:
            return fallback_tv / max_tv
        return 0.0
