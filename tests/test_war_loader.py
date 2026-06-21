"""Tests for API-first war data loading."""

from pathlib import Path

from dynasty_draft.dynasty_daddy import DynastyDaddyStore
from dynasty_draft.war_data import WarData
from dynasty_draft.war_loader import _append_csv_only, load_war_data


def _csv(tmp_path: Path) -> Path:
    path = tmp_path / "war.csv"
    path.write_text(
        "\n".join(
            [
                "player,pos,team,worpTier,worp,porp,tradeValue,spikeHighP,spikeMidP,spikeLowP",
                "Csv Only,WR,NYJ,3,0.2,5.0,1500,0.1,0.2,0.3",
            ]
        ),
        encoding="utf-8",
    )
    return path


def test_war_data_empty_has_no_players():
    war = WarData.empty()
    assert war.players == []
    assert war.lookup("Anyone") is None


def test_append_csv_only_adds_missing_players(tmp_path):
    api_war = WarData.empty()
    api_war.replace_players(
        [
            __import__("dynasty_draft.war_data", fromlist=["PlayerValue"]).PlayerValue(
                name="Api Star",
                pos="WR",
                team="KC",
                worp_tier=1,
                worp=1.0,
                porp=10.0,
                trade_value=5000,
                spike_high_p=None,
                spike_mid_p=None,
                spike_low_p=None,
            )
        ]
    )
    merged = _append_csv_only(api_war, WarData(_csv(tmp_path)))
    assert merged.lookup("Api Star") is not None
    assert merged.lookup("Csv Only") is not None
    assert merged.lookup("Csv Only").trade_value == 1500


def test_load_war_data_csv_fallback_when_api_disabled(tmp_path):
    settings = {
        "war_csv": str(_csv(tmp_path)),
        "dynasty_daddy": {"enabled": False},
    }
    war, meta = load_war_data(settings)
    assert war.lookup("Csv Only") is not None
    assert meta["source"] == "csv"


def test_dynasty_daddy_to_war_data_without_csv(tmp_path):
    store = DynastyDaddyStore(
        market=14,
        superflex=True,
        player_values=[
            {
                "full_name": "Api Only",
                "position": "WR",
                "team": "CAR",
                "trade_value": 4000,
                "sf_trade_value": 4500,
            }
        ],
        league_metrics={},
        league_format_payload={},
        fetched_at=1.0,
    )
    war = store.to_war_data()
    player = war.lookup("Api Only")
    assert player is not None
    assert player.trade_value == 4500
