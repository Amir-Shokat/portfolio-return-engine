# Methodology

This page explains the three numbers the engine produces for each horizon, and the data
conventions they share. Code references point to `src/portfolio_returns/`.

## The three numbers and the question each answers

| Number | Question | Unit |
|---|---|---|
| Time-weighted return (TWR) | How well did the investments perform, regardless of when money came and went? | % of the period, not annualised |
| Money-weighted return (MWR) | What return did *this investor* earn on the money they actually had in the account? | % of the period (annual rate kept for the back end) |
| Wealth change | How many rials did the investments gain or lose, after removing deposits and withdrawals? | rials |

TWR is the right number to judge a portfolio or a strategy, because a large deposit just
before a fall does not punish it. MWR is the investor's own experience, and it does react to
timing. Wealth change is not a rate at all: it is an amount, so it stays defined when a rate
is not (for example when the account started from zero inside the period).

## Shared conventions

**Account boundary.** The measured account is cash, holdings, the net value of options and,
under the credit method, active purchase credit:

    V[t] = cash[t] + holdings[t] + net_option_value[t] + active_credit[t]

**External flows.** Only money or securities crossing that boundary are flows. A purchase,
a sale, a fee, a dividend credited to the account's cash, bonus shares or a rights allocation
are internal: they change the composition of the account, not its owner's contribution. The
full rule table is in [transaction-mapping.md](transaction-mapping.md).

**Sign.** The account perspective is used everywhere except inside the IRR solver: money in
is an inflow (+), money out is an outflow (-). The solver uses the investor perspective
(contribution negative). The conversion happens once, at the solver boundary.

**Gross flows.** Inflows and outflows are summed separately for each day. A deposit and a
withdrawal of the same size on the same day are *not* netted to zero. Netting hides a day on
which the capital at work changed, and gives a different (wrong) daily return.

**End-of-day values.** One value per calendar day, after the market closes. Levels (cash,
holdings, options) carry forward over weekends and holidays; flows never do. An explicitly
missing value is unknown, not zero and not carried forward. See [edge-cases.md](edge-cases.md).

**Windows.** Every horizon is a window `(anchor, end]`. The anchor is a closing value (the
starting value BV); the first included day is the day after it; the end date is included.
TWR, MWR and wealth change for one horizon always use the same anchor and end, and the
cumulative chart starts at 0% on the anchor.

## Time-weighted return

Only one value per day is known, so the timing of flows inside a day is an assumption. The
engine uses the convention of the open-source Portfolio Performance application:
**inflows at the beginning of the day, outflows at the end of the day**.

    D[t] = V[t-1] + Inflow[t]                   capital at work during day t
    r[t] = (V[t] + Outflow[t]) / D[t] - 1

Daily returns are linked geometrically:

    TWR(anchor, end) = prod over t in (anchor, end] of (1 + r[t]) - 1

Why this convention: a deposit made in the morning is invested for the day, so it belongs in
the denominator; a withdrawal paid out at the end of the day earned that day's return, so it
is added back to the closing value. The older "all flows at end of day, netted" formula
`r = (V[t] - CF[t] - V[t-1]) / V[t-1]` puts a morning deposit into the numerator as if it were
profit-neutral but leaves it out of the capital base; it overstates returns on deposit days
and cannot see same-day opposite flows. The worked comparison is in [decisions.md](decisions.md).

Each day gets a status. Days that cannot be measured are kept visible instead of being
turned into fake zero returns:

| Status | When | Effect on the horizon |
|---|---|---|
| `BASELINE` | first row (no earlier value) | factor 1 |
| `CALCULATED` | normal day, including 0% and -100% | factor `1 + r` |
| `CALCULATED` + `LOSS_EXCEEDS_CAPITAL` | loss larger than capital (possible with debt) | floored at -100% |
| `NO_CAPITAL` | values and flows all zero | factor 1 (chart flat) |
| `LOW_CAPITAL` | `D <= 0` or `0 < D < min_capital` | factor 1 (chart flat), counted |
| `INVALID_DATA` | unknown value, unknown flow, duplicate record, credit inconsistency | factor unknown: every horizon containing the day is blocked |

The minimum-capital guard exists because a few thousand rials left in an emptied account
can show +300% in a day when a dividend or a tiny price move lands on them. Those days carry
no economic information. The default is 1,000,000 rials; it is a parameter.

The **cumulative chart** is rebased to 0% on the anchor of the selected horizon, so the
end of the line equals the horizon TWR. The anchor's own daily return belongs to the
previous interval and is not used. From the first invalid day the line stops; it is never
bridged across unknown performance.

`twr.subperiods` gives the classic subperiod view of the same window (flow-free stretches
merged into one block each). Linking the blocks reproduces the daily linking exactly; this is
a test, not a second method.

## Money-weighted return (XIRR)

For the window `(anchor, end]` the dated cash flows, investor perspective, are:

    anchor date    -BV
    each day t     Outflow[t] - Inflow[t]
    end date       +EV

Flows on the anchor date are already inside BV and are not added again. Flows on the end
date are added and EV is added as well, because EV is the value after those flows.

