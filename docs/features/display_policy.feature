Feature: Display policy
  Unreliable numbers are flagged or hidden with a reason; nothing is shown as 0% by default.

  Scenario Outline: Status texts
    Given a horizon whose status is <status>
    Then the card shows "<text>"

    Examples:
      | status               | text                                             |
      | INSUFFICIENT_HISTORY | Insufficient history                             |
      | NO_INVESTMENT        | No investment during this period                 |
      | RETURN_UNAVAILABLE   | The return for this period cannot be calculated. |

  Scenario Outline: One-month TWR bands
    Given a 1M TWR of <value>
    Then the display state is <state>

    Examples:
      | value | state   |
      | +5%   | NORMAL  |
      | -45%  | WARNING |
      | +150% | WARNING |
      | +260% | HIDDEN  |
      | -100% | HIDDEN  |

  Scenario: Longer horizons allow larger values
    Given a 1Y TWR of +260%
    Then the display state is NORMAL

  Scenario: Each horizon is judged alone
    Given the 1Y TWR is hidden
    Then the 1M TWR is still shown if it passes its own checks

  Scenario: Stored values are never changed
    Given a value is hidden by the bands
    Then the calculated value and the reason code are still in the output
