"""Tests for trade calculator service."""

from backend.services.trade_calculator_service import (
    _accept_likelihood_grade,
    _overall_grade,
    _tv_fairness_grade,
)


def test_tv_fairness_grade_within_band():
    assert _tv_fairness_grade({"within_band": True, "net_delta_adjusted_pct": 2}) == "A"


def test_tv_fairness_grade_lopsided():
    assert _tv_fairness_grade({"within_band": False, "net_delta_adjusted_pct": 35}) == "D"
    assert _tv_fairness_grade({"within_band": False, "net_delta_adjusted_pct": 45}) == "F"


def test_accept_likelihood_grade():
    assert _accept_likelihood_grade("high") == "A"
    assert _accept_likelihood_grade("low") == "D"


def test_overall_grade_takes_worst():
    assert _overall_grade("A", "D", "A") == "D"
    assert _overall_grade("B+", None, None) == "B+"
