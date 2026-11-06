# Display policy

A calculated number is not automatically a number the investor should see. Most extreme
returns come from calculation limits (a tiny capital base, a flow that was posted a day late,
an unrecorded transfer), not from real performance. The display policy decides, per horizon
and per metric, whether a value is **shown**, **shown with a warning**, **hidden**, or replaced
by a **status text**.

The policy only controls display. The calculated value, its state and the reason code are
always kept (`twr_display`, `twr_code`, ... in the horizon table), so support and data teams
can see what was hidden and why. Each horizon is judged on its own: a hidden 1Y does not hide
the 1M.

Code: `src/portfolio_returns/display_policy.py`.

## States

| State | What the investor sees |
|---|---|
| `NORMAL` | the number |
| `WARNING` | the number with a "!" and a short explanation |
| `HIDDEN` | "The return for this period cannot be shown at the moment." |
| `EMPTY` | a status text such as "Insufficient history" or "No investment during this period" |

A value that was not calculated is **never shown as 0%**. Zero is a real result; "unknown"
and "not applicable" are different things and need different texts.

## Order of checks (first match wins)

1. **Status rules.** `INSUFFICIENT_HISTORY` and `NO_INVESTMENT` give `EMPTY` with a text.
   `RETURN_UNAVAILABLE` and `NO_ELAPSED_TIME` give `HIDDEN`.
2. **Validation rules.** Results known to be unreliable are hidden:

   | Code | Metric | Rule |
   |---|---|---|
   | `TOTAL_LOSS_OR_WORSE` | TWR, MWR | value <= -100% |
   | `ZERO_LENGTH_PERIOD` | all | effective start equals end |
   | `MISSING_AMOUNT` | WC | BV, EV, inflows or outflows missing |
   | `IDENTITY_BROKEN` | WC | BV + gain + net flow differs from EV |
   | `NEGATIVE_VALUE` | WC | BV or EV below zero |
   | `NO_BASE` | WC | BV + inflows = 0 but EV + outflows > 0 |
   | `TOTAL_LOSS` | WC | EV + outflows = 0 but BV + inflows > 0 |
   | `NO_BASE_NO_EXIT` | WC | both are 0: the ratio is undefined, the amount (0) is shown |

3. **Value bands.** Four limits per horizon split the value into `NORMAL`, `WARNING` and
   `HIDDEN`: hide below, warn below, warn above, hide above. Comparisons use the unrounded
   decimal value, so a value that rounds to the limit is still classified correctly.
   An MWR solved with several valid roots is never plainly normal: it is at least a warning.

Wealth change is an amount, so its bands are applied to the hidden ratio
`R = (EV + outflows) / (BV + inflows) - 1`, not to the rial figure.

## Default bands

Periodic (not annualised) returns, as decimals. **These numbers are illustrative.**
Calibrate and approve limits separately before adopting this demonstration.

| Horizon | Hide below | Warn below | Warn above | Hide above |
|---|---|---|---|---|
| 1M | -60% | -30% | +100% | +250% |
| 3M | -60% | -35% | +150% | +300% |
| 6M | -65% | -40% | +250% | +500% |
| 1Y | -70% | -45% | +300% | +600% |
| longer | -75% | -50% | +400% | +800% |

Wider limits for longer horizons are deliberate: +150% in a year is plausible on the Tehran
market, +150% in a month much less so.

MWR reuses the TWR bands for now. This is a temporary decision until MWR has its own
calibration (see [decisions.md](decisions.md)).

## How the limits are calibrated

`calibrate_bands()` implements the method used for the real thresholds:

1. Take the distribution of `log(1 + R)` over all accounts for one horizon. It has a body of
   genuine returns and a long, almost flat tail produced by calculation limits.
2. Estimate the tail density from the outer part of the distribution and extrapolate it
   inwards.
3. In each histogram bin, the share of suspicious values is tail density / bin density.
4. Moving out from the median, the warning limit is where that share first reaches about
   20% and the hide limit where it reaches about 50%.
5. Round the limits and align them across horizons so a longer horizon is never stricter.

Recalibrate when market conditions change: a strong bull year moves the body to the right.

## TWR versus MWR comparison text

The app shows TWR and MWR side by side with a short "chart analysis" sentence. It is hidden
when either number is not displayable. It describes the past period only and is not advice on
when to deposit.

| Code | Condition | Text |
|---|---|---|
| `OPPOSITE_SIGNS` | different signs, gap > 0.5 pp | explains that timing turned a gain into a personal loss (or the reverse) |
| `SIMILAR_NO_FLOWS` | gap <= 0.5 pp, no flows | the two returns match because there were no deposits or withdrawals |
| `SIMILAR` | gap <= 0.5 pp, with flows | timing had little effect |
| `DIFFERENT_WITHOUT_FLOWS` | gap > 0.5 pp, no flows | purchase credit or very-low-capital days make them differ |
| `TIMING_HELPED` / `TIMING_HURT` | MWR above / below TWR | more money was invested in the stronger / weaker part of the period |

## Acceptance criteria

* No horizon shows 0% (or 0 rials) for a value that was not calculated.
* Every hidden or flagged value has a reason code in the output.
* Changing a band changes only the display state, never the stored value.
* A hidden horizon does not change the state of any other horizon.
* For wealth change, the four card numbers (start, gain, net flow, end) always add up when
  shown.

Scenarios: [features/display_policy.feature](features/display_policy.feature).
