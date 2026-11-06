# Decision log

Decisions taken while defining the methodology, with the alternatives considered. Status is
the state at hand-off.

| # | Decision | Alternatives | Why | Status |
|---|---|---|---|---|
| D1 | TWR flow timing: inflow at the start of the day, outflow at the end (Portfolio Performance convention) | All flows at the end of the day, netted (the earlier formula) | The earlier formula treats a morning deposit as if it earned nothing and hides same-day opposite flows; see the worked example below | Adopted for new development; earlier formula kept in code (`eod_net_return`) for comparison |
| D2 | Gross daily flows, split by direction before summing | Net daily flow | Net flow cannot reconstruct the capital base when money goes both ways on one day | Adopted |
| D3 | Days with tiny or non-positive capital are flat (factor 1), counted, and do not block the horizon | Drop the days; block the horizon; compute anyway | Dropping or computing them produced absurd compounded returns; blocking hid valid long horizons | Adopted, threshold is a parameter |
| D4 | A loss larger than capital is floored at -100% and later days still link | Reset the history after a total loss (separate "episodes") | Resetting made yearly returns stop linking to the total and confused investors who kept trading | Adopted; episode reset superseded |
| D5 | An unknown day blocks every horizon that contains it; the chart line stops there | Treat as 0%; interpolate | A guessed day makes every long horizon silently wrong | Adopted |
| D6 | Horizon window `(anchor, end]`: anchor is a closing value, first day is the next day | Include the anchor's own return | Including it double counts the day across consecutive windows and stops yearly linking | Adopted; the cumulative chart starts at 0% on the anchor |
| D7 | Calendar months with month-end clipping; YTD on the calendar year | 30/90/180/365 fixed days; Gregorian YTD | Matches what investors read on the screen and the market fiscal year | Adopted |
| D8 | MWR shown as a periodic return for the invested span | Show the annual rate | A 20-day annual rate is not meaningful to an investor and is not comparable with TWR | Adopted; annual rate kept in the back end |
| D9 | XIRR solved on `log(1 + r)` with bracket scan and residual check; statuses instead of exceptions | Newton from a 10% guess, as spreadsheets do | Newton fails on short windows with large moves and hides multiple roots; these were a large share of MWR mismatches | Adopted |
| D10 | Tiny start value treated as zero for MWR | Use it as is | A few currency units for eleven months turned a +10% month into about +215% "1Y" | Adopted |
| D11 | Transaction rules by type identifier; unmapped types block | Classify by title text; default unknown types to zero | Titles are free text and change; a default hides new flow types | Adopted |
| D12 | Cash dividend paid to the bank account is an outflow | Ignore it | The price falls at the ex-date while the cash is outside: without the flow the ex-date is a fake loss | Adopted |
| D13 | Credit as capital: credit added once to the value, grant = inflow, removal = outflow, raw negative cash kept | Ignore credit; floor cash at zero and add credit | Only this option gives 0% for a credit purchase with no price change | Reference-model assumption; service compatibility unverified |
| D14 | Negative-cash exception list floors cash for listed accounts | No exceptions | Some negatives are posting artefacts; but flooring counts credit twice, so the list must stay small and reviewed | Accepted with a documented side effect |
| D15 | Options included through signed net option value; settlements are internal | Exclude options | Excluding them makes premium and settlement look like performance | Reference-model assumption; service compatibility unverified |
| D16 | Display: three states (normal, warning, hidden) plus status texts; four limits per horizon | One cap on the value | A single cap either hides too many real returns or shows too many artefacts | Adopted; limits calibrated on the output distribution |
| D17 | MWR reuses the TWR display bands | Calibrate separately now | No separate calibration yet; same scale (periodic return) | Temporary |
| D18 | Long horizons fall back to since entry (`all_since_entry`) by default; `nearest_only` available | Only one fallback horizon | Product preferred showing a number on every tab; the stricter option is kept for the wealth-change card design | Both supported |
| D19 | Wealth change is not blocked by a missing value inside the window | Block like TWR | No division and no daily linking: only the two boundary values and the flows matter | Adopted |

## Worked example for D1 and D2

Start 1,000. During the day the investor deposits 500 and withdraws 500. The market adds 50.
Close 1,050.

| Formula | Capital base | Daily return |
|---|---|---|
| Earlier: all flows at end of day, netted (net flow 0) | 1,000 | (1,050 - 0 - 1,000) / 1,000 = **5.00%** |
| Adopted: inflow at start, outflow at end, gross | 1,000 + 500 = 1,500 | (1,050 + 500) / 1,500 - 1 = **3.33%** |

50 currency units were earned on 1,500 currency units at work, not on 1,000. The test
`test_same_day_deposit_and_withdrawal_are_not_netted` pins both numbers.

## Example for D10

| | Tiny start kept | Tiny start treated as 0 |
|---|---|---|
| Flows | -500 currency units on day 0, -100,000,000 on day 331, +110,000,000 on day 361 | -100,000,000 on day 331, +110,000,000 on day 361 |
| Invested span | 361 days | 30 days |
| Periodic MWR | +214.8% (a one-month rate of about +219% a year, stretched over 361 days) | +10.0% |
