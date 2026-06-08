from pathlib import Path

from dynasty_draft.dynasty_daddy import DynastyDaddyStore
from dynasty_draft.war_data import WarData


def _war(tmp_path: Path) -> WarData:
    path = tmp_path / "war.csv"
    path.write_text(
        "\n".join(
            [
                "player,pos,team,worpTier,worp,porp,tradeValue,spikeHighP,spikeMidP,spikeLowP",
                "Existing Player,WR,KC,2,1.2,8.0,3000,0.1,0.2,0.3",
                "Fallback Player,RB,DAL,3,0.5,3.0,1200,0.0,0.1,0.2",
            ]
        ),
        encoding="utf-8",
    )
    return WarData(path)


def test_dynasty_daddy_overlay_uses_superflex_value_and_league_worp(tmp_path):
    store = DynastyDaddyStore(
        market=14,
        superflex=True,
        player_values=[
            {
                "full_name": "Existing Player",
                "position": "WR",
                "team": "KC",
                "trade_value": 4000,
                "sf_trade_value": 4500,
                "overall_rank": 20,
                "sf_overall_rank": 18,
            }
        ],
        league_metrics={
            "existingplayerwr": {
                "w": {"worp": 2.5, "porp": 12.0, "percent": 0.9, "cWorp": 2.8}
            }
        },
        league_format_payload={"seasons": [2025], "startWeek": 1, "endWeek": 18},
        fetched_at=1.0,
    )

    war = store.overlay_war_data(_war(tmp_path))
    player = war.lookup("Existing Player")

    assert player is not None
    assert player.trade_value == 4500
    assert player.worp == 2.5
    assert player.porp == 12.0
    assert war.lookup_value_inputs("Existing Player")["dynasty_daddy"]["selected_format"] == "superflex"


def test_dynasty_daddy_overlay_keeps_csv_fallback_players(tmp_path):
    store = DynastyDaddyStore(
        market=14,
        superflex=False,
        player_values=[],
        league_metrics={},
        league_format_payload={"seasons": [2025], "startWeek": 1, "endWeek": 18},
        fetched_at=1.0,
    )

    war = store.overlay_war_data(_war(tmp_path))
    player = war.lookup("Fallback Player")

    assert player is not None
    assert player.trade_value == 1200
    assert war.lookup_value_inputs("Fallback Player")["dynasty_daddy"]["source"] == "war_csv"
