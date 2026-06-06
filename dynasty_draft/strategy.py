from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from dynasty_draft.war_data import POSITIONS, WarData, normalize_name


@dataclass
class DraftStrategy:
    """League-specific draft context beyond raw Sleeper state."""

    draft_phase: str = "vets"  # vets | rookies
    teams: int = 10
    startup_slot: int = 10
    rookie_draft_slot: int = 1
    reserved_rookies: list[str] = field(default_factory=lambda: ["Jeremiyah Love"])
    rookie_draft_reversed: bool = True

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> DraftStrategy:
        raw = config.get("strategy") or {}
        return cls(
            draft_phase=str(raw.get("draft_phase", "vets")),
            teams=int(raw.get("teams", 10)),
            startup_slot=int(raw.get("startup_slot", 10)),
            rookie_draft_slot=int(raw.get("rookie_draft_slot", 1)),
            reserved_rookies=list(raw.get("reserved_rookies") or []),
            rookie_draft_reversed=bool(raw.get("rookie_draft_reversed", True)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "draft_phase": self.draft_phase,
            "teams": self.teams,
            "startup_slot": self.startup_slot,
            "rookie_draft_slot": self.rookie_draft_slot,
            "reserved_rookies": self.reserved_rookies,
            "rookie_draft_reversed": self.rookie_draft_reversed,
        }

    @property
    def is_vet_draft(self) -> bool:
        return self.draft_phase.lower() == "vets"

    @property
    def is_rookie_draft(self) -> bool:
        return self.draft_phase.lower() == "rookies"

    def reserved_by_position(self, war: WarData) -> dict[str, int]:
        counts = {pos: 0 for pos in POSITIONS}
        for name in self.reserved_rookies:
            player = war.lookup(name)
            if player and player.pos in counts:
                counts[player.pos] += 1
        return counts

    def reserved_players(self, war: WarData) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for name in self.reserved_rookies:
            player = war.lookup(name)
            if not player:
                rows.append({"name": name, "pos": "?", "trade_value": None, "note": "not in war.csv"})
                continue
            rows.append(
                {
                    "name": player.name,
                    "pos": player.pos,
                    "trade_value": player.trade_value,
                    "note": "locked for rookie draft",
                }
            )
        return rows

    def strategy_notes(self, war: WarData) -> list[str]:
        notes: list[str] = []
        if self.is_vet_draft and self.reserved_rookies:
            reserved = ", ".join(self.reserved_rookies)
            notes.append(
                f"Vet-only startup at 1.{self.startup_slot:02d}: rookies are off the board. "
                f"You plan to take {reserved} at 1.{self.rookie_draft_slot:02d} in the reversed rookie draft — "
                "deprioritize early RB in this draft."
            )
            love = war.lookup("Jeremiyah Love")
            if love and normalize_name("Jeremiyah Love") in {
                normalize_name(n) for n in self.reserved_rookies
            }:
                notes.append(
                    f"Jeremiyah Love (TV {love.trade_value:,.0f}) fills your RB1 pipeline — "
                    "target QB/WR/TE value in rounds 1–4, then take a vet RB2 later."
                )
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
