"""Wealth change: the gain or loss in currency units after removing deposits and withdrawals.

    net_flow       = sum(inflows) - sum(outflows)          over (anchor, end]
    wealth_change  = EV - BV - net_flow

BV is the total value at the anchor close (the day before the first included day), EV the
total value at the end close. Flows on the anchor date are already inside BV and are not
counted again; flows on the end date are counted. The four card numbers always add up::

    BV + wealth_change + net_flow = EV

Wealth change is an amount, not a rate: there is no division, so the minimum-capital guard
and the -100% floor of TWR do not apply, and every day of the window counts. A missing
internal value does not block it either; only unknown boundary values or an unknown flow
(an unmapped transaction) in the window do.

``ratio`` is used only by the display policy, never shown::

    R = (EV + outflows) / (BV + inflows) - 1
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class WealthChange:
    status: str
    anchor: pd.Timestamp | None = None
    end: pd.Timestamp | None = None
    bv: float | None = None
    ev: float | None = None
    inflow: float = 0.0
    outflow: float = 0.0
    deposits: float = 0.0
    withdrawals: float = 0.0
    credit_in: float = 0.0
    credit_out: float = 0.0
    other_in: float = 0.0
    other_out: float = 0.0
    reason: str | None = None

    @property
    def net_flow(self) -> float:
        return self.inflow - self.outflow

    @property
    def value(self) -> float | None:
        if self.status != "CALCULATED":
            return None
        return self.ev - self.bv - self.net_flow

    @property
    def days(self) -> int:
        return (self.end - self.anchor).days if self.anchor is not None and self.end is not None else 0

    @property
    def base(self) -> float | None:
        return None if self.bv is None else self.bv + self.inflow

    @property
    def ratio(self) -> float | None:
        """Relative change for the display policy; None when undefined (no base and no exit)."""
        if self.status != "CALCULATED":
            return None
        base, back = self.bv + self.inflow, self.ev + self.outflow
        if base == 0:
            return None if back == 0 else np.inf
        return back / base - 1.0

    def waterfall(self, split_flows: bool = True) -> pd.DataFrame:
        """Waterfall bars: start value, investment gain, flows, end value.

        With ``split_flows`` the net flow is broken into customer deposits/withdrawals, credit
        and other boundary crossings (securities transfers, dividends paid out, rights), so
        credit adjustments are not shown as bank deposits.
        """
        if self.status != "CALCULATED":
            return pd.DataFrame(columns=["step", "amount", "level"])
        rows = [("Start value", self.bv), ("Investment gain", self.value)]
        if split_flows:
            rows += [("Deposits", self.deposits), ("Withdrawals", -self.withdrawals),
                     ("Credit, net", self.credit_in - self.credit_out),
                     ("Other flows, net", self.other_in - self.other_out)]
        else:
            rows += [("Net deposits and withdrawals", self.net_flow)]
        out = pd.DataFrame(rows, columns=["step", "amount"])
        out = out[(out["amount"] != 0) | out["step"].isin(["Start value", "Investment gain"])]
        out["level"] = out["amount"].cumsum()
        out = pd.concat([out, pd.DataFrame([{"step": "End value", "amount": self.ev, "level": self.ev}])],
                        ignore_index=True)
        if not np.isclose(out["level"].iloc[-2], self.ev, rtol=0, atol=1e-6 * max(1.0, abs(self.ev))):
            raise AssertionError("waterfall does not add up to the end value")
        return out


def wealth_change(daily: pd.DataFrame, anchor, end) -> WealthChange:
    """Wealth change over ``(anchor, end]`` from the daily table."""
    anchor, end = pd.Timestamp(anchor), pd.Timestamp(end)
    if anchor not in daily.index or end not in daily.index:
        return WealthChange("INSUFFICIENT_HISTORY", anchor, end)
    if end <= anchor:
        return WealthChange("NO_ELAPSED_TIME", anchor, end)
    bv, ev = daily.at[anchor, "total_value"], daily.at[end, "total_value"]
    w = daily.loc[(daily.index > anchor) & (daily.index <= end)]
    if pd.isna(bv) or pd.isna(ev):
        return WealthChange("RETURN_UNAVAILABLE", anchor, end, reason="MISSING_BOUNDARY_VALUE")
    flow_flags = {"UNMAPPED_TRANSACTION", "CREDIT_INCONSISTENT"}
    if "flag" in w and w["flag"].isin(flow_flags).any():
        return WealthChange("RETURN_UNAVAILABLE", anchor, end, reason="UNKNOWN_FLOW_IN_PERIOD")
    sums = {c: float(w[c].sum()) for c in ["inflow", "outflow", "deposits", "withdrawals",
                                           "credit_in", "credit_out", "other_in", "other_out"] if c in w}
    return WealthChange("CALCULATED", anchor, end, float(bv), float(ev), **sums)
