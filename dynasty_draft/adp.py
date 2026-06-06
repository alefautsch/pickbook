from __future__ import annotations

from dynasty_draft.war_data import WarData, normalize_name


class AdpIndex:
    """Consensus ADP from dynasty-daddy trade value (higher TV = earlier pick)."""

    def __init__(self, war: WarData) -> None:
        ranked = sorted(war.players, key=lambda p: p.trade_value, reverse=True)
        self._by_name: dict[str, int] = {}
        for index, player in enumerate(ranked, start=1):
            key = normalize_name(player.name)
            if key not in self._by_name:
                self._by_name[key] = index

    def pick_no(self, name: str) -> int | None:
        return self._by_name.get(normalize_name(name))

    def delta(self, name: str, reference_pick: int) -> int | None:
        """Positive = player typically goes later (value at reference pick)."""
        adp = self.pick_no(name)
        if adp is None:
            return None
        return adp - reference_pick

    def adp_class(self, delta: int | None) -> str:
        if delta is None:
            return "adp-unknown"
        if delta >= 6:
            return "adp-steal"
        if delta <= -6:
            return "adp-reach"
        return "adp-fair"
