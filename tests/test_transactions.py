import pandas as pd
import pytest

from portfolio_returns.transactions import (RULES, TxnType, UnmappedTransactionError, classify,
                                            daily_flows, rule_table)


def txns(*rows):
    return pd.DataFrame([dict(zip(["txn_id", "date", "type", "amount", "side"], r)) for r in rows])


def test_every_type_has_a_rule():
    assert set(RULES) == set(TxnType)
    assert len(rule_table()) == len(TxnType)


def test_deposit_and_withdrawal_signs_and_investor_perspective():
    a = classify(txns(("T1", "1405/01/15", "DEPOSIT", 100, None), ("T2", "1405/01/16", "WITHDRAWAL", 40, None)))
    assert list(a["account_flow"]) == [100, -40]
    assert list(a["investor_flow"]) == [-100, 40]
    assert list(a["inflow"]) == [100, 0] and list(a["outflow"]) == [0, 40]
    assert a["date"].iloc[0] == pd.Timestamp("2026-04-04")


@pytest.mark.parametrize("t", ["BUY", "SELL", "FEE", "DIVIDEND_CREDITED", "BONUS_SHARES", "RIGHTS_ALLOCATED",
                               "RIGHTS_EXERCISED_FROM_CASH", "PENDING_SHARES_LISTED",
                               "OPTION_PHYSICAL_SETTLEMENT", "OPTION_CASH_SETTLEMENT"])
def test_internal_types_carry_no_external_flow(t):
    a = classify(txns(("T1", "2026-05-01", t, 1_000_000, None)))
    assert a.at[0, "status"] == "internal"
    assert a.at[0, "account_flow"] == 0


@pytest.mark.parametrize("t,sign", [("CASH_DIVIDEND_PAID_OUT", -1), ("SECURITIES_TRANSFER_IN", 1),
                                    ("SECURITIES_TRANSFER_OUT", -1), ("RIGHTS_EXERCISED", 1),
                                    ("RIGHTS_LAPSED", -1), ("CREDIT_GRANTED", 1), ("CREDIT_REMOVED", -1),
                                    ("TRANSFER_TO_OTHER_PRODUCT", -1), ("WITHDRAWAL_REVERSAL", 1)])
def test_external_boundary_crossings(t, sign):
    a = classify(txns(("T1", "2026-05-01", t, 500, None)))
    assert a.at[0, "status"] == "external"
    assert a.at[0, "account_flow"] == sign * 500


def test_unknown_type_is_unmapped_never_guessed():
    a = classify(txns(("T1", "2026-05-01", "LOYALTY_REWARD", 500, None)))
    assert a.at[0, "status"] == "unmapped" and a.at[0, "account_flow"] == 0
    with pytest.raises(UnmappedTransactionError):
        classify(txns(("T1", "2026-05-01", "LOYALTY_REWARD", 500, None)), strict=True)


def test_description_is_never_used_for_classification():
    df = txns(("T1", "2026-05-01", "BUY", 500, None))
    df["description"] = "deposit from bank"
    assert classify(df).at[0, "status"] == "internal"


def test_conditional_type_needs_side():
    a = classify(txns(("T1", "2026-05-01", "ACCOUNT_OFFSET", 70, "out"),
                      ("T2", "2026-05-01", "ACCOUNT_OFFSET", 70, "in"),
                      ("T3", "2026-05-01", "ACCOUNT_OFFSET", 70, None)))
    assert list(a["account_flow"]) == [-70, 70, 0]
    assert a.at[2, "status"] == "invalid"


def test_duplicates_and_bad_amounts():
    a = classify(txns(("T1", "2026-05-01", "DEPOSIT", 100, None), ("T1", "2026-05-01", "DEPOSIT", 100, None),
                      ("T2", "2026-05-01", "DEPOSIT", 100, None), ("T2", "2026-05-02", "DEPOSIT", 100, None),
                      ("T3", "2026-05-01", "DEPOSIT", -5, None)))
    assert list(a["status"]) == ["external", "duplicate", "external", "invalid", "invalid"]


def test_closing_balance_is_a_snapshot_not_a_flow():
    a = classify(txns(("T1", "2026-05-01", "CLOSING_BALANCE", 900, None)))
    assert a.at[0, "status"] == "snapshot" and a.at[0, "account_flow"] == 0


def test_same_day_opposite_flows_stay_gross():
    a = classify(txns(("T1", "2026-05-01", "DEPOSIT", 50, None), ("T2", "2026-05-01", "WITHDRAWAL", 50, None),
                      ("T3", "2026-05-01", "CREDIT_GRANTED", 30, None), ("T4", "2026-05-02", "MYSTERY", 1, None)))
    f = daily_flows(a)
    day = f.loc["2026-05-01"]
    assert (day["inflow"], day["outflow"], day["net_flow"]) == (80, 50, 30)
    assert (day["deposits"], day["withdrawals"], day["credit_in"]) == (50, 50, 30)
    assert f.loc["2026-05-02", "blocked"] == 1


def test_mapping_document_lists_every_type():
    from pathlib import Path
    doc = (Path(__file__).resolve().parents[1] / "docs" / "transaction-mapping.md").read_text(encoding="utf-8")
    assert all(f"`{t.value}`" in doc for t in TxnType)
