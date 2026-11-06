"""When a number is shown, shown with a warning, or hidden.

The policy only controls display: the calculated value is always kept, together with the
display state and the reason code. Each horizon is judged on its own; a hidden 1Y does not
hide the 1M.

Order of checks (the first match wins):

1. Status rules: a value that was not calculated is never shown as 0. It gets a text such
   as "Insufficient history" or "No investment during this period".
2. Validation rules: results that are known to be unreliable are hidden (for example a TWR
   of -100% or worse, a zero-length period, or a wealth change whose four card numbers do
   not add up).
3. Value bands: four configurable limits per horizon split the value into NORMAL, WARNING
   (shown with "!") and HIDDEN. Comparisons use the unrounded decimal value.

The default bands below are **illustrative**. In the real product they were calibrated
on the full output distribution with the method in :func:`calibrate_bands` and must be
recalibrated when market conditions change.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

NORMAL, WARNING, HIDDEN, EMPTY = "NORMAL", "WARNING", "HIDDEN", "EMPTY"

MESSAGES = {
    "TWR_WARNING": "The calculated return for this period is unusual and may be affected by calculation limits.",
    "TWR_HIDDEN": "The return for this period cannot be shown at the moment.",
    "WC_WARNING": "The calculated wealth change for this period is unusual and may be affected by incomplete data or calculation limits.",
    "WC_HIDDEN": "The wealth change for this period cannot be shown at the moment.",
    "INSUFFICIENT_HISTORY": "Insufficient history",
    "NO_INVESTMENT": "No investment during this period",
    "RETURN_UNAVAILABLE": "The return for this period cannot be calculated.",
    "NO_ELAPSED_TIME": "The period has no elapsed time.",
}


@dataclass(frozen=True)
class Bands:
    """Four limits on a decimal value: hide below, warn below, warn above, hide above."""

    hide_below: float
    warn_below: float
    warn_above: float
    hide_above: float

    def classify(self, value: float) -> str:
        if value < self.hide_below or value > self.hide_above:
            return HIDDEN
        if value < self.warn_below or value > self.warn_above:
            return WARNING
        return NORMAL


# Illustrative defaults for periodic (non-annualised) returns, as decimals.
TWR_BANDS = {
    "1M": Bands(-0.60, -0.30, 1.00, 2.50),
    "3M": Bands(-0.60, -0.35, 1.50, 3.00),
    "6M": Bands(-0.65, -0.40, 2.50, 5.00),
    "1Y": Bands(-0.70, -0.45, 3.00, 6.00),
    "default": Bands(-0.75, -0.50, 4.00, 8.00),
}
MWR_BANDS = TWR_BANDS  # temporary: reuse the TWR bands until MWR has its own calibration
WC_BANDS = {           # applied to the hidden ratio R, not to the rial amount
    "1M": Bands(-0.55, -0.35, 1.00, 2.00),
    "3M": Bands(-0.55, -0.35, 1.50, 3.00),
    "6M": Bands(-0.55, -0.35, 3.00, 5.00),
    "1Y": Bands(-0.60, -0.40, 4.00, 6.00),
    "default": Bands(-0.65, -0.45, 5.00, 8.00),
}


@dataclass(frozen=True)
class Decision:
    state: str
    code: str
    message: str = ""
    value: float | None = None


def _bands(table, horizon):
    return table.get(horizon, table["default"])


def _status_decision(status: str) -> Decision | None:
    if status == "CALCULATED":
        return None
    return Decision(EMPTY if status in ("INSUFFICIENT_HISTORY", "NO_INVESTMENT") else HIDDEN,
                    status, MESSAGES.get(status, MESSAGES["RETURN_UNAVAILABLE"]))


def return_display(status: str, value: float | None, horizon: str, days: int,
                   bands: dict = TWR_BANDS, prefix: str = "TWR", reason: str | None = None) -> Decision:
    """Display decision for a TWR or MWR value.

    An MWR solved with several valid roots (``reason == "MULTIPLE_ROOTS"``) is never shown
    as plainly normal: it gets at least a warning.
    """
    d = _status_decision(status)
    if d:
        return d
    if value is None or not np.isfinite(value):
        return Decision(HIDDEN, "NOT_A_NUMBER", MESSAGES["TWR_HIDDEN"])
    if value <= -1.0:
        return Decision(HIDDEN, "TOTAL_LOSS_OR_WORSE", MESSAGES["TWR_HIDDEN"], value)
    if days <= 0:
        return Decision(HIDDEN, "ZERO_LENGTH_PERIOD", MESSAGES["TWR_HIDDEN"], value)
    state = _bands(bands, horizon).classify(value)
    if state == NORMAL and reason == "MULTIPLE_ROOTS":
        return Decision(WARNING, f"{prefix}_MULTIPLE_ROOTS", MESSAGES["TWR_WARNING"], value)
    code = {NORMAL: "WITHIN_NORMAL_BAND", WARNING: "OUTSIDE_NORMAL_BAND", HIDDEN: "OUTSIDE_DISPLAY_LIMITS"}[state]
    msg = {NORMAL: "", WARNING: MESSAGES["TWR_WARNING"], HIDDEN: MESSAGES["TWR_HIDDEN"]}[state]
    return Decision(state, f"{prefix}_{code}", msg, value)


def wealth_change_display(wc, horizon: str, bands: dict = WC_BANDS) -> Decision:
    """Display decision for a :class:`wealth_change.WealthChange`."""
    d = _status_decision(wc.status)
    if d:
        return d
    if any(x is None or not np.isfinite(x) for x in (wc.bv, wc.ev, wc.inflow, wc.outflow)):
        return Decision(HIDDEN, "MISSING_AMOUNT", MESSAGES["WC_HIDDEN"])
    if not np.isclose(wc.ev - wc.bv - wc.net_flow, wc.value) or not np.isclose(wc.net_flow, wc.inflow - wc.outflow):
        return Decision(HIDDEN, "IDENTITY_BROKEN", MESSAGES["WC_HIDDEN"], wc.value)
    if wc.days <= 0:
        return Decision(HIDDEN, "ZERO_LENGTH_PERIOD", MESSAGES["WC_HIDDEN"], wc.value)
    if wc.bv < 0 or wc.ev < 0:
        return Decision(HIDDEN, "NEGATIVE_VALUE", MESSAGES["WC_HIDDEN"], wc.value)
    base, back = wc.bv + wc.inflow, wc.ev + wc.outflow
    if base == 0 and back == 0:
        return Decision(NORMAL, "NO_BASE_NO_EXIT", "", wc.value)
    if base <= 0 < back:
        return Decision(HIDDEN, "NO_BASE", MESSAGES["WC_HIDDEN"], wc.value)
    if back <= 0 < base:
        return Decision(HIDDEN, "TOTAL_LOSS", MESSAGES["WC_HIDDEN"], wc.value)
    state = _bands(bands, horizon).classify(wc.ratio)
    code = {NORMAL: "WITHIN_NORMAL_BAND", WARNING: "OUTSIDE_NORMAL_BAND", HIDDEN: "OUTSIDE_DISPLAY_LIMITS"}[state]
    msg = {NORMAL: "", WARNING: MESSAGES["WC_WARNING"], HIDDEN: MESSAGES["WC_HIDDEN"]}[state]
    return Decision(state, f"WC_{code}", msg, wc.value)


def compare_twr_mwr(twr: float | None, mwr: float | None, has_flows: bool,
                    tolerance: float = 0.005) -> Decision:
    """The "chart analysis" text next to the TWR and MWR bars.

    Hidden when either number is missing. The comparison is about the past period only and
    is not advice on when to deposit.
    """
    if twr is None or mwr is None:
        return Decision(EMPTY, "COMPARISON_HIDDEN")
    gap = mwr - twr
    if np.sign(twr) * np.sign(mwr) < 0 and abs(gap) > tolerance:
        msg = ("Your investments gained, but more of your money was in the account during the weaker part "
               "of the period, so your personal return is negative." if twr > 0 else
               "Your investments lost value overall, but more of your money was in the account during the "
               "stronger part of the period, so your personal return is positive.")
        return Decision(NORMAL, "OPPOSITE_SIGNS", msg, gap)
    if abs(gap) <= tolerance:
        if not has_flows:
            return Decision(NORMAL, "SIMILAR_NO_FLOWS", "With no deposits or withdrawals the two returns match.", gap)
        return Decision(NORMAL, "SIMILAR", "The timing of your deposits and withdrawals had little effect.", gap)
    if not has_flows:
        return Decision(NORMAL, "DIFFERENT_WITHOUT_FLOWS",
                        "No deposits or withdrawals, but purchase credit or days with very low capital make the two returns differ.", gap)
    if gap > 0:
        return Decision(NORMAL, "TIMING_HELPED", "More of your money was invested during the stronger part of the period.", gap)
    return Decision(NORMAL, "TIMING_HURT", "More of your money was invested during the weaker part of the period.", gap)


def calibrate_bands(returns, warn_share: float = 0.20, hide_share: float = 0.50, bins: int = 80,
                    tail_quantile: float = 0.02) -> Bands:
    """Derive the four limits from an output distribution.

    Method used for the real thresholds: the distribution of ``log(1 + R)`` has a body of
    genuine returns and a long, almost flat tail caused by calculation limits (tiny capital
    bases, unrecorded flows). The tail density is estimated from the outer part of the
    distribution and extrapolated inwards; the share of suspicious values in each bin is
    tail density / bin density. Moving out from the median, the warning limit is where that
    share first reaches ``warn_share`` (about 20%) and the hide limit where it reaches
    ``hide_share`` (about 50%). Round the limits and align them across horizons afterwards.
    """
    r = np.asarray(returns, dtype=float)
    x = np.log1p(r[np.isfinite(r) & (r > -1)])
    lo, hi = np.quantile(x, [0.001, 0.999])
    counts, edges = np.histogram(x, bins=bins, range=(lo, hi))
    centres = 0.5 * (edges[:-1] + edges[1:])
    med = np.median(x)
    limits = {}
    for side in ("low", "high"):
        mask = centres < med if side == "low" else centres > med
        idx = np.where(mask)[0]
        idx = idx[::-1] if side == "low" else idx           # from the median outwards
        outer = counts[idx][-max(2, int(len(idx) * 0.25)):]
        tail = max(float(np.median(outer)), 1e-9)
        share = np.clip(tail / np.maximum(counts[idx], 1e-9), 0, 1)
        warn = next((centres[i] for i, s in zip(idx, share) if s >= warn_share), centres[idx[-1]])
        hide = next((centres[i] for i, s in zip(idx, share) if s >= hide_share), centres[idx[-1]])
        limits[side] = (float(np.expm1(warn)), float(np.expm1(hide)))
    return Bands(limits["low"][1], limits["low"][0], limits["high"][0], limits["high"][1])


def policy_table() -> list[dict]:
    """The rules as data, in evaluation order (used for docs/display-policy.md)."""
    return [
        dict(order=1, metric="all", code="INSUFFICIENT_HISTORY / NO_INVESTMENT", state=EMPTY,
             rule="status is not CALCULATED because there is no history or no capital", text="status text, never 0%"),
        dict(order=1, metric="all", code="RETURN_UNAVAILABLE / NO_ELAPSED_TIME", state=HIDDEN,
             rule="status is not CALCULATED because data or the solver failed", text=MESSAGES["RETURN_UNAVAILABLE"]),
        dict(order=2, metric="TWR, MWR", code="TOTAL_LOSS_OR_WORSE", state=HIDDEN, rule="value <= -100%", text=MESSAGES["TWR_HIDDEN"]),
        dict(order=2, metric="all", code="ZERO_LENGTH_PERIOD", state=HIDDEN, rule="effective start equals end", text="hidden"),
        dict(order=2, metric="WC", code="MISSING_AMOUNT", state=HIDDEN, rule="BV, EV, inflows or outflows missing", text=MESSAGES["WC_HIDDEN"]),
        dict(order=2, metric="WC", code="IDENTITY_BROKEN", state=HIDDEN, rule="BV + gain + net flow != EV", text=MESSAGES["WC_HIDDEN"]),
        dict(order=2, metric="WC", code="NEGATIVE_VALUE", state=HIDDEN, rule="BV or EV below zero", text=MESSAGES["WC_HIDDEN"]),
        dict(order=2, metric="WC", code="NO_BASE", state=HIDDEN, rule="BV + inflows = 0 but EV + outflows > 0", text=MESSAGES["WC_HIDDEN"]),
        dict(order=2, metric="WC", code="TOTAL_LOSS", state=HIDDEN, rule="EV + outflows = 0 but BV + inflows > 0", text=MESSAGES["WC_HIDDEN"]),
        dict(order=2, metric="WC", code="NO_BASE_NO_EXIT", state=NORMAL, rule="both bases are 0: R undefined, amount shown", text=""),
        dict(order=3, metric="all", code="OUTSIDE_NORMAL_BAND", state=WARNING, rule="between warn and hide limits", text=MESSAGES["TWR_WARNING"]),
        dict(order=3, metric="MWR", code="MULTIPLE_ROOTS", state=WARNING, rule="several rates solve the MWR equation", text=MESSAGES["TWR_WARNING"]),
        dict(order=3, metric="all", code="OUTSIDE_DISPLAY_LIMITS", state=HIDDEN, rule="beyond the hide limits", text=MESSAGES["TWR_HIDDEN"]),
        dict(order=4, metric="TWR vs MWR", code="OPPOSITE_SIGNS", state=NORMAL, rule="TWR and MWR have opposite signs",
             text="explanation box: timing of deposits drove the personal return the other way"),
    ]
