"""Purchase credit treated as capital, and the negative-cash policy.

Method (credit-as-capital):

    V[t] = holdings[t] + net_option_value[t] + cash_effective[t] + active_credit[t]
    CREDIT_GRANTED  -> active credit up,   same amount as an inflow
    CREDIT_REMOVED  -> active credit down, same amount as an outflow

Active credit is added **once**. Cash is the raw ledger balance, kept negative when the
investor has bought on credit or before a deposit was posted. Removal of credit is the
end of the credit period, not necessarily repayment: unpaid debt stays in the negative
cash balance and a later sale that settles it is an internal move, not a second outflow.

With this method, receiving and using credit creates no gain or loss by itself; only the
price change of what was bought moves the return.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .transactions import TxnType


@dataclass(frozen=True)
class CreditIssue:
    date: pd.Timestamp
    ref: str
    code: str
    message: str


def active_credit(audit: pd.DataFrame, calendar: pd.DatetimeIndex) -> tuple[pd.Series, list[CreditIssue]]:
    """End-of-day active credit per date, rebuilt from credit events by effective date.

    Events are deltas per credit agreement (column ``ref``; one default agreement if absent).
    Identical repeats were already dropped by :func:`transactions.classify`. A removal larger
    than the active amount, or a removal with no earlier grant, is an inconsistency: it is
    reported (code ``CREDIT_OVER_REMOVAL`` / ``CREDIT_MISSING_OPENING``) instead of being
    silently clipped, and the engine blocks returns on that date.
    """
    level = pd.Series(0.0, index=calendar, name="credit")
    issues: list[CreditIssue] = []
    if audit.empty:
        return level, issues
    ev = audit[(audit["status"] == "external")
               & audit["txn_type"].isin([TxnType.CREDIT_GRANTED.value, TxnType.CREDIT_REMOVED.value])].copy()
    if ev.empty:
        return level, issues
    ref = ev["ref"] if "ref" in ev else pd.Series("default", index=ev.index)
    ev["ref"] = ref.fillna("default").astype(str)
    ev = ev.sort_values(["date", "source_row"], kind="stable")
    balances: dict[str, float] = {}
    delta = pd.Series(0.0, index=calendar)
    for _, e in ev.iterrows():
        d, r, amt = e["date"], e["ref"], float(e["amount"])
        bal = balances.get(r)
        if e["txn_type"] == TxnType.CREDIT_GRANTED.value:
            balances[r] = (bal or 0.0) + amt
            change = amt
        else:
            if bal is None:
                issues.append(CreditIssue(d, r, "CREDIT_MISSING_OPENING", "removal with no earlier grant; opening credit is unknown, not zero"))
                change = 0.0
            elif amt > bal + 1e-9:
                issues.append(CreditIssue(d, r, "CREDIT_OVER_REMOVAL", f"removal {amt:,.0f} exceeds active credit {bal:,.0f}"))
                balances[r] = 0.0
                change = -bal
            else:
                balances[r] = bal - amt
                change = -amt
        if d in delta.index:
            delta[d] += change
    level = delta.cumsum().rename("credit")
    return level, issues


def effective_cash(raw_cash: pd.Series, floor_mask: pd.Series | None = None) -> pd.Series:
    """Cash used in the total value.

    Normal accounts keep the raw (possibly negative) balance. Accounts on an exception list
    get ``max(cash, 0)`` on the dates they are listed. Flooring is *not* neutral: with active
    credit in the value it counts the credit twice (see docs/credit-and-options.md, the
    exception example gives a +25% day out of a trade with no price change).
    """
    if floor_mask is None:
        return raw_cash.astype(float)
    mask = floor_mask.reindex(raw_cash.index, fill_value=False).astype(bool)
    return raw_cash.where(~mask, np.maximum(raw_cash, 0.0)).astype(float)
