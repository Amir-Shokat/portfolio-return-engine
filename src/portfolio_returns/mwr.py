"""Money-weighted return (MWR) for a horizon, from the daily table and XIRR.

Cash flows for the window ``(anchor, end]``, investor perspective (as spreadsheet XIRR)::

    anchor date      -BV                   BV = total value at the anchor close
    each day t       Outflow[t] - Inflow[t]  deposits negative, withdrawals positive
    end date         +EV                   EV = total value at the end close

Flows on the anchor date are already inside BV and are not added again; flows on the end
date are added *and* EV is added, because EV is the value after those flows.

The solver returns an annual rate ``x``. The UI shows a periodic return, comparable with
the TWR of the same window::

    MWR_period = (1 + x) ** (invested_days / 365) - 1

``invested_days`` runs from the first to the last non-zero flow. When BV and EV are both
non-zero this is exactly the window; it is shorter when the account started from zero or
was emptied inside the window, so a one-month rate is not stretched over a whole year.

Boundary rules (from the edge-case review):

1. ``|BV| < min_capital``: BV is treated as 0 and the period starts at the first real flow.
   (A few rials left in the account for eleven months, then a deposit and a 10% month,
   would otherwise show about +215% for the year instead of +10%.)
2. ``BV <= -min_capital`` (real debt at the start): kept as it is.
3. No positive flow (nothing came back): -100%; reason LOSS_EXCEEDS_CAPITAL if EV < 0.
4. No negative flow (nothing was put in): NO_INVESTMENT, no number.
5. An INVALID_DATA day inside the window: RETURN_UNAVAILABLE.
6. Solver failure: RETURN_UNAVAILABLE with the solver status; several roots: the one
   closest to 0% with a MULTIPLE_ROOTS note.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .twr import MIN_CAPITAL_DEFAULT
from .xirr import DAYS_PER_YEAR, XirrResult, spreadsheet_xirr, xirr


@dataclass
class MwrResult:
    status: str
    value: float | None = None
    annualised: float | None = None
    reason: str | None = None
    bv: float | None = None
    ev: float | None = None
    window_days: int = 0
    invested_days: int = 0
    start_value_zeroed: bool = False
    flows: list = field(default_factory=list)
    solver: XirrResult | None = None
    spreadsheet_rate: float | None = None


def cash_flows(daily: pd.DataFrame, anchor, end, min_capital: float = MIN_CAPITAL_DEFAULT):
    """Investor-perspective dated flows for the window, and whether BV was zeroed."""
    anchor, end = pd.Timestamp(anchor), pd.Timestamp(end)
    bv, ev = float(daily.at[anchor, "total_value"]), float(daily.at[end, "total_value"])
    zeroed = abs(bv) < min_capital and bv != 0
    bv_used = 0.0 if abs(bv) < min_capital else bv
    w = daily.loc[(daily.index > anchor) & (daily.index <= end)]
    flows = {anchor: -bv_used}
    for date, row in w.iterrows():
        flows[date] = flows.get(date, 0.0) + float(row["outflow"] - row["inflow"])
    flows[end] = flows.get(end, 0.0) + ev
    series = pd.Series(flows).sort_index()
    return series[series != 0], bv, ev, zeroed


def horizon_mwr(daily: pd.DataFrame, returns: pd.DataFrame | None, anchor, end,
                min_capital: float = MIN_CAPITAL_DEFAULT) -> MwrResult:
    """MWR for ``(anchor, end]``. ``returns`` (from :func:`twr.daily_returns`) is used only to
    see whether any day in the window has unknown inputs."""
    anchor, end = pd.Timestamp(anchor), pd.Timestamp(end)
    days = (end - anchor).days
    if anchor not in daily.index or end not in daily.index:
        return MwrResult("INSUFFICIENT_HISTORY", window_days=days)
    if days <= 0:
        return MwrResult("NO_ELAPSED_TIME")
    window = daily.loc[(daily.index > anchor) & (daily.index <= end)]
    if returns is not None:
        rw = returns.loc[(returns.index > anchor) & (returns.index <= end)]
        if (rw["status"] == "INVALID_DATA").any():
            return MwrResult("RETURN_UNAVAILABLE", reason="INVALID_DATA_IN_PERIOD", window_days=days)
    elif window["flag"].notna().any() if "flag" in window else False:
        return MwrResult("RETURN_UNAVAILABLE", reason="INVALID_DATA_IN_PERIOD", window_days=days)
    bv, ev = daily.at[anchor, "total_value"], daily.at[end, "total_value"]
    if pd.isna(bv) or pd.isna(ev):
        return MwrResult("RETURN_UNAVAILABLE", reason="MISSING_BOUNDARY_VALUE", window_days=days)
    flows, bv, ev, zeroed = cash_flows(daily, anchor, end, min_capital)
    base = dict(bv=bv, ev=ev, window_days=days, start_value_zeroed=zeroed,
                flows=list(zip(flows.index, flows.to_numpy())))
    if not (flows < 0).any():
        return MwrResult("NO_INVESTMENT", reason="NO_CONTRIBUTION", **base)
    span = int((flows.index.max() - flows.index.min()).days)
    if not (flows > 0).any():
        return MwrResult("CALCULATED", -1.0, -1.0, "LOSS_EXCEEDS_CAPITAL" if ev < 0 else "TOTAL_LOSS",
                         invested_days=span, **base)
    if span == 0:
        return MwrResult("NO_ELAPSED_TIME", reason="ALL_FLOWS_ON_ONE_DATE", **base)
    solved = xirr(flows.index, flows.to_numpy())
    try:
        sheet = spreadsheet_xirr(flows.index, flows.to_numpy())
    except ValueError:
        sheet = None
    if not solved.ok:
        return MwrResult("RETURN_UNAVAILABLE", reason=f"XIRR_{solved.status}", solver=solved,
                         invested_days=span, spreadsheet_rate=sheet, **base)
    y = math.log1p(solved.rate)
    periodic = math.expm1(y * span / DAYS_PER_YEAR)
    reason = "MULTIPLE_ROOTS" if solved.status == "MULTIPLE_ROOTS" else ("TINY_START_VALUE_ZEROED" if zeroed else None)
    return MwrResult("CALCULATED", periodic, solved.rate, reason, invested_days=span, solver=solved,
                     spreadsheet_rate=sheet, **base)


def simple_flows_mwr(values: list[float], inflows: list[float], outflows: list[float],
                     start: str = "2026-01-01", min_capital: float = 0.0) -> MwrResult:
    """Convenience for examples and tests: daily values and flows from a start date."""
    idx = pd.date_range(start, periods=len(values), freq="D")
    daily = pd.DataFrame({"total_value": values, "inflow": inflows, "outflow": outflows}, index=idx)
    return horizon_mwr(daily, None, idx[0], idx[-1], min_capital=min_capital)


def periodic_from_annual(rate: float, days: int) -> float:
    """Convert an annual rate to a period of ``days`` (Actual/365)."""
    return float(np.expm1(np.log1p(rate) * days / DAYS_PER_YEAR))
