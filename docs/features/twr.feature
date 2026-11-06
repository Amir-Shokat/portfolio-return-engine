Feature: Time-weighted return
  As an investor I want a return that shows how my investments performed,
  so that my own deposits and withdrawals do not look like gains or losses.

  Background:
    Given end-of-day account values in rials
    And the minimum capital is 1,000,000 rials

  Scenario: Deposit at the start of the day joins the capital base
    Given the account closed at 100,000,000 yesterday
    And the investor deposits 50,000,000 today
    When the account closes at 160,000,000
    Then the daily return is 160 / 150 - 1 = 6.67%

  Scenario: Withdrawal at the end of the day earned that day's return
    Given the account closed at 100,000,000 yesterday
    And the investor withdraws 50,000,000 today
    When the account closes at 60,000,000
    Then the daily return is (60 + 50) / 100 - 1 = 10%

  Scenario: Same-day deposit and withdrawal are not netted
    Given the account closed at 1,000,000,000 yesterday
    And the investor deposits 500,000,000 and withdraws 500,000,000 today
    When the account closes at 1,050,000,000
    Then the daily return is 3.33%
    And it is not the 5.00% that a netted end-of-day formula gives

  Scenario: Daily returns are linked, not added
    Given daily returns of +10% and -10% with no flows
    Then the two-day TWR is -1%

  Scenario: Dust left after a withdrawal is not measured
    Given the account holds 200,000 rials at the start of a day
    When the value rises 50% that day
    Then the day is LOW_CAPITAL with a flat factor of 1
    And the horizon is still calculated and counts one low-capital day

  Scenario: Unknown data blocks the horizon and stops the chart
    Given a day whose value is missing in the value file
    Then every horizon containing that day or the next day is RETURN_UNAVAILABLE
    And the cumulative chart stops at the last known day and is not bridged
    And shorter horizons that do not contain the day are still calculated

  Scenario: Cumulative chart starts at zero
    Given the investor selects the 1M horizon
    Then the chart starts at 0% on the anchor close
    And the last point equals the 1M TWR

  Scenario: Yearly returns link to the total
    Given an account with history in two Jalali years
    When the TWR of each Jalali year is linked
    Then the result equals the since-entry TWR
