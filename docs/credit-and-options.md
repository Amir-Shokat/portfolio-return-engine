# Purchase credit and options

This demonstration uses credit as capital and signed net option value. These are
explicit reference-model assumptions, not confirmed service semantics or an approved
employer policy. Validate balance definitions, event meanings and effective times before
adapting the model. Consistency in a synthetic example does not establish compatibility
with a real credit or options service.

## Purchase credit: the problem

An investor with 100 in cash receives 50 of credit and buys shares worth 150. The ledger shows
cash of -50 (the debt) and holdings of 150. Nothing has happened to prices. Any sensible method
must show a 0% return for that day. Three candidate definitions of the account value:

| Definition | Value after the purchase | Daily return |
|---|---|---|
| Cash + holdings (credit ignored, raw negative cash) | 100 | 0%, but the credit is invisible and the investor appears to have 100 at work while 150 is exposed |
| Cash floored at 0 + holdings + active credit | 200 | +33%: the credit is counted twice |
| **Raw cash + holdings + active credit, credit as a flow** | 150 | **0%** |

## Method: credit as capital

    V[t] = holdings[t] + net_option_value[t] + cash_raw[t] + active_credit[t]

* `CREDIT_GRANTED` raises active credit and is an inflow of the same amount.
* `CREDIT_REMOVED` lowers active credit and is an outflow of the same amount.
* Active credit is added **once**. Cash stays the raw ledger balance, negative when the
  investor bought on credit or before a deposit was posted.
* Removal is the end of the credit period, **not** necessarily repayment. If the debt is not
  paid, it stays in the negative cash. A later sale that settles it is an internal move
  (holdings become cash), not a second outflow.

Result: receiving and using credit creates no gain or loss by itself. Only the price change of
what was bought moves the return. TWR measures the return on all capital at work, including
borrowed capital; MWR sees the credit as money the investor put in and took out.

Active credit is rebuilt from the events by effective date, per credit agreement (`ref`).
Inconsistent histories are reported, not clipped:

| Code | Meaning | Effect |
|---|---|---|
| `CREDIT_OVER_REMOVAL` | removal larger than the active amount | date flagged, horizons containing it blocked |
| `CREDIT_MISSING_OPENING` | removal with no earlier grant | opening credit is unknown, not zero; date flagged |

## The negative-cash exception list

Some negative balances are accounting artefacts rather than real debt (for example a deposit
posted one day after the shares it paid for). One proposal was to floor cash at zero for
accounts on an exception list. `credit.effective_cash()` supports it, but it is **not neutral**:
with active credit in the value, flooring counts the credit twice. In the example above,
100 + 50 credit used for a 150 purchase shows +33% on a day with no price change (the test
suite pins this). The exception list must be small, explicit and reviewed, and the late-deposit
case is better handled by the data-quality check `LIKELY_LATE_FLOW` (see
[edge-cases.md](edge-cases.md)).

## Options

    net_option_value[t] = long option market value - short option market value

* Buying an option is a trade: cash becomes option value. No flow.
* Physical settlement (exercise by delivery): option value and strike cash become shares
  inside the account. No flow.
* Cash settlement: option value becomes cash inside the account. No flow.
* Collateral blocked for short positions stays in cash; it is not a second asset.
* The value is signed. A written option is a liability and lowers the value.

Leaving options out of the value makes the premium paid look like a loss on
the purchase day (and the shares delivered at settlement look like a gain); including them makes the return follow
the option's market value day by day.

## Scenarios

[features/credit_and_options.feature](features/credit_and_options.feature).
