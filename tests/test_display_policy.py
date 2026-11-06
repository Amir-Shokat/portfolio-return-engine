import numpy as np
import pandas as pd
import pytest

from portfolio_returns import display_policy as dp
from portfolio_returns.wealth_change import WealthChange

A, B = pd.Timestamp("2026-01-01"), pd.Timestamp("2026-02-01")


@pytest.mark.parametrize("status,state", [("INSUFFICIENT_HISTORY", dp.EMPTY), ("NO_INVESTMENT", dp.EMPTY),
                                          ("RETURN_UNAVAILABLE", dp.HIDDEN), ("NO_ELAPSED_TIME", dp.HIDDEN)])
def test_uncalculated_values_are_never_shown_as_zero(status, state):
    d = dp.return_display(status, None, "1M", 30)
    assert d.state == state and d.value is None and d.message


@pytest.mark.parametrize("value,state", [(0.05, dp.NORMAL), (-0.29, dp.NORMAL), (-0.45, dp.WARNING),
                                         (1.5, dp.WARNING), (2.6, dp.HIDDEN), (-0.61, dp.HIDDEN),
                                         (-1.0, dp.HIDDEN)])
def test_twr_bands_for_one_month(value, state):
    assert dp.return_display("CALCULATED", value, "1M", 30).state == state


def test_bands_differ_by_horizon_and_multiple_roots_warn():
    assert dp.return_display("CALCULATED", 2.6, "1Y", 365).state == dp.NORMAL
    d = dp.return_display("CALCULATED", 0.05, "1M", 30, dp.MWR_BANDS, "MWR", reason="MULTIPLE_ROOTS")
    assert (d.state, d.code) == (dp.WARNING, "MWR_MULTIPLE_ROOTS")


def wc(bv, ev, inflow=0.0, outflow=0.0):
    return WealthChange("CALCULATED", A, B, bv, ev, inflow, outflow)


@pytest.mark.parametrize("w,code,state", [
    (wc(100, 105), "WC_WITHIN_NORMAL_BAND", dp.NORMAL),
    (wc(100, 300), "WC_OUTSIDE_NORMAL_BAND", dp.WARNING),
    (wc(-10, 50), "NEGATIVE_VALUE", dp.HIDDEN),
    (wc(0, 0), "NO_BASE_NO_EXIT", dp.NORMAL),
    (wc(100, 0), "TOTAL_LOSS", dp.HIDDEN),
])
def test_wealth_change_rules(w, code, state):
    d = dp.wealth_change_display(w, "1M")
    assert (d.code, d.state) == (code, state)


def test_comparison_text():
    assert dp.compare_twr_mwr(0.08, -0.02, True).code == "OPPOSITE_SIGNS"
    assert dp.compare_twr_mwr(0.05, 0.052, False).code == "SIMILAR_NO_FLOWS"
    assert dp.compare_twr_mwr(0.05, 0.09, True).code == "TIMING_HELPED"
    assert dp.compare_twr_mwr(None, 0.09, True).state == dp.EMPTY


def test_calibrated_bands_are_ordered_around_the_body():
    rng = np.random.default_rng(7)
    body = np.expm1(rng.normal(0.01, 0.08, 20_000))
    noise = np.expm1(rng.uniform(-2.0, 2.0, 1_000))     # long flat tail from calculation limits
    b = dp.calibrate_bands(np.r_[body, noise])
    assert b.hide_below < b.warn_below < 0 < b.warn_above < b.hide_above
