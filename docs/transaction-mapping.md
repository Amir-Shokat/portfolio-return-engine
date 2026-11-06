# Transaction mapping

Returns are only as good as the separation between **external flows** (money or securities
crossing the account boundary) and **internal moves** (everything that happens inside the
account). This table is the single source of that separation. It is generated from
`transactions.RULES`; the code and this page cannot drift apart without a test failing.

## Rules

* A rule is chosen by the **type identifier** of the transaction, never by its free-text
  title. Titles change, are translated and are typed by hand; identifiers are stable.
* A type that is not in the table is **unmapped**. It is never guessed and never treated as a
  zero flow. It marks its date as unknown, which blocks every horizon whose window contains
  it (TWR, MWR and wealth change). Short horizons that do not contain the date still work.
  `classify(..., strict=True)` raises instead, for pipelines that must stop.
* Amounts are non-negative magnitudes; the sign comes from the rule.
* Account perspective: `+1` is an inflow, `-1` an outflow, `0` internal. "side" means the sign
  depends on a `side` column (`in`/`out`). Snapshots are not events.
* The Cash/Holdings/Credit columns show the direction of the effect on each value component.
  They are used for audit and reconciliation, not for the flow itself.
* Same-day flows are summed by direction before anything else (gross inflow, gross outflow).
* Identical repeats of a `txn_id` are ignored as duplicates; a reused `txn_id` with different
  content is invalid.

## Table

| Type | External sign | Category | Cash | Holdings | Credit | Meaning |
|---|---|---|---|---|---|---|
| `DEPOSIT` | +1 | deposit | +1 | 0 | 0 | Money transferred from a bank account into the brokerage account. |
| `WITHDRAWAL` | -1 | withdrawal | -1 | 0 | 0 | Money paid out to the investor's bank account. |
| `DEPOSIT_REVERSAL` | -1 | withdrawal | -1 | 0 | 0 | Correction that removes a deposit posted in error. |
| `WITHDRAWAL_REVERSAL` | +1 | deposit | +1 | 0 | 0 | A payout that failed at the bank and came back to the account. |
| `TRANSFER_TO_OTHER_PRODUCT` | -1 | other_out | -1 | 0 | 0 | Cash moved to a wallet, commodity or fund account outside the measured scope. |
| `TRANSFER_FROM_OTHER_PRODUCT` | +1 | other_in | +1 | 0 | 0 | Cash moved back from a product outside the measured scope. |
| `ACCOUNT_OFFSET` | side | other | 0 | 0 | 0 | Netting transfer between accounts: side 'in' is an inflow, side 'out' an outflow. |
| `LEGAL_PAYMENT` | -1 | withdrawal | -1 | 0 | 0 | Payment to a third party ordered by a court or for an estate. |
| `FEE` | 0 | fee | -1 | 0 | 0 | Trading, custody or service cost. Stays inside the return (never neutralised). |
| `CLOSING_BALANCE` | n/a | snapshot | 0 | 0 | 0 | End-of-day balance snapshot. Not a flow; may repair a zero cash balance on the same day. |
| `BUY` | 0 | trade | -1 | +1 | 0 | Purchase inside the account: cash becomes holdings. |
| `SELL` | 0 | trade | +1 | -1 | 0 | Sale inside the account: holdings become cash. |
| `DIVIDEND_CREDITED` | 0 | income | +1 | -1 | 0 | Cash dividend paid into the account's cash: investment income, internal. |
| `CASH_DIVIDEND_PAID_OUT` | -1 | distribution | 0 | -1 | 0 | Cash dividend paid directly to the investor's bank account: the price drops at the ex-date and the cash lands outside the account, so it is a distribution. |
| `BONUS_SHARES` | 0 | corporate_action | 0 | 0 | 0 | Bonus shares: more shares at an adjusted price, no change in value. |
| `RIGHTS_ALLOCATED` | 0 | corporate_action | 0 | 0 | 0 | Rights issue: rights credited at the ex-rights price adjustment, no change in value. |
| `RIGHTS_EXERCISED` | +1 | other_in | 0 | +1 | 0 | Rights subscription paid from outside the account; new money enters the holdings. |
| `RIGHTS_EXERCISED_FROM_CASH` | 0 | corporate_action | -1 | +1 | 0 | Rights subscription paid from the account's own cash: internal. |
| `RIGHTS_LAPSED` | -1 | other_out | 0 | -1 | 0 | Unused rights removed at the deadline; the issuer sells them and pays the holder outside the account. |
| `PENDING_SHARES_LISTED` | 0 | corporate_action | 0 | 0 | 0 | Pending bonus or rights shares become tradable: internal. |
| `SECURITIES_TRANSFER_IN` | +1 | securities_in | 0 | +1 | 0 | Shares moved in from another broker (custodian change), valued at market value. |
| `SECURITIES_TRANSFER_OUT` | -1 | securities_out | 0 | -1 | 0 | Shares moved out to another broker, valued at market value. |
| `HOLDING_ADJUSTMENT_IN` | +1 | other_in | 0 | +1 | 0 | Holdings increase with no trade behind it. Treated as an inflow and flagged for review. |
| `HOLDING_ADJUSTMENT_OUT` | -1 | other_out | 0 | -1 | 0 | Holdings decrease with no trade behind it. Treated as an outflow and flagged for review. |
| `OPTION_PHYSICAL_SETTLEMENT` | 0 | option | -1 | +1 | 0 | Option exercised by delivery: option value and strike cash become shares, all inside the account. |
| `OPTION_CASH_SETTLEMENT` | 0 | option | +1 | 0 | 0 | Option settled in cash inside the account. |
| `CREDIT_GRANTED` | +1 | credit | 0 | 0 | +1 | Purchase credit becomes active: treated as capital coming in. |
| `CREDIT_REMOVED` | -1 | credit | 0 | 0 | -1 | Credit period ends (not necessarily repayment): treated as capital going out. |

