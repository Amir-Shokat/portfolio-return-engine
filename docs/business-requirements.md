# Business requirements: portfolio performance cards

Product requirements for the three performance cards of a retail trading app's portfolio
screen: return (TWR), personal return (MWR) and wealth change. Written as a product owner
would write them for engineering, design, QA and the data team. Specific to this public
package: production thresholds, system names and figures are left out.

## Problem

Investors judged their performance from a single "profit" figure that mixed market moves with
their own deposits and withdrawals. A deposit looked like a gain; a withdrawal like a loss.
Support tickets about "wrong returns" were frequent, and the two existing return numbers
(time-weighted and money-weighted) were computed by different teams with different
definitions of a cash flow, so they often disagreed for reasons nobody could explain.

## Goals

1. One definition of the account, of an external flow and of a horizon, shared by all three
   numbers.
2. Numbers an investor can trust: when a value is unreliable it is flagged or hidden with a
   reason, never shown as a confident figure and never shown as 0%.
3. Every number traceable to the transactions behind it.

Non-goals: tax reporting, performance of accounts outside the brokerage account, advice on
when to invest.

## Users and questions

| User | Question | Card |
|---|---|---|
| Investor | "How did my picks do?" | Return (TWR) and its cumulative chart |
| Investor | "What did I actually earn on my money?" | Personal return (MWR) |
| Investor | "How many rials did I make, apart from what I put in?" | Wealth change |
| Support | "Why does the app show this number?" | Audit and reason codes |
| Data team | "Which accounts have unreliable inputs?" | Control counters and quality report |

## Functional requirements

**R1. Horizons.** 1M, 3M, 6M, 1Y, YTD (Jalali year) and since entry. Calendar months with
month-end clipping. Requested and effective start dates are both available, and the effective
dates are shown to the investor.

**R2. Short history.** A horizon longer than the investor's history shows the since-entry
result with a "since entry" label, or "Insufficient history" under the stricter policy. It
never shows a number for a period the investor was not invested.

**R3. Flows.** External flows are defined by the transaction mapping table. A transaction
type that is not in the table blocks the affected horizons until it is mapped. It is never
guessed.

**R4. TWR.** Daily, inflow at the start of the day and outflow at the end, gross same-day
flows, geometrically linked, not annualised in the UI. The cumulative chart starts at 0% on
the first day of the selected horizon and ends at the horizon value.

**R5. MWR.** Dated IRR, Actual/365, shown as the return for the invested span of the horizon.
Solver failures produce a status, not a number. Multiple roots produce a warning.

**R6. Wealth change.** `EV - BV - net flow`, with the four card rows (start value, gain or
loss, net deposits and withdrawals, end value) adding up exactly. Deposits and withdrawals are
also shown separately; credit adjustments are not shown as deposits.

**R7. Display policy.** Each value is shown, shown with a warning, hidden or replaced by a
status text according to [display-policy.md](display-policy.md). The policy is configurable per
horizon and never changes the stored value.

**R8. TWR versus MWR.** When both are displayable, a one-sentence explanation of the
difference, describing the past only.

**R9. Credit and options.** Included in the account value under the shared method in
[credit-and-options.md](credit-and-options.md).

**R10. Audit.** For any account and horizon, the engine can output the classified
transactions, the daily table and the reason codes.

## Acceptance criteria

* AC1. For an account with no flows, TWR and MWR are equal (to rounding) for every horizon.
* AC2. For every displayed wealth change, start + gain + net flow = end, to the rial.
* AC3. A deposit and a withdrawal of the same size on the same day change the TWR of that day
  compared with no flows, unless the market did not move.
* AC4. The linked TWR of the Jalali years equals the since-entry TWR.
* AC5. An unmapped transaction blocks exactly the horizons whose window contains its date.
* AC6. Buying with credit on a day with no price change gives a 0% daily return.
* AC7. No horizon shows 0% for a value that was not calculated.
* AC8. MWR for a two-day window with a large move is calculated (or carries an explicit status),
  never a solver crash.
* AC9. Changing a display band changes only `*_display` and `*_code`.

Each criterion maps to tests listed in [validation.md](validation.md) and to scenarios in
[features/](features/).

## Illustrative release measurement

Track calculation success and displayable rate against the expected account–horizon
population, together with invalid days, low-capital days, loss-floor days, flows on stale
values and yearly-linking checks. Targets, tolerances, ownership and release authority
must be agreed for the adopting product. This repository contains no production
measurements, target achievement or release approval.

## Open questions at hand-off

* MWR needs its own display bands; it reuses the TWR bands for now.
* Policy for the negative-cash exception list (see credit document).
* Whether a fully withdrawn account should show its closed result, and for how long.
* Freshness rule when the as-of date has no value yet (today the horizon is not shown).
