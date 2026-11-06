Feature: Wealth change
  As an investor I want to see how many rials my investments made,
  apart from what I deposited or withdrew.

  Scenario: The four card numbers add up
    Given a start value of 100,000,000 and an end value of 180,000,000
    And deposits of 70,000,000 and withdrawals of 10,000,000 in the period
    Then the gain is 20,000,000
    And start value + gain + net deposits = end value

  Scenario: Flows on the anchor date are already in the start value
    Given a deposit on the anchor date
    Then it is not counted again as a flow of the period

  Scenario: Deposits equal withdrawals
    Given deposits of 200,000,000 and withdrawals of 200,000,000 in the period
    Then the net flow shows 0
    And the deposit and withdrawal amounts are still shown

  Scenario: Credit is not shown as a deposit
    Given purchase credit was granted in the period
    Then the waterfall shows it on its own "Credit, net" bar
    And the "Deposits" bar contains only money from the investor's bank account

  Scenario: Unknown flow blocks the amount
    Given an unmapped transaction inside the period
    Then the wealth change is RETURN_UNAVAILABLE and hidden

  Scenario: Missing value inside the period does not block the amount
    Given the value is missing on one day inside the period
    And the start and end values are known
    Then the wealth change is calculated

  Scenario: Negative end value
    Given the end value is below zero
    Then the wealth change is hidden with the code NEGATIVE_VALUE
