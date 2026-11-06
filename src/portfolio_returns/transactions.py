"""Transaction taxonomy and the rules that separate external cash flows from internal moves.

Every event in a brokerage account changes cash, holdings or credit. Only some of those
changes are *external*: money or securities crossing the boundary of the measured
account. Returns must remove external flows and keep everything else.

Account perspective (used by TWR and wealth change): money coming into the account is
an inflow (+1), money leaving is an outflow (-1), internal moves are 0. The IRR solver
uses the investor perspective, the exact opposite sign; the conversion is done once, at
the solver boundary (:func:`to_investor`).

Rules are selected by the transaction *type identifier*, never by a free-text title.
A type that is not in the table is **unmapped**: it is never guessed and never treated
as a zero flow; it blocks every horizon whose window contains it.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import numpy as np
import pandas as pd

from .dates import parse_date


class TxnType(str, Enum):
    # cash ledger
    DEPOSIT = "DEPOSIT"
    WITHDRAWAL = "WITHDRAWAL"
    DEPOSIT_REVERSAL = "DEPOSIT_REVERSAL"
    WITHDRAWAL_REVERSAL = "WITHDRAWAL_REVERSAL"
    TRANSFER_TO_OTHER_PRODUCT = "TRANSFER_TO_OTHER_PRODUCT"
    TRANSFER_FROM_OTHER_PRODUCT = "TRANSFER_FROM_OTHER_PRODUCT"
    ACCOUNT_OFFSET = "ACCOUNT_OFFSET"
    LEGAL_PAYMENT = "LEGAL_PAYMENT"
    FEE = "FEE"
    CLOSING_BALANCE = "CLOSING_BALANCE"
    # trading
    BUY = "BUY"
    SELL = "SELL"
    # income and corporate actions
    DIVIDEND_CREDITED = "DIVIDEND_CREDITED"
    CASH_DIVIDEND_PAID_OUT = "CASH_DIVIDEND_PAID_OUT"
    BONUS_SHARES = "BONUS_SHARES"
    RIGHTS_ALLOCATED = "RIGHTS_ALLOCATED"
    RIGHTS_EXERCISED = "RIGHTS_EXERCISED"
    RIGHTS_EXERCISED_FROM_CASH = "RIGHTS_EXERCISED_FROM_CASH"
    RIGHTS_LAPSED = "RIGHTS_LAPSED"
    PENDING_SHARES_LISTED = "PENDING_SHARES_LISTED"
    # securities crossing the account boundary
    SECURITIES_TRANSFER_IN = "SECURITIES_TRANSFER_IN"
    SECURITIES_TRANSFER_OUT = "SECURITIES_TRANSFER_OUT"
    HOLDING_ADJUSTMENT_IN = "HOLDING_ADJUSTMENT_IN"
    HOLDING_ADJUSTMENT_OUT = "HOLDING_ADJUSTMENT_OUT"
    # options
    OPTION_PHYSICAL_SETTLEMENT = "OPTION_PHYSICAL_SETTLEMENT"
    OPTION_CASH_SETTLEMENT = "OPTION_CASH_SETTLEMENT"
    # purchase credit
    CREDIT_GRANTED = "CREDIT_GRANTED"
    CREDIT_REMOVED = "CREDIT_REMOVED"


CONDITIONAL = None  # sign depends on the row's side ("in" or "out")


@dataclass(frozen=True)
class FlowRule:
    """How one transaction type affects the account.

    ``sign`` is the external-flow sign in the account perspective (+1 inflow, -1 outflow,
    0 internal, ``None`` conditional on side, and the string ``"snapshot"`` for balance
    snapshots that are not events at all). ``cash``/``holdings``/``credit`` give the
    direction of the effect on each value component, for audit and reconciliation.
    """

    sign: object
    category: str
    cash: int
    holdings: int
    credit: int
    description: str


R = FlowRule
RULES: dict[TxnType, FlowRule] = {
    TxnType.DEPOSIT: R(+1, "deposit", +1, 0, 0, "Money transferred from a bank account into the brokerage account."),
    TxnType.WITHDRAWAL: R(-1, "withdrawal", -1, 0, 0, "Money paid out to the investor's bank account."),
    TxnType.DEPOSIT_REVERSAL: R(-1, "withdrawal", -1, 0, 0, "Correction that removes a deposit posted in error."),
    TxnType.WITHDRAWAL_REVERSAL: R(+1, "deposit", +1, 0, 0, "A payout that failed at the bank and came back to the account."),
    TxnType.TRANSFER_TO_OTHER_PRODUCT: R(-1, "other_out", -1, 0, 0, "Cash moved to a wallet, commodity or fund account outside the measured scope."),
    TxnType.TRANSFER_FROM_OTHER_PRODUCT: R(+1, "other_in", +1, 0, 0, "Cash moved back from a product outside the measured scope."),
    TxnType.ACCOUNT_OFFSET: R(CONDITIONAL, "other", 0, 0, 0, "Netting transfer between accounts: side 'in' is an inflow, side 'out' an outflow."),
    TxnType.LEGAL_PAYMENT: R(-1, "withdrawal", -1, 0, 0, "Payment to a third party ordered by a court or for an estate."),
    TxnType.FEE: R(0, "fee", -1, 0, 0, "Trading, custody or service cost. Stays inside the return (never neutralised)."),
    TxnType.CLOSING_BALANCE: R("snapshot", "snapshot", 0, 0, 0, "End-of-day balance snapshot. Not a flow; may repair a zero cash balance on the same day."),
    TxnType.BUY: R(0, "trade", -1, +1, 0, "Purchase inside the account: cash becomes holdings."),
    TxnType.SELL: R(0, "trade", +1, -1, 0, "Sale inside the account: holdings become cash."),
    TxnType.DIVIDEND_CREDITED: R(0, "income", +1, -1, 0, "Cash dividend paid into the account's cash: investment income, internal."),
    TxnType.CASH_DIVIDEND_PAID_OUT: R(-1, "distribution", 0, -1, 0, "Cash dividend paid directly to the investor's bank account: the price drops at the ex-date and the cash lands outside the account, so it is a distribution."),
    TxnType.BONUS_SHARES: R(0, "corporate_action", 0, 0, 0, "Bonus shares: more shares at an adjusted price, no change in value."),
    TxnType.RIGHTS_ALLOCATED: R(0, "corporate_action", 0, 0, 0, "Rights issue: rights credited at the ex-rights price adjustment, no change in value."),
    TxnType.RIGHTS_EXERCISED: R(+1, "other_in", 0, +1, 0, "Rights subscription paid from outside the account; new money enters the holdings."),
    TxnType.RIGHTS_EXERCISED_FROM_CASH: R(0, "corporate_action", -1, +1, 0, "Rights subscription paid from the account's own cash: internal."),
    TxnType.RIGHTS_LAPSED: R(-1, "other_out", 0, -1, 0, "Unused rights removed at the deadline; the issuer sells them and pays the holder outside the account."),
    TxnType.PENDING_SHARES_LISTED: R(0, "corporate_action", 0, 0, 0, "Pending bonus or rights shares become tradable: internal."),
    TxnType.SECURITIES_TRANSFER_IN: R(+1, "securities_in", 0, +1, 0, "Shares moved in from another broker (custodian change), valued at market value."),
    TxnType.SECURITIES_TRANSFER_OUT: R(-1, "securities_out", 0, -1, 0, "Shares moved out to another broker, valued at market value."),
    TxnType.HOLDING_ADJUSTMENT_IN: R(+1, "other_in", 0, +1, 0, "Holdings increase with no trade behind it. Treated as an inflow and flagged for review."),
    TxnType.HOLDING_ADJUSTMENT_OUT: R(-1, "other_out", 0, -1, 0, "Holdings decrease with no trade behind it. Treated as an outflow and flagged for review."),
    TxnType.OPTION_PHYSICAL_SETTLEMENT: R(0, "option", -1, +1, 0, "Option exercised by delivery: option value and strike cash become shares, all inside the account."),
    TxnType.OPTION_CASH_SETTLEMENT: R(0, "option", +1, 0, 0, "Option settled in cash inside the account."),
    TxnType.CREDIT_GRANTED: R(+1, "credit", 0, 0, +1, "Purchase credit becomes active: treated as capital coming in."),
    TxnType.CREDIT_REMOVED: R(-1, "credit", 0, 0, -1, "Credit period ends (not necessarily repayment): treated as capital going out."),
}

REVIEW_TYPES = {TxnType.HOLDING_ADJUSTMENT_IN, TxnType.HOLDING_ADJUSTMENT_OUT}

AUDIT_COLUMNS = [
    "source_row", "txn_id", "date", "raw_type", "txn_type", "category", "side", "amount",
    "rule", "external_sign", "inflow", "outflow", "account_flow", "investor_flow",
    "status", "message",
]


class UnmappedTransactionError(ValueError):
    """Raised in strict mode when any transaction cannot be classified."""

    def __init__(self, audit: pd.DataFrame):
        self.audit = audit
        bad = audit[audit["status"].isin(["unmapped", "invalid"])]
        super().__init__(f"{len(bad)} transaction(s) could not be classified; inspect .audit")


def to_investor(account_flow):
    """Account perspective (+ inflow) to investor/IRR perspective (- contribution). Apply once."""
    return -account_flow


def _side_sign(side) -> int | None:
    text = str(side).strip().lower() if side is not None and not pd.isna(side) else ""
    return {"in": +1, "credit": +1, "out": -1, "debit": -1}.get(text)


def classify(transactions: pd.DataFrame, strict: bool = False) -> pd.DataFrame:
    """Classify every transaction row and return a full audit table.

    Required columns: ``date``, ``type``, ``amount`` (a non-negative magnitude in currency units).
    Optional: ``txn_id``, ``side`` (for conditional types), ``ref`` (credit application),
    ``symbol``, ``description`` (kept for audit only, never used for classification).

    Status values: ``external``, ``internal``, ``snapshot``, ``duplicate`` (an identical
    repeat of an earlier ``txn_id``, ignored), ``unmapped`` and ``invalid``. Unmapped and
    invalid rows carry no flow but are kept so they can block affected horizons.
    """
    df = transactions.copy()
    df.columns = [str(c).strip().lower() for c in df.columns]
    missing = {"date", "type", "amount"} - set(df.columns)
    if missing:
        raise ValueError(f"transactions missing columns {sorted(missing)}")
    if "txn_id" not in df:
        df["txn_id"] = [f"row{i + 2}" for i in range(len(df))]
    seen: dict[str, tuple] = {}
    rows = []
    for pos, (_, row) in enumerate(df.iterrows()):
        rec = {c: row.get(c) for c in df.columns}
        rec.update(source_row=pos + 2, raw_type=row.get("type"), txn_type=None, category=None,
                   rule=None, external_sign=0, inflow=0.0, outflow=0.0, account_flow=0.0,
                   investor_flow=0.0, status="invalid", message="")
        rec["side"] = row.get("side") if "side" in df else None
        try:
            rec["date"] = parse_date(row.get("date"))
        except (ValueError, TypeError) as exc:
            rec.update(date=pd.NaT, message=f"invalid date: {exc}")
            rows.append(rec)
            continue
        try:
            amount = float(row.get("amount"))
        except (TypeError, ValueError):
            amount = np.nan
        if not np.isfinite(amount) or amount < 0:
            rec.update(amount=amount, message="amount must be a finite non-negative magnitude")
            rows.append(rec)
            continue
        rec["amount"] = amount
        key = str(rec["txn_id"])
        fingerprint = (rec["date"], str(row.get("type")).strip().upper(), amount, str(rec["side"]))
        if key in seen:
            if seen[key] == fingerprint:
                rec.update(status="duplicate", message="identical repeat of an earlier txn_id; ignored")
            else:
                rec.update(message="txn_id reused with different content")
            rows.append(rec)
            continue
        seen[key] = fingerprint
        try:
            ttype = TxnType(str(row.get("type")).strip().upper())
        except ValueError:
            rec.update(status="unmapped", message="type not in the rule table; never guessed")
            rows.append(rec)
            continue
        rule = RULES[ttype]
        rec.update(txn_type=ttype.value, category=rule.category)
        if rule.sign == "snapshot":
            rec.update(status="snapshot", rule="balance snapshot: excluded from flows")
            rows.append(rec)
            continue
        sign = rule.sign
        if sign is CONDITIONAL:
            sign = _side_sign(rec["side"])
            if sign is None:
                rec.update(message="conditional type needs side 'in' or 'out'")
                rows.append(rec)
                continue
            rec["category"] = "other_in" if sign > 0 else "other_out"
            rec["rule"] = f"{ttype.value}: side={rec['side']} -> {sign:+d}"
        else:
            rec["rule"] = f"{ttype.value}: {sign:+d} x amount" if sign else f"{ttype.value}: internal"
        flow = sign * amount
        rec.update(external_sign=sign, account_flow=flow, investor_flow=to_investor(flow) + 0.0,
                   inflow=max(flow, 0.0), outflow=max(-flow, 0.0),
                   status="external" if sign else "internal",
                   message="review: holdings changed without a trade" if ttype in REVIEW_TYPES else "")
        rows.append(rec)
    audit = pd.DataFrame(rows)
    extra = [c for c in audit.columns if c not in AUDIT_COLUMNS]
    audit = audit[AUDIT_COLUMNS + extra] if len(audit) else pd.DataFrame(columns=AUDIT_COLUMNS)
    if strict and audit["status"].isin(["unmapped", "invalid"]).any():
        raise UnmappedTransactionError(audit)
    return audit


def daily_flows(audit: pd.DataFrame) -> pd.DataFrame:
    """Gross daily flows from the audit, split by direction *before* summing.

    Same-day opposite flows stay visible: a deposit of 50 and a withdrawal of 50 give
    inflow 50 and outflow 50, not a net zero. Columns by category feed the wealth-change
    waterfall. ``blocked`` counts unmapped/invalid rows on that date.
    """
    cols = ["inflow", "outflow", "net_flow", "deposits", "withdrawals", "credit_in", "credit_out",
            "other_in", "other_out", "blocked"]
    if audit.empty:
        return pd.DataFrame(columns=cols, index=pd.DatetimeIndex([], name="date"))
    a = audit[audit["date"].notna()].copy()
    ext = a[a["status"] == "external"]
    cat = ext["category"]
    parts = {
        "inflow": ext["inflow"],
        "outflow": ext["outflow"],
        "deposits": ext["inflow"].where(cat == "deposit", 0.0),
        "withdrawals": ext["outflow"].where(cat == "withdrawal", 0.0),
        "credit_in": ext["inflow"].where(cat == "credit", 0.0),
        "credit_out": ext["outflow"].where(cat == "credit", 0.0),
    }
    parts["other_in"] = ext["inflow"] - parts["deposits"] - parts["credit_in"]
    parts["other_out"] = ext["outflow"] - parts["withdrawals"] - parts["credit_out"]
    frame = pd.DataFrame(parts)
    frame["date"] = ext["date"]
    out = frame.groupby("date").sum()
    blocked = a[a["status"].isin(["unmapped", "invalid"])].groupby("date").size().rename("blocked")
    out = out.join(blocked, how="outer").fillna(0.0)
    out["net_flow"] = out["inflow"] - out["outflow"]
    out.index.name = "date"
    return out[cols]


def rule_table() -> pd.DataFrame:
    """The mapping table as a DataFrame (used to generate docs/transaction-mapping.md)."""
    rows = []
    for t, r in RULES.items():
        sign = {1: "+1", -1: "-1", 0: "0", None: "side", "snapshot": "n/a"}[r.sign]
        rows.append(dict(type=t.value, external_sign=sign, category=r.category, cash=r.cash,
                         holdings=r.holdings, credit=r.credit, description=r.description))
    return pd.DataFrame(rows)
