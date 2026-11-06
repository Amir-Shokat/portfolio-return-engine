# Validation

How the engine was checked, and how to check it again.

## Test suite

`pytest` runs 105 test cases (68 test functions, some parametrised). Expected values are
worked out by hand or from closed-form relationships, not copied from the engine's own
output.

| File | What it pins |
|---|---|
| `test_transactions.py` | every type has a rule and appears in the mapping document; signs of internal and external types; unmapped, invalid and duplicate rows; titles never used; gross same-day flows |
| `test_twr.py` | start-of-day inflow, end-of-day outflow, same-day opposite flows (3.33% versus 5.00%), all daily statuses, -100% floor, geometric linking, low-capital days, unknown days blocking and stopping the chart, rebased chart, subperiod reconciliation, Actual/365 annualisation |
| `test_xirr.py` | 10% in one year, agreement with spreadsheet Newton on ordinary flows, the two-day +10% case where Newton fails, two roots (10% and 20%), every failure status |
| `test_mwr.py` | MWR = TWR without flows, periodic versus annual, the tiny-start rule (+10.0% versus +214.8%), anchor and end flows, timing effect, total loss, no investment, unknown days |
| `test_wealth_change_credit.py` | the identity and flow boundaries, unknown flows blocking, waterfall with credit on its own bar, credit as capital (0% on a credit purchase), the +33% side effect of flooring cash, removal versus repayment, credit inconsistencies |
| `test_dates_horizons.py` | ISO conversion (1 Farvardin 1405 = 21 March 2026), month-end clipping in both calendars, YTD on 1 Farvardin, since-entry fallback under both policies, no-investment and missing end date |
| `test_display_policy.py` | status texts, one-month bands, horizon-specific bands, multiple-root warning, wealth-change rules, comparison texts, band calibration |
| `test_engine.py` | end-to-end run on the synthetic account, identity on every horizon, yearly linking, chart rebasing, unknown type blocking only the windows that contain it, CLI, carry-forward of levels but not flows, missing and conflicting values, late-deposit detection |

## Reconciliation checks built into every run

* **Wealth-change identity**: `BV + wealth_change + net_flow = EV` for each horizon; the
  display policy hides a result that breaks it (`IDENTITY_BROKEN`).
* **Yearly linking**: the linked TWR of the calendar years equals the since-entry TWR
  (`years_link_to_all` in the controls).
* **Subperiod reconciliation**: linking flow-free blocks gives the same TWR as linking days.
* **No flows, same return**: with no external flows in a window, MWR equals TWR.
* **Spreadsheet comparison**: `MwrResult.spreadsheet_rate` keeps what spreadsheet `XIRR`
  would return for the same flows, so differences can be explained one by one.

## Suggested validation in an adopting product

Independently recalculate an authorized sample, classify mismatches by flow mapping,
timing, boundaries, capital base, solver, credit/options and inputs, then investigate
distribution tails and calibrate display bands. Agree release metrics and tolerances
before deployment. These are recommended steps, not completed production actions.

## Reproduce

```bash
pip install -e ".[dev,charts]"
pytest
python scripts/make_example_data.py      # regenerates examples/ (seed 42)
python scripts/make_charts.py            # regenerates docs/*.png
portfolio-returns --transactions examples/transactions.csv --values examples/daily_values.csv \
    --as-of 2026-10-21 --years --audit audit.csv --daily daily.csv
```
