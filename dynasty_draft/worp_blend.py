from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class WorpBlend:
    """Blend historical dynasty-daddy WORP with forward-looking projected WORP."""

    historical_weight: float = 0.7
    projected_weight: float = 0.3
    auto_adjust_by_experience: bool = True

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> WorpBlend:
        raw = config.get("worp_blend") or {}
        return cls(
            historical_weight=float(raw.get("historical_weight", 0.7)),
            projected_weight=float(raw.get("projected_weight", 0.3)),
            auto_adjust_by_experience=bool(raw.get("auto_adjust_by_experience", True)),
        )

    def historical_alpha(
        self,
        *,
        years_exp: int,
        thin_sample: bool,
        has_historical: bool,
        has_projected: bool,
    ) -> float:
        """Return weight on historical WORP in [0, 1]."""
        if not has_historical:
            return 0.0
        if not has_projected:
            return 1.0

        if self.auto_adjust_by_experience:
            if years_exp <= 0:
                return 0.0
            if thin_sample:
                return 0.18
            if years_exp == 1:
                return 0.35
            if years_exp == 2:
                return 0.58
            return min(0.88, 0.66 + 0.07 * max(0, years_exp - 3))

        total = self.historical_weight + self.projected_weight
        if total <= 0:
            return 1.0
        return max(0.0, min(1.0, self.historical_weight / total))

    def blend(self, historical: float | None, projected: float | None, alpha: float) -> float | None:
        if historical is None and projected is None:
            return None
        if projected is None:
            return historical
        if historical is None:
            return projected
        return alpha * historical + (1.0 - alpha) * projected

    def uses_projection(self, alpha: float, *, has_projected: bool) -> bool:
        return has_projected and alpha < 0.95
