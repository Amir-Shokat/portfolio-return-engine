"""End-to-end run: transactions and daily values in, one result row per horizon out."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import display_policy as dp
from .dates import GREGORIAN, format_date, parse_date
from .horizons import STANDARD, Window, calendar_year_horizons, resolve_windows
from .mwr import horizon_mwr
from .quality import control_report, unexplained_changes
from .transactions import classify
from .twr import MIN_CAPITAL_DEFAULT, cumulative, daily_returns, horizon_twr
from .valuation import build_daily_table
from .wealth_change import wealth_change


@dataclass
class Report:
    as_of: pd.Timestamp
    audit: pd.DataFrame
    daily: pd.DataFrame
    returns: pd.DataFrame
    horizons: pd.DataFrame
    years: pd.DataFrame
    charts: dict = field(default_factory=dict)
    warnings: list = field(default_factory=list)
    credit_issues: list = field(default_factory=list)
    quality: pd.DataFrame | None = None
    controls: dict = field(default_factory=dict)


def evaluate_window(daily: pd.DataFrame, returns: pd.DataFrame, w: Window,
                    min_capital: float = MIN_CAPITAL_DEFAULT) -> tuple[dict, pd.Series | None]:
    """TWR, MWR, wealth change and display decisions for one resolved window."""
    row = dict(horizon=w.label, basis=w.basis, requested_anchor=w.requested_anchor, anchor=w.anchor,
               first_day=w.first_day, end=w.end, days=w.days, note=w.note)
    if not w.usable:
        status = w.basis
        empty = dp.Decision(dp.EMPTY if status in ("INSUFFICIENT_HISTORY", "NO_INVESTMENT") else dp.HIDDEN,
                            status, dp.MESSAGES.get(status, ""))
        row.update(twr=None, twr_status=status, mwr=None, mwr_status=status, mwr_reason=None,
                   mwr_annualised=None, wc=None, wc_status=status, bv=None, ev=None, inflow=None,
                   outflow=None, net_flow=None, twr_display=empty.state, twr_code=empty.code,
                   mwr_display=empty.state, mwr_code=empty.code, wc_display=empty.state, wc_code=empty.code,
                   comparison=None, low_capital_days=0)
        return row, None
    t = horizon_twr(returns, w.anchor, w.end)
    m = horizon_mwr(daily, returns, w.anchor, w.end, min_capital=min_capital)
    c = wealth_change(daily, w.anchor, w.end)
    td = dp.return_display(t.status, t.value, w.label, w.days, dp.TWR_BANDS, "TWR")
    md = dp.return_display(m.status, m.value, w.label, w.days, dp.MWR_BANDS, "MWR", reason=m.reason)
    wd = dp.wealth_change_display(c, w.label)
    has_flows = bool(c.status == "CALCULATED" and (c.inflow or c.outflow))
    cmp_ = dp.compare_twr_mwr(t.value if td.state in (dp.NORMAL, dp.WARNING) else None,
                              m.value if md.state in (dp.NORMAL, dp.WARNING) else None, has_flows)
    row.update(twr=t.value, twr_status=t.status, low_capital_days=t.low_capital_days,
               mwr=m.value, mwr_status=m.status, mwr_reason=m.reason, mwr_annualised=m.annualised,
               wc=c.value, wc_status=c.status, bv=c.bv, ev=c.ev,
               inflow=c.inflow if c.status == "CALCULATED" else None,
               outflow=c.outflow if c.status == "CALCULATED" else None,
               net_flow=c.net_flow if c.status == "CALCULATED" else None,
               twr_display=td.state, twr_code=td.code, mwr_display=md.state, mwr_code=md.code,
               wc_display=wd.state, wc_code=wd.code, comparison=cmp_.code)
    if t.status == "RETURN_UNAVAILABLE":
        row["note"] = (row["note"] + "; " if row["note"] else "") + \
            f"unknown data on {t.first_invalid_date.date()} ({t.first_invalid_reason})"
    chart = cumulative(returns, w.anchor, w.end) if t.status in ("CALCULATED", "RETURN_UNAVAILABLE") else None
    return row, chart


def analyse(transactions: pd.DataFrame, values: pd.DataFrame, as_of, *, horizons=STANDARD,
            min_capital: float = MIN_CAPITAL_DEFAULT, calendar: str = GREGORIAN,
            history_policy: str = "all_since_entry", floor_cash: pd.Series | None = None) -> Report:
    """Run the whole pipeline for one account.

    ``floor_cash`` is an optional boolean series by date marking days on which the account
    is on the negative-cash exception list (cash floored at zero).
    """
    as_of = parse_date(as_of)
    audit = classify(transactions)
    daily, warnings, issues = build_daily_table(values, audit, as_of=as_of, floor_cash=floor_cash)
    returns = daily_returns(daily, min_capital=min_capital)
    rows, charts = [], {}
    for w in resolve_windows(daily, as_of, horizons, calendar, history_policy):
        row, chart = evaluate_window(daily, returns, w, min_capital)
        rows.append(row)
        if chart is not None:
            charts[w.label] = chart
    table = pd.DataFrame(rows)
    year_rows = []
    for w in resolve_windows(daily, as_of, calendar_year_horizons(daily, as_of), calendar, history_policy):
        row, _ = evaluate_window(daily, returns, w, min_capital)
        row["year_to_date"] = bool(w.end is not None and w.end == as_of)
        year_rows.append(row)
    years = pd.DataFrame(year_rows)
    if len(years) and "ALL" in set(table["horizon"]):
        all_twr = table.set_index("horizon").at["ALL", "twr"]
        yt = years["twr"]
        if all_twr is not None and yt.notna().all():
            linked = float(np.prod(1 + yt.astype(float)) - 1)
            table.attrs["years_link_to_all"] = bool(np.isclose(linked, all_twr, rtol=1e-9, atol=1e-12))
    quality = unexplained_changes(daily, min_capital=min_capital)
    controls = control_report(returns, table, warnings)
    return Report(as_of, audit, daily, returns, table, years, charts, warnings, issues, quality, controls)


def format_table(report: Report) -> str:
    """Plain-text horizon table for the command line."""
    def pct(x):
        return "" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x:+.2%}"

    def amt(x):
        return "" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x:,.0f}"

    def shown(value, state, fmt):
        if state == dp.EMPTY:
            return "-"
        if state == dp.HIDDEN:
            return "hidden"
        return fmt(value) + (" !" if state == dp.WARNING else "")

    head = f"{'Horizon':<7} {'From':<10} {'To':<10} {'Basis':<12} {'TWR':>10} {'MWR':>10} {'Wealth change':>16}  Notes"
    lines = [head, "-" * len(head)]
    for _, r in report.horizons.iterrows():
        frm = format_date(r["first_day"]) if r["first_day"] is not None and not pd.isna(r["first_day"]) else ""
        to = format_date(r["end"]) if r["end"] is not None and not pd.isna(r["end"]) else ""
        notes = []
        if r["twr_display"] in (dp.HIDDEN, dp.EMPTY) and r["twr_status"] != "CALCULATED":
            notes.append(r["twr_status"].lower().replace("_", " "))
        if r.get("comparison") == "OPPOSITE_SIGNS":
            notes.append("TWR and MWR differ in sign: timing")
        if r.get("low_capital_days"):
            notes.append(f"{r['low_capital_days']} low-capital day(s) skipped")
        if r.get("mwr_reason") == "MULTIPLE_ROOTS":
            notes.append("MWR has several roots")
        lines.append(f"{r['horizon']:<7} {frm:<10} {to:<10} {r['basis'].lower():<12} "
                     f"{shown(r['twr'], r['twr_display'], pct):>10} {shown(r['mwr'], r['mwr_display'], pct):>10} "
                     f"{shown(r['wc'], r['wc_display'], amt):>16}  {'; '.join(notes)}")
    return "\n".join(lines)
