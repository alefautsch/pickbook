"""Tests for pick valuation floors (lock premium + Dynasty Dealer)."""

from backend.services.pick_valuation import (
    LOCK_DISCOUNT,
    apply_market_pick_adjustments,
    resolve_prospect_tv,
)
from dynasty_draft.dynasty_dealer import DynastyDealerStore
from dynasty_draft.ktc_values import KtcStore


def _ktc_store(**names: int) -> KtcStore:
    from dynasty_draft.war_data import normalize_name

    return KtcStore(
        superflex=True,
        by_name={normalize_name(k): v for k, v in names.items()},
        by_pick={},
        fetched_at=0.0,
        _rows=[],
    )


def _dd_store(*, players: dict[str, float], slots: dict[tuple[str, int, int], float]) -> DynastyDealerStore:
    from dynasty_draft.war_data import normalize_name

    return DynastyDealerStore(
        superflex=True,
        by_name={normalize_name(k): v for k, v in players.items()},
        by_sleeper_id={},
        by_slot=slots,
        fetched_at=0.0,
    )


def test_resolve_prospect_tv_uses_highest_source():
    ktc = _ktc_store(**{"Jeremiyah Love": 7500})
    dd = _dd_store(players={"Jeremiyah Love": 8169}, slots={})
    assert resolve_prospect_tv("Jeremiyah Love", ktc_store=ktc, dd_store=dd) == 8169


def test_locked_slot_option_c_blend():
    ktc = _ktc_store(**{"Jeremiyah Love": 7500})
    dd = _dd_store(
        players={"Jeremiyah Love": 8169},
        slots={("2026", 1, 1): 8169},
    )
    tv, meta = apply_market_pick_adjustments(
        6471.0,
        pick_season="2026",
        current_season="2026",
        round_no=1,
        slot_in_round=1,
        ktc_store=ktc,
        dd_store=dd,
    )
    assert tv == 8169
    assert meta is not None
    assert meta["valuation_source"] == "lock_blend"
    assert meta["locked_prospect"] == "Jeremiyah Love"
    assert meta["prospect_floor"] == round(8169 * LOCK_DISCOUNT, 1)


def test_premium_non_locked_slot_uses_dd_only():
    dd = _dd_store(players={}, slots={("2026", 1, 3): 6422})
    tv, meta = apply_market_pick_adjustments(
        5445.0,
        pick_season="2026",
        current_season="2026",
        round_no=1,
        slot_in_round=3,
        ktc_store=None,
        dd_store=dd,
    )
    assert tv == 6422
    assert meta is not None
    assert meta["valuation_source"] == "dynasty_dealer_slot"


def test_future_season_unchanged():
    dd = _dd_store(players={}, slots={("2027", 1, 1): 9000})
    tv, meta = apply_market_pick_adjustments(
        5000.0,
        pick_season="2027",
        current_season="2026",
        round_no=1,
        slot_in_round=1,
        ktc_store=None,
        dd_store=dd,
    )
    assert tv == 5000.0
    assert meta is None


def test_dynasty_dealer_from_payload_indexes_slots():
    payload = {
        "players": [
            {
                "sleeper_id": "pick_2026_1_slot_01",
                "name": "2026 Pick 1.01",
                "current_value": 8169,
            },
            {
                "sleeper_id": "13287",
                "name": "Jeremiyah Love",
                "base_value": 8169,
                "current_value": 8000,
            },
        ]
    }
    store = DynastyDealerStore.from_payload(payload, superflex=True, fetched_at=0.0)
    assert store.lookup_slot("2026", 1, 1) == 8169
    assert store.lookup_player("Jeremiyah Love") == 8169
    assert store.lookup_sleeper_id("13287") == 8169
