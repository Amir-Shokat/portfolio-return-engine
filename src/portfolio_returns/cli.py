"""Command line for portfolio return analysis."""

from __future__ import annotations

import argparse
import sys

import pandas as pd

from .dates import format_date
from .engine import analyse, format_table
from .horizons import EXTENDED, STANDARD
from .twr import MIN_CAPITAL_DEFAULT


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="portfolio-returns",
                                description="TWR, MWR and wealth change per horizon for one account.")
    p.add_argument("--transactions", required=True, help="CSV: txn_id,date,type,amount[,side,ref,symbol,description]")
    p.add_argument("--values", required=True, help="CSV: date,cash,holdings[,options] (end of day, currency units)")
    p.add_argument("--as-of", required=True, help="reporting date in ISO format, e.g. 2026-10-22")
    p.add_argument("--min-capital", type=float, default=MIN_CAPITAL_DEFAULT, help="minimum start-of-day capital in currency units")
    p.add_argument("--history-policy", choices=["all_since_entry", "nearest_only"], default="all_since_entry")
    p.add_argument("--extended", action="store_true", help="also show 3Y and 5Y")
    p.add_argument("--years", action="store_true", help="also show each calendar year")
    p.add_argument("--audit", help="write the classified transaction audit to this CSV")
    p.add_argument("--daily", help="write the daily table with returns to this CSV")
    p.add_argument("--csv", help="write the horizon table to this CSV")
    a = p.parse_args(argv)

    rep = analyse(pd.read_csv(a.transactions), pd.read_csv(a.values), a.as_of,
                  horizons=EXTENDED if a.extended else STANDARD, min_capital=a.min_capital,
                  history_policy=a.history_policy)
    st = rep.audit["status"].value_counts()
    print(f"As of {format_date(rep.as_of)}; amounts in currency units; returns not annualised")
    print(f"Transactions: {int(st.get('external', 0))} external, {int(st.get('internal', 0))} internal, "
          f"{int(st.get('snapshot', 0))} snapshots, {int(st.get('unmapped', 0))} unmapped, "
          f"{int(st.get('invalid', 0))} invalid, {int(st.get('duplicate', 0))} duplicates ignored")
    print()
    print(format_table(rep))
    if a.years and len(rep.years):
        print()
        yr = rep.years.copy()
        print(f"{'Year':<6} {'TWR':>10} {'MWR':>10} {'Wealth change':>16}")
        for _, r in yr.iterrows():
            tag = " (to date)" if r["year_to_date"] else ""
            twr = "" if r["twr"] is None or pd.isna(r["twr"]) else f"{r['twr']:+.2%}"
            mwr = "" if r["mwr"] is None or pd.isna(r["mwr"]) else f"{r['mwr']:+.2%}"
            wc = "" if r["wc"] is None or pd.isna(r["wc"]) else f"{r['wc']:,.0f}"
            print(f"{r['horizon']:<6} {twr:>10} {mwr:>10} {wc:>16}{tag}")
        if "years_link_to_all" in rep.horizons.attrs:
            print(f"Calendar years link to ALL: {rep.horizons.attrs['years_link_to_all']}")
    if rep.warnings or rep.credit_issues:
        print()
        for w in rep.warnings:
            print(f"warning: {w}")
        for i in rep.credit_issues:
            print(f"credit: {i.date.date()} {i.code} {i.message}")
    print()
    print("Controls: " + ", ".join(f"{k}={v}" for k, v in rep.controls.items()))
    if a.audit:
        rep.audit.to_csv(a.audit, index=False)
    if a.daily:
        rep.daily.join(rep.returns[["daily_return", "status", "reason", "factor"]]).to_csv(a.daily)
    if a.csv:
        rep.horizons.to_csv(a.csv, index=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
