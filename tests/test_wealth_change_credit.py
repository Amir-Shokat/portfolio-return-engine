import numpy as np
import pandas as pd
import pytest

from portfolio_returns.credit import active_credit, effective_cash
from portfolio_returns.transactions import classify
from portfolio_returns.twr import daily_returns
from portfolio_returns.valuation import build_daily_table
from portfolio_returns.wealth_change import wealth_change

M = 1_000_000


def test_identity_and_flow_boundaries(daily_factory):
    d = daily_factory([100 * M, 130 * M, 125 * M, 180 * M], inflow=[999 * M, 20 * M, 0, 50 * M],
                      outflow=[0, 0, 10 * M, 0])
    wc = wealth_change(d, "2026-01-01", "2026-01-04")
    assert (wc.inflow, wc.outflow) == (70 * M, 10 * M)     # anchor-day 999 is inside BV
    assert wc.value == 180 * M - 100 * M - 60 * M == 20 * M
    assert wc.bv + wc.value + wc.net_flow == wc.ev
    assert wc.ratio == pytest.approx((180 + 10) / (100 + 70) - 1)


def test_unknown_flow_blocks_wealth_change(daily_factory):
    d = daily_factory([100 * M, 110 * M, 120 * M])
    d["flag"] = [None, "UNMAPPED_TRANSACTION", None]
    assert wealth_change(d, "2026-01-01", "2026-01-03").status == "RETURN_UNAVAILABLE"
    d["flag"] = [None, "MISSING_VALUATION", None]        # a missing internal value does not block it
    assert wealth_change(d, "2026-01-01", "2026-01-03").value == 20 * M


def test_waterfall_separates_credit_from_deposits(daily_factory):
    d = daily_factory([100 * M, 160 * M, 150 * M], inflow=[0, 50 * M, 0], outflow=[0, 0, 0])
    d["deposits"], d["credit_in"] = [0, 20 * M, 0], [0, 30 * M, 0]
    w = wealth_change(d, "2026-01-01", "2026-01-03").waterfall()
    assert w["step"].tolist() == ["Start value", "Investment gain", "Deposits", "Credit, net", "End value"]
    assert w["amount"].iloc[:-1].sum() == w["amount"].iloc[-1] == 150 * M


def values_and_txns(rows, txns):
    v = pd.DataFrame(rows, columns=["date", "cash", "holdings"])
    t = pd.DataFrame(txns, columns=["txn_id", "date", "type", "amount", "ref"])
    return v, classify(t)


def test_buying_on_credit_creates_no_return_by_itself():
    v, a = values_and_txns([("2026-05-01", 100 * M, 0), ("2026-05-02", -50 * M, 150 * M)],
                           [("T1", "2026-05-02", "CREDIT_GRANTED", 50 * M, "C-0001"),
                            ("T2", "2026-05-02", "BUY", 150 * M, "")])
    daily, _, issues = build_daily_table(v, a)
    assert not issues
    assert daily["total_value"].tolist() == [100 * M, 150 * M]
    assert daily_returns(daily)["daily_return"].iloc[1] == pytest.approx(0.0)
    # Flooring negative cash at zero counts the credit twice: a +33% day out of nothing.
    floored, _, _ = build_daily_table(v, a, floor_cash=pd.Series(True, index=pd.to_datetime(["2026-05-02"])))
    assert daily_returns(floored)["daily_return"].iloc[1] == pytest.approx(200 / 150 - 1)


def test_credit_removal_is_not_repayment():
    v, a = values_and_txns([("2026-05-01", 100 * M, 0), ("2026-05-02", -50 * M, 150 * M),
                            ("2026-05-03", -50 * M, 150 * M), ("2026-05-04", 100 * M, 0)],
                           [("T1", "2026-05-02", "CREDIT_GRANTED", 50 * M, "C-0001"),
                            ("T2", "2026-05-03", "CREDIT_REMOVED", 50 * M, "C-0001"),
                            ("T3", "2026-05-04", "SELL", 150 * M, "")])
    daily, _, _ = build_daily_table(v, a)
    assert daily["credit"].tolist() == [0, 50 * M, 0, 0]
    assert daily["total_value"].tolist() == [100 * M, 150 * M, 100 * M, 100 * M]
    assert daily["outflow"].tolist() == [0, 0, 50 * M, 0]          # the sale is internal
    assert daily_returns(daily)["daily_return"].iloc[1:].tolist() == pytest.approx([0.0, 0.0, 0.0])


def test_credit_inconsistencies_are_reported_not_clipped():
    a = classify(pd.DataFrame([("T1", "2026-05-02", "CREDIT_GRANTED", 50, "C-1"),
                               ("T2", "2026-05-03", "CREDIT_REMOVED", 80, "C-1"),
                               ("T3", "2026-05-03", "CREDIT_REMOVED", 10, "C-2")],
                              columns=["txn_id", "date", "type", "amount", "ref"]))
    level, issues = active_credit(a, pd.date_range("2026-05-01", "2026-05-03"))
    assert sorted(i.code for i in issues) == ["CREDIT_MISSING_OPENING", "CREDIT_OVER_REMOVAL"]
    assert level.tolist() == [0, 50, 0]


def test_effective_cash_floors_only_listed_days():
    raw = pd.Series([-5.0, -5.0], index=pd.to_datetime(["2026-05-01", "2026-05-02"]))
    mask = pd.Series([True], index=pd.to_datetime(["2026-05-02"]))
    assert effective_cash(raw, mask).tolist() == [-5.0, 0.0]
    assert np.array_equal(effective_cash(raw).to_numpy(), raw.to_numpy())
