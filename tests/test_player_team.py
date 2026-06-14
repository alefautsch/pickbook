"""Tests for NFL team resolution fallbacks."""

from __future__ import annotations

from dataclasses import dataclass

from backend.services.player_team import resolve_nfl_team


@dataclass(frozen=True)
class _WarStub:
    name: str
    team: str | None = None


@dataclass(frozen=True)
class _StoreRow:
    nfl_team: str | None


class _StoreStub:
    def __init__(self, row: _StoreRow | None) -> None:
        self._row = row

    def lookup(self, sleeper_id: str | None, *, name: str | None = None) -> _StoreRow | None:
        return self._row


def test_resolve_prefers_sleeper_over_war_and_nflverse():
    team = resolve_nfl_team(
        player_id="1",
        sleeper={"team": "sea", "full_name": "Kenneth Walker"},
        war_player=_WarStub(name="Kenneth Walker", team="KC"),
        healthy_ppg_store=_StoreStub(_StoreRow("SF")),
    )
    assert team == "SEA"


def test_resolve_falls_back_to_war_when_sleeper_empty():
    team = resolve_nfl_team(
        player_id="1",
        sleeper={"team": None, "full_name": "Kenneth Walker"},
        war_player=_WarStub(name="Kenneth Walker", team="kc"),
    )
    assert team == "KC"


def test_resolve_falls_back_to_nflverse_when_sleeper_and_war_empty():
    team = resolve_nfl_team(
        player_id="5872",
        sleeper={"team": None, "full_name": "Deebo Samuel"},
        war_player=_WarStub(name="Deebo Samuel", team=""),
        healthy_ppg_store=_StoreStub(_StoreRow("WAS")),
    )
    assert team == "WAS"


def test_resolve_uses_opportunity_store_after_healthy_ppg():
    team = resolve_nfl_team(
        player_id="99",
        sleeper={},
        opportunity_store=_StoreStub(_StoreRow("BUF")),
    )
    assert team == "BUF"
