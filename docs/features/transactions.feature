Feature: Transaction mapping
  Returns must remove external flows and keep everything else.

  Scenario Outline: Internal events carry no flow
    Given a <type> transaction
    Then it is internal and its external flow is 0

    Examples:
      | type                       |
      | BUY                        |
      | SELL                       |
      | FEE                        |
      | DIVIDEND_CREDITED          |
      | BONUS_SHARES               |
      | RIGHTS_ALLOCATED           |
      | RIGHTS_EXERCISED_FROM_CASH |
      | PENDING_SHARES_LISTED      |
      | OPTION_PHYSICAL_SETTLEMENT |

  Scenario Outline: Boundary crossings are flows
    Given a <type> transaction of 500 currency units
    Then its external flow is <flow>

    Examples:
      | type                    | flow |
      | DEPOSIT                 | +500 |
      | WITHDRAWAL              | -500 |
      | CASH_DIVIDEND_PAID_OUT  | -500 |
      | SECURITIES_TRANSFER_IN  | +500 |
      | SECURITIES_TRANSFER_OUT | -500 |
      | RIGHTS_EXERCISED        | +500 |
      | RIGHTS_LAPSED           | -500 |
      | CREDIT_GRANTED          | +500 |
      | CREDIT_REMOVED          | -500 |

  Scenario: Unknown type blocks, never guessed
    Given a transaction of a type that is not in the rule table
    Then it is unmapped
    And every horizon whose window contains its date is RETURN_UNAVAILABLE
    And horizons that do not contain its date are calculated

  Scenario: Titles are never used
    Given a BUY transaction whose description says "deposit"
    Then it is classified as internal

  Scenario: Duplicates
    Given the same txn_id delivered twice with identical content
    Then the second row is ignored as a duplicate
    But a txn_id reused with different content is invalid
