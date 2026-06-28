"""Tests for trade calculator service."""

from backend.services.trade_calculator_service import (
    _accept_likelihood_grade,
    _overall_grade,
    _overall_grade_for_completed,
    _overall_grade_for_negotiation,
    _tv_fairness_grade,
)


def test_tv_fairness_grade_within_band():
    assert _tv_fairness_grade({"within_band": True, "net_delta_adjusted_pct": 2}) == "A"


def test_tv_fairness_grade_lopsided():
    assert _tv_fairness_grade({"within_band": False, "net_delta_adjusted_pct": 35}) == "D"
    assert _tv_fairness_grade({"within_band": False, "net_delta_adjusted_pct": 45}) == "F"


def test_accept_likelihood_grade():
    assert _accept_likelihood_grade("high") == "A"
    assert _accept_likelihood_grade("low") == "C"
    assert _accept_likelihood_grade("medium") == "B"


def test_overall_grade_takes_worst():
    assert _overall_grade("A", "D", "A") == "D"
    assert _overall_grade("B+", None, None) == "B+"


def test_overall_grade_for_negotiation_blends_tv_and_accept():
    assert _overall_grade_for_negotiation("A", "A", "B") == "A"
    assert _overall_grade_for_negotiation("C+", "A", "A") == "B"
    assert _overall_grade_for_negotiation("D", "C", "C") == "D"


def test_overall_grade_for_completed_blends_tv_and_accept():
    assert _overall_grade_for_completed("A", "A", "B") == "A"
    assert _overall_grade_for_completed("C+", "A", "A") == "B"
    assert _overall_grade_for_completed("D", "D", "D") == "D"
