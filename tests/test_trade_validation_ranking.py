"""Tests for validation-based package ranking."""

from unittest.mock import patch

from backend.services.advisor_tools import rank_packages_by_counterparty_validation


def _pkg(cp_id: str, quality: float = 5.0) -> dict:
    return {
        "counterparty": {"roster_id": cp_id, "team_name": f"Team {cp_id}"},
        "give": {"players": [{"player_id": "g1", "name": "Giver"}], "picks": []},
        "receive": {"players": [{"player_id": "r1", "name": "Receiver"}], "picks": []},
        "package_quality": quality,
        "net_delta_adjusted_pct": 0.0,
    }


def test_rank_packages_skips_without_api_key():
    packages = [_pkg("2"), _pkg("4")]
    result = rank_packages_by_counterparty_validation(
        packages,
        my_roster_id="3",
        resolve_player=lambda _: {"player_id": "x", "tv": 100},
        resolve_pick=lambda _: None,
        load_team=lambda _: {"team_name": "T"},
        trade_surplus=None,
        api_key=None,
    )
    assert result is packages


@patch("backend.services.advisor_tools.validate_trade_with_llm")
@patch("backend.services.advisor_tools.evaluate_trade_package")
def test_rank_packages_sorts_by_accept_score(mock_eval, mock_validate):
    mock_eval.return_value = {
        "give": {"players": [], "picks": []},
        "receive": {"players": [], "picks": []},
        "missing_assets": [],
    }

    def validation_side_effect(payload, api_key=None, model=None):
        cp = payload["review_for_team_context"]["roster_id"]
        if cp == "2":
            return {
                "accept_likelihood": "low",
                "fairness_from_counterparty_view": "favors_you",
                "would_improve_their_roster": False,
            }
        return {
            "accept_likelihood": "high",
            "fairness_from_counterparty_view": "favors_them",
            "would_improve_their_roster": True,
        }

    mock_validate.side_effect = validation_side_effect

    packages = [_pkg("2", quality=9.0), _pkg("4", quality=1.0)]
    ranked = rank_packages_by_counterparty_validation(
        packages,
        my_roster_id="3",
        resolve_player=lambda pid: {"player_id": pid, "tv": 100, "name": pid},
        resolve_pick=lambda _: None,
        load_team=lambda rid: {"team_name": f"T{rid}", "players": [], "draft_picks": []},
        trade_surplus={"surplus": [], "needs": []},
        api_key="test-key",
        max_validate=2,
    )

    assert ranked[0]["counterparty"]["roster_id"] == "4"
    assert ranked[0]["validation_accept_score"] > ranked[1]["validation_accept_score"]
    assert ranked[0]["counterparty_validation"]["accept_likelihood"] == "high"
