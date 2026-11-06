# Edge-case catalogue

Every case below came up while reconciling the app's returns with independent calculations,
or from investor tickets about numbers that "looked wrong". Each one has a rule and, where
marked, a test (`tests/`). Most surprising returns came from inputs, not from formulas.

## Flows and timing

| # | Case | Wrong result it caused | Rule | Test |
|---|---|---|---|---|
| F1 | Deposit and withdrawal of the same size on the same day | Netted to zero, so the capital at work that day was wrong | Gross inflow and outflow per day; inflow at start, outflow at end | `test_same_day_deposit_and_withdrawal_are_not_netted` |
| F2 | Deposit made in the morning and invested the same day | All-end-of-day formula put it in the numerator only: a large positive return on deposit days | Inflow joins the capital base at the start of the day | `test_inflow_at_start_of_day` |
| F3 | Withdrawal of most of the account | Return measured on the remaining dust | Outflow added back to the closing value | `test_outflow_at_end_of_day` |
| F4 | Shares bought the day before the deposit that paid for them was posted | Negative cash for a day, then a jump that looks like profit | Raw negative cash kept; quality check `LIKELY_LATE_FLOW` flags the pair | `test_late_deposit_is_flagged_by_quality_check` |
| F5 | Flow on a weekend or holiday (no value snapshot) | Carried value does not contain the flow | Flow counted on its date; warning `FLOW_ON_STALE_VALUE` | `test_levels_carry_forward_flows_do_not` |
| F6 | Flow before the first value date or after the as-of date | Silently dropped or double counted | Excluded with a warning | engine warnings |
| F7 | Flow on the anchor date | Counted twice (inside BV and as a flow) | Anchor-date flows are inside BV; end-date flows are counted | `test_anchor_flow_inside_bv_end_flow_added_with_ev` |

## Values

| # | Case | Rule | Test |
|---|---|---|---|
| V1 | No row for a weekend or holiday | Levels carry forward; flows are zero | `test_levels_carry_forward_flows_do_not` |
| V2 | Row present but a value is empty | Unknown, not zero, not carried: `MISSING_VALUATION`; next day's opening is unknown too | `test_unknown_day_blocks_and_stops_the_chart` |
| V3 | Two different rows for the same date | Both quarantined: `DUPLICATE_DAILY_RECORD` | `test_missing_and_conflicting_values_are_unknown` |
| V4 | Cash reported as exactly zero while a closing snapshot shows a balance | Snapshot repairs that date only | `build_daily_table` |
| V5 | Negative total value (debt larger than assets) | Kept; loss larger than capital floored at -100%; WC hidden as `NEGATIVE_VALUE` | `test_loss_larger_than_capital_is_floored` |
| V6 | History starts with investments already held | Since-entry with a note; a zero opening is never invented | `resolve_windows` |

## Capital base

| # | Case | Wrong result it caused | Rule | Test |
|---|---|---|---|---|
| C1 | A few thousand rials left after a full withdrawal | +300% days that compound into absurd yearly returns | `LOW_CAPITAL` days below 1,000,000 rials are flat and counted | `test_low_capital_day_is_flat_and_does_not_block` |
| C2 | Empty account for months | Division by zero | `NO_CAPITAL`; a window of only such days is `NO_INVESTMENT` | `test_all_low_capital_window_is_no_investment` |
| C3 | Tiny start value, then a deposit late in the year (MWR) | About +215% "1Y" MWR for a +10% month | `|BV| < min_capital` treated as 0; period starts at the first real flow | `test_tiny_start_value_is_zeroed` |
| C4 | Credit used to buy, no price change | +33% (credit counted twice) | Credit as capital, raw negative cash | `test_buying_on_credit_creates_no_return_by_itself` |

## Transactions

| # | Case | Rule | Test |
|---|---|---|---|
| T1 | New transaction type appears in the feed | Unmapped: blocks windows containing it, never guessed | `test_unknown_type_is_unmapped_never_guessed`, `test_unknown_type_blocks_only_windows_that_contain_it` |
| T2 | Same transaction delivered twice | Identical repeat ignored; conflicting repeat invalid | `test_duplicates_and_bad_amounts` |
| T3 | Classification by the Persian title of the row | Titles vary; identifiers only | `test_description_is_never_used_for_classification` |
| T4 | Cash dividend paid to the bank account | External outflow, otherwise the ex-date looks like a loss | `test_external_boundary_crossings` |
| T5 | Shares moved in from another broker | External inflow at market value, otherwise they look like profit | same |
| T6 | Rights paid from outside vs from the account's cash | Two identifiers: inflow vs internal | `test_external_boundary_crossings`, `test_internal_types_carry_no_external_flow` |
| T7 | Credit removed but not repaid | Outflow of the credit; the later sale is internal | `test_credit_removal_is_not_repayment` |
| T8 | Credit removed with no grant, or more than granted | Reported, date blocked, not clipped | `test_credit_inconsistencies_are_reported_not_clipped` |

## Horizons and dates

| # | Case | Rule | Test |
|---|---|---|---|
| H1 | One month before 31 March | 28 February (month-end clipping), never "30 days" | `test_calendar_months_clip_to_month_end` |
| H2 | YTD in an Iranian app | Jalali year: starts on 1 Farvardin | `test_full_period_and_ytd_anchors` |
| H3 | Investor joined two months ago | 3M, 6M, 1Y fall back to since entry (or "Insufficient history" under `nearest_only`) | `test_short_history_falls_back_to_since_entry` |
| H4 | Exact anniversary | Stays in the lower bucket | `resolve_windows` |
| H5 | As-of date has no value | `INSUFFICIENT_HISTORY` for every horizon, not the last available date silently | `test_end_date_without_value_is_insufficient_history` |
| H6 | Anchor equals end | `NO_ELAPSED_TIME`, hidden | `resolve_windows`, `horizon_twr` |
| H7 | Cumulative chart does not end at the horizon value | Rebased to 0% on the anchor; anchor's own return excluded | `test_cumulative_is_rebased_to_zero_on_anchor` |
| H8 | Yearly returns do not link to the total | Checked on every run: `years_link_to_all` | `test_jalali_years_link_to_all` |

## Solver (MWR)

| # | Case | Rule | Test |
|---|---|---|---|
| S1 | +10% in two days | Annual rate of about 3.6e7 %; solved on `log(1 + r)`; spreadsheet Newton fails | `test_short_period_large_move_where_newton_fails` |
| S2 | Flows change sign twice | All roots reported, closest to 0% returned, display warning | `test_multiple_roots_are_reported` |
| S3 | Only deposits, nothing back | -100% (total loss) | `test_no_contribution_and_total_loss` |
| S4 | Only withdrawals, nothing put in | `NO_INVESTMENT` | same |
| S5 | All flows on one date | `NO_ELAPSED_TIME`, not a misleading "no sign change" | `test_failure_statuses_never_invent_a_rate` |

## Investor-facing cases (display)

| # | Case | Rule |
|---|---|---|
| D1 | TWR positive, MWR negative | Both shown, with an explanation that timing of deposits drove the difference |
| D2 | Net flow zero because deposits equal withdrawals | Show 0 and still show the deposit and withdrawal amounts |
| D3 | No deposits or withdrawals in the period | "No deposits or withdrawals in this period", no details link |
| D4 | Start or end value is a real zero | Show 0; do not confuse with the empty state |
| D5 | Value not calculated | Status text, never 0% |
| D6 | Fully withdrawn account | The closed result is shown under the tab matching the time since the full withdrawal, then hidden after twelve months; it is not merged with a later new investment (product rule; not implemented in this package) |
