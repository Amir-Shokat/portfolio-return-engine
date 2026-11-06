import numpy as np
import pandas as pd
import pytest

from portfolio_returns.twr import (annualise, cumulative, daily_return, daily_returns, eod_net_return,
                                   horizon_twr, subperiods)

M = 1_000_000  # currency units


def test_inflow_at_start_of_day():
    r, status, _ = daily_return(100 * M, 160 * M, 50 * M, 0)
    assert status == "CALCULATED" and r == pytest.approx(160 / 150 - 1)


def test_outflow_at_end_of_day():
    r, _, _ = daily_return(100 * M, 60 * M, 0, 50 * M)
    assert r == pytest.approx(0.10)


def test_same_day_deposit_and_withdrawal_are_not_netted():
    # 1000 at the start, 500 in and 500 out on the same day, 1050 at the close.
    r, _, _ = daily_return(1000 * M, 1050 * M, 500 * M, 500 * M)
    assert r == pytest.approx(1550 / 1500 - 1)          # 3.33%
    assert eod_net_return(1000 * M, 1050 * M, 0) == pytest.approx(0.05)  # netted view overstates


@pytest.mark.parametrize("args,status,reason", [
    ((500_000, 600_000, 0, 0), "LOW_CAPITAL", "BELOW_MIN_CAPITAL"),
    ((-5 * M, 2 * M, 1 * M, 0), "LOW_CAPITAL", "NON_POSITIVE_CAPITAL"),
    ((0, 0, 0, 0), "NO_CAPITAL", "EMPTY_ZERO_CAPITAL_DAY"),
    ((np.nan, 1 * M, 0, 0), "INVALID_DATA", "MISSING_VALUATION"),
    ((2 * M, 1 * M, -1, 0), "INVALID_DATA", "NEGATIVE_FLOW_INPUT"),
])
def test_daily_statuses(args, status, reason):
    r, s, why = daily_return(*args)
    assert (s, why) == (status, reason) and np.isnan(r)


def test_loss_larger_than_capital_is_floored():
    r, s, why = daily_return(10 * M, -5 * M, 0, 0)
    assert (r, s, why) == (-1.0, "CALCULATED", "LOSS_EXCEEDS_CAPITAL")


def test_daily_returns_link_geometrically(daily_factory):
    rt = daily_returns(daily_factory([100 * M, 110 * M, 99 * M]))
    assert rt["status"].iloc[0] == "BASELINE"
    res = horizon_twr(rt, "2026-01-01", "2026-01-03")
    assert res.status == "CALCULATED" and res.value == pytest.approx(-0.01)   # 1.1 x 0.9 - 1, not +0%


def test_daily_table_must_be_consecutive(daily_factory):
    d = daily_factory([1 * M, 2 * M, 3 * M]).drop(pd.Timestamp("2026-01-02"))
    with pytest.raises(ValueError):
        daily_returns(d)


def test_low_capital_day_is_flat_and_does_not_block(daily_factory):
    # A small residual balance after a withdrawal; a +50% day on that dust is skipped, not compounded.
    rt = daily_returns(daily_factory([100 * M, 200_000, 300_000, 110 * M], inflow=[0, 0, 0, 99.7 * M],
                                     outflow=[0, 99.8 * M, 0, 0]))
    res = horizon_twr(rt, "2026-01-01", "2026-01-04")
    assert res.low_capital_days == 1
    assert rt["factor"].iloc[2] == 1.0
    assert res.value == pytest.approx(0.10)


def test_unknown_day_blocks_and_stops_the_chart(daily_factory):
    d = daily_factory([100 * M, 101 * M, 102 * M, 103 * M])
    d["flag"] = [None, None, "UNMAPPED_TRANSACTION", None]
    rt = daily_returns(d)
    assert rt["status"].tolist()[2:] == ["INVALID_DATA", "INVALID_DATA"]   # next day's opening is unknown too
    res = horizon_twr(rt, "2026-01-01", "2026-01-04")
    assert res.status == "RETURN_UNAVAILABLE" and res.first_invalid_date == pd.Timestamp("2026-01-03")
    cum = cumulative(rt, "2026-01-01", "2026-01-04")
    assert cum.iloc[0] == 0.0 and cum.iloc[1] == pytest.approx(0.01) and cum.iloc[2:].isna().all()
    assert horizon_twr(rt, "2026-01-01", "2026-01-02").status == "CALCULATED"


def test_cumulative_is_rebased_to_zero_on_anchor(daily_factory):
    rt = daily_returns(daily_factory([100 * M, 120 * M, 132 * M]))
    cum = cumulative(rt, "2026-01-02", "2026-01-03")
    assert cum.tolist() == pytest.approx([0.0, 0.10])


def test_all_low_capital_window_is_no_investment(daily_factory):
    rt = daily_returns(daily_factory([100_000, 200_000, 300_000]))
    assert horizon_twr(rt, "2026-01-01", "2026-01-03").status == "NO_INVESTMENT"


def test_subperiods_reconcile_with_daily_linking(daily_factory):
    d = daily_factory([100 * M, 104 * M, 106 * M, 160 * M, 150 * M, 155 * M],
                      inflow=[0, 0, 0, 50 * M, 0, 0], outflow=[0, 0, 0, 0, 0, 0])
    rt = daily_returns(d)
    blocks = subperiods(rt, "2026-01-01", "2026-01-06")
    assert list(blocks["kind"]) == ["quiet", "flow", "quiet"]
    assert np.prod(blocks["factor"]) - 1 == pytest.approx(horizon_twr(rt, "2026-01-01", "2026-01-06").value)


def test_annualise_actual_365():
    assert annualise(0.10, 365) == pytest.approx(0.10)
    assert annualise(0.21, 730) == pytest.approx(0.10)
    assert annualise(-1.0, 30) is None and annualise(0.1, 0) is None
