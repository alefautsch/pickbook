from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from dynasty_draft.war_data import WarData


@dataclass
class DraftStrategy:
    """League-specific draft context beyond raw Sleeper state."""

    draft_phase: str = "vets"  # vets | rookies
    teams: int = 10
    startup_slot: int = 10
    rookie_draft_slot: int = 1
    rookie_draft_reversed: bool = True

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> DraftStrategy:
        raw = config.get("strategy") or {}
        return cls(
            draft_phase=str(raw.get("draft_phase", "vets")),
            teams=int(raw.get("teams", 10)),
            startup_slot=int(raw.get("startup_slot", 10)),
            rookie_draft_slot=int(raw.get("rookie_draft_slot", 1)),
            rookie_draft_reversed=bool(raw.get("rookie_draft_reversed", True)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "draft_phase": self.draft_phase,
            "teams": self.teams,
            "startup_slot": self.startup_slot,
            "rookie_draft_slot": self.rookie_draft_slot,
            "rookie_draft_reversed": self.rookie_draft_reversed,
        }

    @property
    def is_vet_draft(self) -> bool:
        return self.draft_phase.lower() == "vets"

    @property
    def is_rookie_draft(self) -> bool:
        return self.draft_phase.lower() == "rookies"

    def strategy_notes(
        self,
        war: WarData,
        *,
        tv_fn: object = None,
    ) -> list[str]:
        notes: list[str] = []
        if self.is_rookie_draft:
            notes.append(
                f"Rookie draft: you pick 1.{self.rookie_draft_slot:02d} "
                f"(reverse of startup 1.{self.startup_slot:02d})."
            )
        return notes

    def snake_pick_numbers(self, rounds: int = 5) -> list[int]:
        """First N pick numbers for the active draft slot."""
        slot = self.startup_slot if self.is_vet_draft else self.rookie_draft_slot
        picks: list[int] = []
        for round_no in range(1, rounds + 1):
            if round_no % 2 == 1:
                picks.append((round_no - 1) * self.teams + slot)
            else:
                picks.append(round_no * self.teams - slot + 1)
        return picks
