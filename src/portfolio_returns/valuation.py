"""Daily table: one row per calendar day with total value and gross external flows.

    total_value = cash (raw, may be negative) + holdings + net option value + active credit

Levels and events are treated differently:

* **Levels** (cash, holdings, options) are states. A day without a new observation keeps
  the last one (forward fill), e.g. over the Saturday-Sunday weekend or Nowruz.
* **Events** (flows) are things that happened. A day without events has zero flow.
  Flows are never forward filled; that would invent money that never moved.

An explicitly missing value in an observed row is *unknown*, not carried forward, and
blocks the returns that need it. Conflicting duplicate rows for one date are quarantined.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .credit import CreditIssue, active_credit, effective_cash
from .dates import parse_date
from .transactions import TxnType, daily_flows

LEVELS = ["cash", "holdings", "options"]
FLOW_COLUMNS = ["inflow", "outflow", "net_flow", "deposits", "withdrawals", "credit_in",
                "credit_out", "other_in", "other_out"]


def read_values(values: pd.DataFrame) -> tuple[pd.DataFrame, set, list[str]]:
    """Validate the end-of-day values file. Returns (values by date, conflicting dates, warnings)."""
    df = values.copy()
    df.columns = [str(c).strip().lower() for c in df.columns]
    missing = {"date", "cash", "holdings"} - set(df.columns)
    if missing:
        raise ValueError(f"values missing columns {sorted(missing)}")
    if "options" not in df:
        df["options"] = 0.0
    df["date"] = [parse_date(d) for d in df["date"]]
    for c in LEVELS:
        df[c] = pd.to_numeric(df[c], errors="coerce")
        df.loc[~np.isfinite(df[c].astype(float)), c] = np.nan
    warnings = []
    conflicts = set()
    dup = df[df["date"].duplicated(keep=False)]
    for d, grp in dup.groupby("date"):
        if len(grp[LEVELS].drop_duplicates()) > 1:
            conflicts.add(d)
            warnings.append(f"{d.date()}: conflicting duplicate value rows quarantined")
    df = df.drop_duplicates("date", keep="last").set_index("date").sort_index()
    df.loc[list(conflicts), LEVELS] = np.nan
    return df[LEVELS], conflicts, warnings


def build_daily_table(values: pd.DataFrame, audit: pd.DataFrame, as_of=None,
                      floor_cash: pd.Series | None = None) -> tuple[pd.DataFrame, list[str], list[CreditIssue]]:
    """Build the daily table from end-of-day values and the classified transaction audit.

    Returns ``(daily, warnings, credit_issues)``. ``daily`` is indexed by date from the first
    value date to ``as_of`` (or the last value date). Columns: raw and effective cash,
    holdings, options, credit, total_value, value_source_date, the gross flow columns,
    ``blocked`` (unmapped/invalid transactions that day) and ``flag`` (a reason code when
    the day's inputs are unknown or inconsistent).
    """
    vals, conflicts, warnings = read_values(values)
    if vals.empty:
        raise ValueError("values file has no rows")
    end = parse_date(as_of) if as_of is not None else vals.index.max()
    calendar = pd.date_range(vals.index.min(), max(end, vals.index.min()), freq="D", name="date")
    observed = vals.index

    # Closing snapshots repair a zero cash balance on the same date only.
    snaps = audit[(audit["status"] == "snapshot") & (audit["txn_type"] == TxnType.CLOSING_BALANCE.value)]
    patched = []
    for d, grp in snaps.groupby("date"):
        if d in vals.index and vals.at[d, "cash"] == 0:
            vals.at[d, "cash"] = float(grp["amount"].iloc[-1])
            patched.append(d)
            warnings.append(f"{d.date()}: zero cash replaced by closing snapshot {vals.at[d, 'cash']:,.0f}")

    daily = vals.reindex(calendar)
    present = calendar.isin(observed)
    # Forward fill only across dates with no observation; explicit NaN in an observed row stays unknown.
    filled = vals.reindex(calendar).ffill()
    for c in LEVELS:
        daily[c] = daily[c].where(present, filled[c])
    src = pd.Series(calendar.where(present), index=calendar).ffill()
    daily["value_source_date"] = pd.to_datetime(src)
    daily["cash_raw"] = daily["cash"]
    daily["cash"] = effective_cash(daily["cash_raw"], floor_cash)

    credit, issues = active_credit(audit, calendar)
    daily["credit"] = credit
    daily["total_value"] = daily["cash"] + daily["holdings"] + daily["options"] + daily["credit"]

    flows = daily_flows(audit)
    outside = flows[(flows.index < calendar.min()) | (flows.index > calendar.max())]
    for d, row in outside.iterrows():
        if row["inflow"] or row["outflow"] or row["blocked"]:
            where = "before the first value date" if d < calendar.min() else "after the as-of date"
            warnings.append(f"{d.date()}: flow {where}; not included")
    flows = flows.reindex(calendar, fill_value=0.0).astype(float)
    for c in FLOW_COLUMNS + ["blocked"]:
        daily[c] = flows[c]

    flag = pd.Series(None, index=calendar, dtype=object)
    flag[daily[LEVELS].isna().any(axis=1)] = "MISSING_VALUATION"
    flag[calendar.isin(list(conflicts))] = "DUPLICATE_DAILY_RECORD"
    flag[daily["blocked"] > 0] = "UNMAPPED_TRANSACTION"
    for issue in issues:
        if issue.date in flag.index:
            flag[issue.date] = "CREDIT_INCONSISTENT"
    daily["flag"] = flag

    stale = (~present) & ((daily["inflow"] > 0) | (daily["outflow"] > 0))
    for d in calendar[stale]:
        warnings.append(f"{d.date()}: FLOW_ON_STALE_VALUE - flow on a day without a value snapshot; "
                        "the carried value may not include it")
    daily.attrs["patched_closing"] = patched
    cols = ["cash_raw", "cash", "holdings", "options", "credit", "total_value", "value_source_date",
            *FLOW_COLUMNS, "blocked", "flag"]
    return daily[cols], warnings, issues
