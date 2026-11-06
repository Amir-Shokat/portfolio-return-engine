import pandas as pd
import pytest

from portfolio_returns.mwr import cash_flows, horizon_mwr, periodic_from_annual, simple_flows_mwr
from portfolio_returns.twr import daily_returns, horizon_twr

M = 1_000_000


def test_without_flows_mwr_equals_twr(daily_factory):
    d = daily_factory([100 * M, 103 * M, 101 * M, 108 * M])
    m = horizon_mwr(d, None, "2026-01-01", "2026-01-04")
    t = horizon_twr(daily_returns(d), "2026-01-01", "2026-01-04")
    assert m.value == pytest.approx(t.value, abs=1e-10) == pytest.approx(0.08)


def test_periodic_and_annual():
    m = simple_flows_mwr([100 * M] + [100 * M] * 364 + [110 * M], [0] * 366, [0] * 366)
    assert m.invested_days == 365
    assert m.value == pytest.approx(0.10) and m.annualised == pytest.approx(0.10)
    assert periodic_from_annual(0.21, 365 // 2) == pytest.approx(1.21 ** (182 / 365) - 1)


def test_tiny_start_value_is_zeroed(daily_factory):
    # 500 rials sit in the account for 330 days, then a deposit and a 10% month.
    values = [500.0] * 331 + [100 * M] * 30 + [110 * M]
    inflow = [0.0] * 331 + [100 * M - 500] + [0.0] * 30
    inflow = inflow[:len(values)]
    d = daily_factory(values, inflow=inflow, outflow=[0.0] * len(values))
    m = horizon_mwr(d, None, d.index[0], d.index[-1], min_capital=M)
    assert m.start_value_zeroed and m.reason == "TINY_START_VALUE_ZEROED"
    assert m.invested_days == 30
    assert m.value == pytest.approx(110 / (100 - 0.0005) - 1, rel=1e-6)     # about +10%, not +215%


def test_anchor_flow_inside_bv_end_flow_added_with_ev(daily_factory):
    d = daily_factory([100 * M, 100 * M, 150 * M], inflow=[40 * M, 0, 50 * M], outflow=[0, 0, 0])
    flows, bv, ev, zeroed = cash_flows(d, "2026-01-01", "2026-01-03")
    assert flows.to_dict() == {pd.Timestamp("2026-01-01"): -100 * M, pd.Timestamp("2026-01-03"): 100 * M}
    assert (bv, ev, zeroed) == (100 * M, 150 * M, False)


def test_deposit_before_a_fall_makes_mwr_worse_than_twr(daily_factory):
    # +20% on 100, then a 1,000 deposit, then -10% on everything.
    d = daily_factory([100 * M, 120 * M, 1_120 * M, 1_008 * M], inflow=[0, 0, 1_000 * M, 0], outflow=[0, 0, 0, 0])
    m = horizon_mwr(d, daily_returns(d), "2026-01-01", "2026-01-04")
    t = horizon_twr(daily_returns(d), "2026-01-01", "2026-01-04")
    assert t.value == pytest.approx(1.2 * 0.9 - 1)              # +8%: the investments gained
    assert m.value < 0 < t.value


def test_no_contribution_and_total_loss(daily_factory):
    assert horizon_mwr(daily_factory([0.0, 0.0, 0.0]), None, "2026-01-01", "2026-01-03").status == "NO_INVESTMENT"
    lost = horizon_mwr(daily_factory([100 * M, 40 * M, 0.0]), None, "2026-01-01", "2026-01-03")
    assert (lost.status, lost.value, lost.reason) == ("CALCULATED", -1.0, "TOTAL_LOSS")


def test_unknown_day_makes_mwr_unavailable(daily_factory):
    d = daily_factory([100 * M, 101 * M, 102 * M])
    d["flag"] = [None, "MISSING_VALUATION", None]
    m = horizon_mwr(d, daily_returns(d), "2026-01-01", "2026-01-03")
    assert m.status == "RETURN_UNAVAILABLE" and m.value is None


def test_window_outside_table_is_insufficient_history(daily_factory):
    d = daily_factory([100 * M, 101 * M])
    assert horizon_mwr(d, None, "2025-12-01", "2026-01-02").status == "INSUFFICIENT_HISTORY"


def test_tiny_start_value_kept_stretches_one_month_over_a_year():
    values = [500.0] * 331 + [100 * M] * 30 + [110 * M]
    inflow = [0.0] * 331 + [100 * M - 500] + [0.0] * 30
    m = simple_flows_mwr(values, inflow, [0.0] * len(values), min_capital=0)
    assert m.invested_days == 361
    assert m.value == pytest.approx(2.1481, abs=1e-4)