The engine solves the dated IRR equation on an Actual/365 basis (the spreadsheet `XIRR`
equation):

    sum_i C_i / (1 + x) ** ((d_i - d_0).days / 365) = 0

and shows the periodic rate for the invested span, so it can be compared with the TWR of the
same window:

    MWR_period = (1 + x) ** (invested_days / 365) - 1

`invested_days` runs from the first to the last non-zero flow. It equals the window when BV
and EV are both non-zero, and is shorter when the account started from zero or was emptied
inside the window, so a one-month result is not stretched over a year.

### Solver

A plain Newton iteration from a 10% guess (what spreadsheets do) fails on exactly the cases
that matter in a retail app:

* short windows with large moves have enormous annual rates (+10% in two days is about
  3.6e7 % a year); Newton overshoots or crosses `x <= -1`;
* flows that change sign more than once can have several valid roots, and Newton returns
  whichever one it falls into without saying so.

`xirr.xirr` therefore works on `y = log(1 + x)` (defined for every rate above -100%), scans
a wide grid of `y` for sign changes, refines each bracket with a safeguarded Newton step
(bisection whenever Newton leaves the bracket), checks a scaled NPV residual and reports
every root found. Its statuses are explicit and a rate is never invented:

| Status | Meaning |
|---|---|
| `OK` | one root, residual check passed |
| `MULTIPLE_ROOTS` | several rates solve the equation; the one closest to 0% is returned and all are listed |
| `NO_SIGN_CHANGE` | all flows have the same sign |
| `NO_ELAPSED_TIME` | all flows on one date |
| `NO_ROOT` | no rate in the search range solves the equation |
| `NOT_CONVERGED` | residual check failed |
| `INVALID_INPUT` | missing dates, non-finite amounts |

`xirr.spreadsheet_xirr` is the plain Newton version, kept to show where the two disagree.

### Boundary rules for MWR

1. `|BV| < min_capital`: BV is treated as 0 and the period starts at the first real flow.
   Without this, a few rials left for eleven months, then a deposit and a 10% month, give
   about +215% for "1Y" instead of +10%.
2. `BV <= -min_capital` (real debt at the start): kept as it is.
3. Nothing came back (no positive flow): -100%, reason `TOTAL_LOSS`, or
   `LOSS_EXCEEDS_CAPITAL` when EV is negative.
4. Nothing was put in (no negative flow): `NO_INVESTMENT`, no number.
5. An `INVALID_DATA` day in the window: `RETURN_UNAVAILABLE`.
6. Solver failure: `RETURN_UNAVAILABLE` with the solver status. Several roots: the root
   closest to 0% with a `MULTIPLE_ROOTS` reason, and the display policy adds a warning.

## Wealth change

    net_flow       = sum(inflows) - sum(outflows)   over (anchor, end]
    wealth_change  = EV - BV - net_flow

so the four numbers on the card always add up: `BV + wealth_change + net_flow = EV`.
There is no division, so neither the minimum-capital guard nor the -100% floor applies, and
every day counts. A missing value *inside* the window does not block it (only the two
boundary values matter); an unknown flow (unmapped transaction) does, because the net flow
would then be wrong.

The waterfall splits the net flow into customer deposits and withdrawals, purchase credit,
and other boundary crossings (securities transfers, dividends paid out, rights). Credit
adjustments must not appear to the investor as bank deposits.

A hidden ratio `R = (EV + outflows) / (BV + inflows) - 1` is computed only for the display
policy (to decide whether the amount is plausible); it is never shown.

## Horizons and calendars

| Horizon | Anchor |
|---|---|
| 1M, 3M, 6M, 1Y (and 3Y, 5Y with `--extended`) | the same day N calendar months before the as-of date, clipped to the month end (31 March minus one month is 28 February) |
| YTD | the last day of Esfand of the previous Jalali year, so the window starts on 1 Farvardin |
| ALL | entry: the last known-zero close before the first funded day, else the first funded close |
| Jalali years (`--years`) | each Jalali year from the entry year; the current year is to date |

Calendar months are never replaced by 30/90/180/365 fixed days. Month arithmetic can run on
the Gregorian or the Jalali calendar (`--calendar`). Jalali dates are converted exactly
(1 Farvardin 1405 = 21 March 2026).

When the history is shorter than a horizon there are two policies:

* `all_since_entry` (default): every longer horizon shows the since-entry number, so 6M,
  1Y and ALL may be equal;
* `nearest_only`: only the shortest incomplete horizon shows since entry, the longer ones
  show "Insufficient history". An exact anniversary stays in the lower bucket.

When the first value row already contains investments (history starts mid-life), ALL is
labelled since entry with a note that earlier performance is unknown. A zero opening value is
never invented.

Consistency check: linking the TWR of the Jalali years must reproduce the ALL TWR. The
engine computes this on every run (`years_link_to_all`).

## Annualisation

The app shows periodic returns. `twr.annualise` (Actual/365) exists for back-end use only and
returns nothing for non-positive days or a non-positive growth factor. Annualising a
two-week return is misleading and is not shown.
