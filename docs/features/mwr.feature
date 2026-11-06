Feature: Money-weighted return (personal return)
  As an investor I want to know the return on the money I actually had in the account.

  Scenario: No flows means MWR equals TWR
    Given an account with no deposits or withdrawals in the window
    Then MWR equals TWR for that window

  Scenario: Periodic, not annual, return is shown
    Given 100,000,000 rials grows to 110,000,000 over 365 days with no flows
    Then the shown MWR is 10%
    And the annual rate kept in the back end is 10%

  Scenario: Deposit before a fall
    Given the investments gain 20% and then the investor deposits ten times the balance
    And the market then falls 10%
    Then TWR is +8%
    And MWR is negative
    And the comparison text explains that timing made the personal return negative

  Scenario: Tiny start value is ignored
    Given 500 rials sat in the account for eleven months
    And the investor then deposits 100,000,000 and earns 10% in a month
    When the 1Y MWR is calculated with a minimum capital of 1,000,000 rials
    Then the start value is treated as zero
    And the MWR is about +10%, not about +215%

  Scenario: Short window with a large move
    Given +10% in two days
    Then the solver returns the annual rate 1.1 ^ (365 / 2) - 1
    And the shown periodic MWR is +10%
    And a plain spreadsheet-style Newton iteration fails on the same flows

  Scenario: Several valid rates
    Given flows of -100, +230 and -132 one year apart
    Then the solver reports both 10% and 20%
    And returns 10% with the reason MULTIPLE_ROOTS
    And the value is displayed with a warning

  Scenario Outline: Failures produce a status, never a number
    Given flows that <condition>
    Then the status is <status>
    And no rate is shown

    Examples:
      | condition                | status          |
      | all have the same sign   | NO_SIGN_CHANGE  |
      | all fall on one date     | NO_ELAPSED_TIME |
      | contain a missing amount | INVALID_INPUT   |

  Scenario: Nothing came back
    Given the investor put money in and the account is worth 0 at the end
    Then the MWR is -100% with the reason TOTAL_LOSS
    And the display policy hides it
