from __future__ import annotations

import csv
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any


POSITIONS = ("QB", "RB", "WR", "TE")


@dataclass(frozen=True)
class PlayerValue:
    name: str
    pos: str
    team: str
    worp_tier: int | None
    worp: float | None
    porp: float | None
    trade_value: float
    spike_high_p: float | None
    spike_mid_p: float | None
    spike_low_p: float | None

    @property
    def has_worp(self) -> bool:
        return self.worp is not None

    @property
    def upside(self) -> float:
        """Blend spike probabilities when present."""
        parts = [p for p in (self.spike_high_p, self.spike_mid_p, self.spike_low_p) if p is not None]
        return sum(parts) / len(parts) if parts else 0.0


def _parse_float(value: str) -> float | None:
    value = (value or "").strip()
    if not value or value.lower() == "nan":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _parse_int(value: str) -> int | None:
    parsed = _parse_float(value)
    return int(parsed) if parsed is not None else None


def normalize_name(name: str) -> str:
    """Normalize player names for Sleeper <-> CSV matching."""
    text = unicodedata.normalize("NFKD", name)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", "", text)
    text = re.sub(r"\s+(jr|sr|ii|iii|iv|v)$", "", text)
    return re.sub(r"\s+", " ", text).strip()


class WarData:
    def __init__(self, csv_path: Path):
        self.csv_path = csv_path
        self.players: list[PlayerValue] = []
        self.by_name: dict[str, PlayerValue] = {}
        self.value_inputs_by_name: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        with self.csv_path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(line for line in handle if not line.startswith("Data Exported"))
            for row in reader:
                trade_value = _parse_float(row.get("tradeValue", ""))
                if trade_value is None:
                    continue
                player = PlayerValue(
                    name=row["player"].strip(),
                    pos=(row.get("pos") or "").strip().upper(),
                    team=(row.get("team") or "").strip(),
                    worp_tier=_parse_int(row.get("worpTier", "")),
                    worp=_parse_float(row.get("worp", "")),
                    porp=_parse_float(row.get("porp", "")),
                    trade_value=trade_value,
                    spike_high_p=_parse_float(row.get("spikeHighP", "")),
                    spike_mid_p=_parse_float(row.get("spikeMidP", "")),
                    spike_low_p=_parse_float(row.get("spikeLowP", "")),
                )
                self.players.append(player)
                key = normalize_name(player.name)
                if key not in self.by_name:
                    self.by_name[key] = player
                    self.value_inputs_by_name[key] = {
                        "dynasty_daddy": {
                            "source": "war_csv",
                            "trade_value": player.trade_value,
                            "worp": player.worp,
                            "porp": player.porp,
                            "worp_tier": player.worp_tier,
                        }
                    }

    def lookup(self, name: str) -> PlayerValue | None:
        return self.by_name.get(normalize_name(name))

    def lookup_value_inputs(self, name: str) -> dict[str, Any]:
        return dict(self.value_inputs_by_name.get(normalize_name(name), {}))

    def replace_players(
        self,
        players: list[PlayerValue],
        *,
        value_inputs_by_name: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self.players = players
        self.by_name = {}
        self.value_inputs_by_name = {}
        provided_inputs = value_inputs_by_name or {}
        for player in players:
            key = normalize_name(player.name)
            if not key or key in self.by_name:
                continue
            self.by_name[key] = player
            self.value_inputs_by_name[key] = dict(provided_inputs.get(key, {}))

    def top_by_trade_value(self, n: int = 25) -> list[PlayerValue]:
        return sorted(self.players, key=lambda p: p.trade_value, reverse=True)[:n]
