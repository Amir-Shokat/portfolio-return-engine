"""Time-weighted return (TWR) from end-of-day values and gross daily flows.

Only one value per day is stored, after the market closes, so the timing of flows inside
the day is an assumption. The convention used here (the one in the open-source Portfolio
Performance application) is: inflows at the **beginning** of the day, outflows at the
**end** of the day::

    D[t] = V[t-1] + Inflow[t]                  capital at work during day t
    r[t] = (V[t] + Outflow[t]) / D[t] - 1

Daily returns are linked geometrically, never added: ``TWR = prod(1 + r[t]) - 1``.

Daily statuses (``status`` / ``reason``):

=============  =======================  ============================================
BASELINE       ANCHOR_DAY               first row, no earlier value
CALCULATED     (empty)                  normal return, including 0 and -100%
CALCULATED     LOSS_EXCEEDS_CAPITAL     loss larger than capital, floored at -100%
NO_CAPITAL     EMPTY_ZERO_CAPITAL_DAY   values and flows all zero (empty account)
LOW_CAPITAL    NON_POSITIVE_CAPITAL     D <= 0
LOW_CAPITAL    BELOW_MIN_CAPITAL        0 < D < min_capital
INVALID_DATA   specific reason          unknown or inconsistent inputs
=============  =======================  ============================================

``factor`` is what linking uses: ``1 + r`` when calculated, ``1`` for BASELINE, NO_CAPITAL
and LOW_CAPITAL (the chart stays flat and the horizon is not blocked), and NaN for
INVALID_DATA (every horizon containing that day is blocked). ``daily_return`` stays NaN
for non-calculated days so risk statistics never see artificial zero days.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

MIN_CAPITAL_DEFAULT = 1_000_000  # currency units; calibrate on real data (docs/display-policy.md)

FLAT_STATUSES = {"BASELINE", "NO_CAPITAL", "LOW_CAPITAL"}


def daily_return(begin, end, inflow, outflow, min_capital: float = MIN_CAPITAL_DEFAULT):
    """Return ``(r, status, reason)`` for one day. Values may be negative; flows may not."""
    vals = [begin, end, inflow, outflow]
    if any(v is None or pd.isna(v) for v in vals[:2]):
        return np.nan, "INVALID_DATA", "MISSING_VALUATION"
    if any(v is None or pd.isna(v) for v in vals[2:]):
        return np.nan, "INVALID_DATA", "MISSING_FLOW_INPUT"
    try:
        x = np.asarray(vals, dtype=float)
    except (TypeError, ValueError):
        return np.nan, "INVALID_DATA", "INVALID_NUMERIC_INPUT"
    if not np.isfinite(x).all():
        return np.nan, "INVALID_DATA", "INVALID_NUMERIC_INPUT"
    if x[2] < 0 or x[3] < 0:
        return np.nan, "INVALID_DATA", "NEGATIVE_FLOW_INPUT"
    if (x == 0).all():
        return np.nan, "NO_CAPITAL", "EMPTY_ZERO_CAPITAL_DAY"
    capital = x[0] + x[2]
    if capital <= 0:
        return np.nan, "LOW_CAPITAL", "NON_POSITIVE_CAPITAL"
    if capital < min_capital:
        return np.nan, "LOW_CAPITAL", "BELOW_MIN_CAPITAL"
    r = (x[1] + x[3]) / capital - 1.0
    if not np.isfinite(r):
        return np.nan, "INVALID_DATA", "NON_FINITE_RESULT"
    if r < -1.0:
        return -1.0, "CALCULATED", "LOSS_EXCEEDS_CAPITAL"
    return float(r), "CALCULATED", None


def eod_net_return(begin, end, net_flow):
    """Older convention kept for comparison: all flows at end of day, netted.

    ``r = (V[t] - CF[t] - V[t-1]) / V[t-1]``. Same-day opposite flows cancel, so a flow
    boundary disappears; see docs/decisions.md.
    """
    return (end - net_flow - begin) / begin


def _factor(r, status):
    if status == "CALCULATED":
        return 1.0 + r
    if status in FLAT_STATUSES:
        return 1.0
    return np.nan


def daily_returns(daily: pd.DataFrame, min_capital: float = MIN_CAPITAL_DEFAULT) -> pd.DataFrame:
    """Daily returns for a daily table (index: consecutive dates).

    Needs ``total_value``, ``inflow`` and ``outflow``; an optional ``flag`` column marks days
    whose inputs are known to be unknown or inconsistent (reason codes from the valuation
    step, such as ``UNMAPPED_TRANSACTION``). An unknown closing value also makes the next
    day's opening value unknown.
    """
    d = daily.sort_index()
    if d.empty:
        raise ValueError("daily table is empty")
    expected = pd.date_range(d.index.min(), d.index.max(), freq="D")
    if len(d.index) != len(expected) or not (d.index == expected).all():
        raise ValueError("daily table must have one row per consecutive calendar day")
    flags = d["flag"] if "flag" in d else pd.Series(None, index=d.index, dtype=object)
    rows = []
    prev_value = np.nan
    for i, (date, row) in enumerate(d.iterrows()):
        end, inflow, outflow = row["total_value"], row["inflow"], row["outflow"]
        flag = flags.iloc[i]
        if flag is not None and not (isinstance(flag, float) and pd.isna(flag)):
            r, status, reason = np.nan, "INVALID_DATA", str(flag)
        elif i == 0:
            r, status, reason = np.nan, "BASELINE", "ANCHOR_DAY"
        else:
            r, status, reason = daily_return(prev_value, end, inflow, outflow, min_capital)
        rows.append(dict(date=date, begin_value=prev_value if i else np.nan, end_value=end,
                         inflow=inflow, outflow=outflow,
                         start_capital=prev_value + inflow if i else np.nan,
                         daily_return=r, status=status, reason=reason, factor=_factor(r, status)))
        prev_value = end if not (flag is not None and not (isinstance(flag, float) and pd.isna(flag))) else np.nan
    return pd.DataFrame(rows).set_index("date")


def cumulative(returns: pd.DataFrame, anchor, end) -> pd.Series:
    """Cumulative TWR from 0% on the anchor date (rebased to zero).

    The anchor's own daily return is not used: it belongs to the interval before the
    anchor. Flat days keep the last level. From the first INVALID_DATA day onward the
    series is NaN: the line stops and is never bridged across unknown performance.
    """
    anchor, end = pd.Timestamp(anchor), pd.Timestamp(end)
    f = returns.loc[(returns.index > anchor) & (returns.index <= end), "factor"]
    cum = f.cumprod() - 1.0
    cum[f.isna().cummax()] = np.nan
    return pd.concat([pd.Series([0.0], index=[anchor]), cum]).rename("cumulative_twr")


@dataclass
class TwrResult:
    status: str
    value: float | None
    days: int
    low_capital_days: int = 0
    loss_floor_days: int = 0
    first_invalid_date: pd.Timestamp | None = None
    first_invalid_reason: str | None = None


def horizon_twr(returns: pd.DataFrame, anchor, end) -> TwrResult:
    """Non-annualised TWR over the window ``(anchor, end]``.

    CALCULATED            every factor known (empty and low-capital days count as 1)
    RETURN_UNAVAILABLE    an INVALID_DATA day inside the window
    NO_INVESTMENT         every day in the window is NO_CAPITAL or LOW_CAPITAL
    INSUFFICIENT_HISTORY  anchor or end outside the daily table
    NO_ELAPSED_TIME       anchor equals end
    """
    anchor, end = pd.Timestamp(anchor), pd.Timestamp(end)
    days = (end - anchor).days
    if anchor not in returns.index or end not in returns.index:
        return TwrResult("INSUFFICIENT_HISTORY", None, days)
    if days <= 0:
        return TwrResult("NO_ELAPSED_TIME", None, 0)
    w = returns.loc[(returns.index > anchor) & (returns.index <= end)]
    base = dict(days=days, low_capital_days=int((w["status"] == "LOW_CAPITAL").sum()),
                loss_floor_days=int((w["reason"] == "LOSS_EXCEEDS_CAPITAL").sum()))
    invalid = w[w["status"] == "INVALID_DATA"]
    if len(invalid):
        return TwrResult("RETURN_UNAVAILABLE", None, first_invalid_date=invalid.index[0],
                         first_invalid_reason=invalid["reason"].iloc[0], **base)
    if w["status"].isin(["NO_CAPITAL", "LOW_CAPITAL"]).all():
        return TwrResult("NO_INVESTMENT", None, **base)
    return TwrResult("CALCULATED", float(w["factor"].prod() - 1.0), **base)


def subperiods(returns: pd.DataFrame, anchor, end) -> pd.DataFrame:
    """Subperiod view of the same window: flow-free calculated days merged into blocks.

    A block of consecutive calculated days with no inflow or outflow has return
    ``V[last] / V[before first] - 1`` (the daily factors telescope). Each flow day, flat day
    and invalid day is its own block. Linking the blocks must equal linking the days; the
    test suite checks this reconciliation.
    """
    anchor, end = pd.Timestamp(anchor), pd.Timestamp(end)
    w = returns.loc[(returns.index > anchor) & (returns.index <= end)]
    blocks, current = [], None
    for date, row in w.iterrows():
        quiet = row["status"] == "CALCULATED" and row["inflow"] == 0 and row["outflow"] == 0 \
            and row["begin_value"] > 0
        if quiet and current is not None and current["kind"] == "quiet":
            current.update(end=date, end_value=row["end_value"])
            continue
        if current is not None:
            blocks.append(current)
        if quiet:
            current = dict(kind="quiet", start=date, end=date, begin_value=row["begin_value"],
                           end_value=row["end_value"])
        else:
            current = dict(kind="flow" if row["status"] == "CALCULATED" else row["status"].lower(),
                           start=date, end=date, begin_value=row["begin_value"],
                           end_value=row["end_value"], factor=row["factor"])
    if current is not None:
        blocks.append(current)
    out = pd.DataFrame(blocks)
    if out.empty:
        return out
    quiet = out["kind"] == "quiet"
    out.loc[quiet, "factor"] = out.loc[quiet, "end_value"] / out.loc[quiet, "begin_value"]
    out["block_return"] = out["factor"] - 1.0
    return out


def annualise(r: float | None, days: int) -> float | None:
    """Actual/365 annualisation, for back-end use only (the UI shows periodic returns).

    Returns ``None`` for non-positive elapsed days, a non-positive growth factor or a
    non-finite result.
    """
    if r is None or days <= 0 or not np.isfinite(r) or 1.0 + r <= 0:
        return None
    try:
        out = (1.0 + r) ** (365.0 / days) - 1.0
    except OverflowError:
        return None
    return out if np.isfinite(out) else None
