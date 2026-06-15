"""Consensus rookie-class constants shared by pick TV and trade reasoning."""

from __future__ import annotations

# Consensus startup ADP for 2026 rookies — overrides global TV rank and noisy sims.
CONSENSUS_ROOKIE_ADP: dict[str, int] = {
    "Jeremiyah Love": 1,
    "Carnell Tate": 2,
    "Fernando Mendoza": 3,
    "Makai Lemon": 4,
    "Jordyn Tyson": 5,
    "Kenyon Sadiq": 6,
    "Jadarian Price": 7,
    "KC Concepcion": 8,
    "Ty Simpson": 12,
    "Omar Cooper": 14,
    "Eli Stowers": 18,
}

# Picks where the class consensus is effectively locked for trade reasoning / TV.
ROOKIE_PICK_LOCKS: dict[int, str] = {
    1: "Jeremiyah Love",
}

ROOKIE_TRADE_SEASON = "2026"