## Why each borderline case is classified the way it is

**Dividend credited to the account (internal) versus dividend paid to the bank (external).**
On the ex-dividend date the share price drops by the dividend. If the cash lands in the
account's cash, value moves from holdings to cash: internal, no flow, and the return is
unchanged. In the market market issuers often pay the cash dividend directly to the
investor's bank account through the central depository. Then the price drop is inside the
account but the cash is outside: it must be recorded as an outflow (a distribution), or the
ex-date looks like a loss.

**Bonus shares and rights allocation (internal).** The number of shares rises and the price
is adjusted so the value is unchanged. No flow. If prices are *not* adjusted in the value
feed, the daily return on the ex-date is wrong; this is a data check, not a mapping rule.

**Rights exercise (depends on who pays).** Paying the subscription price from the account's
own cash is internal (cash becomes pending shares). Paying it from outside the account is new
money: an inflow. The two cases need two identifiers.

**Rights lapse (external).** Unused rights are removed at the deadline; the issuer sells
them and pays the proceeds outside the account. The value leaves the account: outflow.

**Pending shares listed (internal).** New shares from a capital increase become tradable.
Same value, different line in the holdings.

**Securities transfer between brokers (external).** A custodian change moves shares in or
out without cash. It is a flow at market value on the transfer date; otherwise the arrival
of shares looks like a profit and their departure like a loss.

**Holding adjustments without a trade (external, flagged).** Holdings change with no trade,
transfer or corporate action behind them. Treated as a flow at market value so the return is
not distorted, and flagged for review because the cause is unknown.

**Transfers to other products (external).** Cash moved to a wallet, a commodity account or a
fund outside the measured scope leaves the account boundary.

**Reversals.** A deposit reversed by the bank is an outflow; a payout returned by the bank is
an inflow. Netting them against the original rows by hand is not needed and is error-prone.

**Fees (internal).** Trading, custody and service costs reduce the return. They are never
neutralised as flows.

**Credit (external under the credit-as-capital method).** Activation of purchase credit is
an inflow, its removal an outflow. Removal is the end of the credit period, not necessarily
repayment. See [credit-and-options.md](credit-and-options.md).

**Options (internal).** Buying an option is a trade (cash becomes option value). Physical
settlement turns option value and strike cash into shares inside the account; cash settlement
turns option value into cash inside the account. The option position itself is part of the
value through `net_option_value`.

**Closing balance snapshots (not events).** Some ledgers write an end-of-day balance row. It
is excluded from flows. It may repair a cash balance that the value feed reports as exactly
zero on the same date, and nothing else.

## Audit output

`classify()` returns one row per input row with the rule applied, the account and investor
flows, the status (`external`, `internal`, `snapshot`, `duplicate`, `unmapped`, `invalid`)
and a message. The CLI writes it with `--audit audit.csv`. Every number in a horizon can be
traced back to these rows.
