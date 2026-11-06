"""Data-quality controls that run beside the calculation and never change a number.

Most surprising returns come from inputs, not formulas: a deposit posted a day after the
shares it paid for, a flow on a day with no value snapshot, a tiny capital base. These
checks make such days visible to the data team.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def unexplained_changes(daily: pd.DataFrame, threshold: float = 0.5, min_capital: float = 1_000_000) -> pd.DataFrame:
    """Days where the value moved much more than the flows explain.

    ``unexplained = V[t] - V[t-1] - net_flow[t]`` is the day's market move plus any missing or
    misdated flow. Relative to ``max(V[t-1] + inflow, min_capital)`` it should look like a
    plausible daily return. ``LIKELY_LATE_FLOW`` marks a large unexplained rise followed the
    next day by an inflow of about the same size (the value already contained a deposit
    that was posted one day later).
    """
    v = daily["total_value"]
    unexplained = v.diff() - daily["net_flow"]
    base = np.maximum(v.shift(1) + daily["inflow"], min_capital)
    rel = unexplained / base
    out = pd.DataFrame({"unexplained": unexplained, "relative": rel})
    out = out[rel.abs() > threshold].copy()
    nxt_in = daily["inflow"].shift(-1)
    out["code"] = "LARGE_UNEXPLAINED_CHANGE"
    late = (out["unexplained"] > 0) & (
        (nxt_in.reindex(out.index) - out["unexplained"]).abs() <= 0.1 * out["unexplained"])
    out.loc[late, "code"] = "LIKELY_LATE_FLOW"
    return out


def control_report(returns: pd.DataFrame, horizons: pd.DataFrame | None = None,
                   warnings: list[str] | None = None, big_move: float = 0.5) -> dict:
    """Counters to review after every run (none of them changes a result)."""
    r = returns["daily_return"]
    report = {
        "low_capital_days": int((returns["status"] == "LOW_CAPITAL").sum()),
        "invalid_days": int((returns["status"] == "INVALID_DATA").sum()),
        "days_above_50pct_move": int((r.abs() > big_move).sum()),
        "loss_floor_days": int((returns["reason"] == "LOSS_EXCEEDS_CAPITAL").sum()),
        "flows_on_stale_values": sum("FLOW_ON_STALE_VALUE" in w for w in (warnings or [])),
    }
    if horizons is not None and "years_link_to_all" in horizons.attrs:
        report["years_link_to_all"] = bool(horizons.attrs["years_link_to_all"])
    return report
