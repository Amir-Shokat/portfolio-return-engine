Feature: Purchase credit and options in the account value

  Scenario: Buying on credit is not a gain
    Given 100,000,000 currency units in cash
    And 50,000,000 currency units of credit is granted
    And shares worth 150,000,000 are bought with no price change
    Then the account value is 150,000,000
    And the daily return is 0%

  Scenario: Flooring negative cash counts credit twice
    Given the same account is on the negative-cash exception list
    Then the account value is 200,000,000
    And the daily return is +33%, which is why the exception list must stay small

  Scenario: Credit removal is not repayment
    Given the credit period ends while cash is still negative
    Then the removal is an outflow of the credit amount
    And the later sale that settles the negative cash is internal

  Scenario: Inconsistent credit history
    Given a credit removal larger than the active credit
    Then the issue CREDIT_OVER_REMOVAL is reported
    And horizons containing that date are blocked

  Scenario: Option exercised by delivery
    Given a call option held in the account
    When it is exercised and the shares are delivered
    Then no external flow is recorded
    And the return follows the option value, then the share value
