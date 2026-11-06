"""Generate the synthetic example files in examples/ (no real client data).

    python scripts/make_example_data.py

One made-up account (U001) from August 2025 to October 2026. A small ledger simulates
prices, trades and fees,
and the events the engine has to classify: deposits and withdrawals, a same-day deposit and
withdrawal, a securities transfer from another broker, a cash dividend paid to the
investor's bank account, bonus shares, a rights issue (allocation, partial exercise paid from
outside, lapse of the rest, listing of the new shares), purchase credit, a call option
settled by delivery, a purchase made the day before its deposit was posted (negative cash
for one day) and a transfer to a wallet outside the account.

End-of-day values are written only on standard Monday-to-Friday business days, excluding
a small illustrative holiday set. The engine carries values over weekends and holidays.
All dates use ISO ``YYYY-MM-DD`` format.
"""

from pathlib import Path

import numpy as np
import pandas as pd

rng = np.random.default_rng(42)
out = Path(__file__).resolve().parents[1] / "examples"
out.mkdir(exist_ok=True)

START, END = pd.Timestamp("2025-08-20"), pd.Timestamp("2026-10-21")
HOLIDAYS = {pd.Timestamp(d) for d in ["2025-12-25", "2026-01-01", "2026-04-03"]}


def trading(d):
    return d.weekday() < 5 and d not in HOLIDAYS


def iso_date(d):
    return pd.Timestamp(d).strftime("%Y-%m-%d")


def next_trading(d):
    d = pd.Timestamp(d)
    while not trading(d):
        d += pd.Timedelta(1, "D")
    return d


days = [d for d in pd.date_range(START, END) if trading(d)]
price = {"ALPHA": 18_000.0, "BETA": 6_500.0, "GAMMA": 2_400.0}
qty = {k: 0.0 for k in ["ALPHA", "BETA", "GAMMA", "GAMMA_R", "GAMMA_NEW"]}
cash = 0.0
option = None          # dict(n, strike, time_value, start, expiry)
txns, values = [], []


def add(d, typ, amount, symbol="", side="", ref="", desc=""):
    txns.append(dict(txn_id=f"T{len(txns) + 1:04d}", date=iso_date(d), account_id="U001", type=typ,
                     amount=round(amount), side=side, ref=ref, symbol=symbol, description=desc))


def trade(d, sym, n, desc=""):
    """Buy (n > 0) or sell (n < 0) at the close, with fees (0.37% buy, 0.88% sell incl. tax)."""
    global cash
    value = abs(n) * price[sym]
    fee = value * (0.0037 if n > 0 else 0.0088)
    qty[sym] += n
    cash += -value if n > 0 else value
    cash -= fee
    add(d, "BUY" if n > 0 else "SELL", value, sym, desc=desc)
    add(d, "FEE", fee, sym, desc="trading fee and tax")


def px(sym):
    if sym in ("GAMMA_NEW",):
        return price["GAMMA"]
    if sym == "GAMMA_R":
        return max(price["GAMMA"] - 1_000.0, 1.0)
    return price[sym]


events = {}


def on(date, fn):
    events.setdefault(next_trading(date), []).append(fn)


def deposit(amount, desc="bank transfer"):
    def f(d):
        global cash
        cash += amount
        add(d, "DEPOSIT", amount, desc=desc)
    return f


def withdraw(amount, desc="payout to bank account"):
    def f(d):
        global cash
        cash -= amount
        add(d, "WITHDRAWAL", amount, desc=desc)
    return f


on("2025-08-23", deposit(800_000_000, "first deposit"))
on("2025-08-23", lambda d: trade(d, "ALPHA", 20_000))
on("2025-08-23", lambda d: trade(d, "BETA", 50_000))


def transfer_in(d):
    qty["GAMMA"] += 60_000
    add(d, "SECURITIES_TRANSFER_IN", 60_000 * price["GAMMA"], "GAMMA", desc="shares moved in from another broker")


on("2025-10-12", transfer_in)
on("2025-11-16", deposit(300_000_000))
on("2025-11-16", lambda d: trade(d, "ALPHA", 12_000))


def dividend(d):
    dps = 1_400.0
    price["ALPHA"] -= dps                      # ex-dividend price adjustment
    add(d, "CASH_DIVIDEND_PAID_OUT", qty["ALPHA"] * dps, "ALPHA",
        desc="cash dividend paid by the issuer to the investor's bank account")


on("2025-12-20", dividend)


def bonus(d):
    qty["BETA"] *= 1.3
    price["BETA"] /= 1.3
    add(d, "BONUS_SHARES", 0, "BETA", desc="30% bonus shares; price adjusted")


on("2026-01-17", bonus)


def rights(d):
    ratio = 0.5
    adjusted = (price["GAMMA"] + 1_000.0 * ratio) / (1 + ratio)
    price["GAMMA"] = adjusted
    qty["GAMMA_R"] = qty["GAMMA"] * ratio
    add(d, "RIGHTS_ALLOCATED", qty["GAMMA_R"] * px("GAMMA_R"), "GAMMA_R", desc="rights issue 50%; ex-rights price adjustment")


def exercise(d):
    n = round(qty["GAMMA_R"] * 0.6)
    qty["GAMMA_R"] -= n
    qty["GAMMA_NEW"] += n
    add(d, "RIGHTS_EXERCISED", n * 1_000.0, "GAMMA_R", desc="subscription paid from the investor's bank account")


def lapse(d):
    value = qty["GAMMA_R"] * px("GAMMA_R")
    qty["GAMMA_R"] = 0.0
    add(d, "RIGHTS_LAPSED", value, "GAMMA_R", desc="unused rights removed; proceeds paid outside the account")


def listing(d):
    qty["GAMMA"] += qty["GAMMA_NEW"]
    add(d, "PENDING_SHARES_LISTED", qty["GAMMA_NEW"] * price["GAMMA"], "GAMMA", desc="new shares become tradable")
    qty["GAMMA_NEW"] = 0.0


on("2026-02-14", rights)
on("2026-03-07", exercise)
on("2026-03-14", lapse)
on("2026-04-25", listing)
on("2026-04-11", withdraw(150_000_000))
on("2026-05-09", deposit(200_000_000, "deposit, sent on the same day"))
on("2026-05-09", withdraw(200_000_000, "same-day payout"))


def credit_on(d):
    add(d, "CREDIT_GRANTED", 400_000_000, ref="C-0001", desc="purchase credit activated")


def credit_off(d):
    add(d, "CREDIT_REMOVED", 400_000_000, ref="C-0001", desc="credit period ended; not a repayment")


on("2026-06-06", credit_on)
on("2026-06-06", lambda d: trade(d, "ALPHA", 25_000, "bought partly on credit"))
on("2026-07-18", credit_off)
on("2026-07-20", lambda d: trade(d, "ALPHA", -20_000, "sale that settles the negative cash"))


def option_buy(d):
    global cash, option
    n, strike = 40_000, round(price["BETA"] * 0.9)
    premium = n * (price["BETA"] - strike) + n * 250.0
    cash -= premium
    option = dict(n=n, strike=strike, tv=n * 250.0, start=d, expiry=next_trading(d + pd.Timedelta(45, "D")))
    add(d, "BUY", premium, "BETA_CALL", desc="call option premium")


def option_settle(d):
    global cash, option
    cash -= option["n"] * option["strike"]
    qty["BETA"] += option["n"]
    add(d, "OPTION_PHYSICAL_SETTLEMENT", option["n"] * option["strike"], "BETA_CALL",
        desc="call exercised by delivery: strike paid, shares received")
    option = None


on("2026-06-27", option_buy)
on("2026-08-12", option_settle)
on("2026-08-23", lambda d: trade(d, "GAMMA", 60_000, "bought before the deposit was posted"))
on("2026-08-24", deposit(round(60_000 * 3_000 * 1.0037, -6) + 50_000_000, "deposit posted one day late"))
on("2026-09-20", lambda d: (add(d, "TRANSFER_TO_OTHER_PRODUCT", 50_000_000, desc="cash moved to a commodity wallet"),
                            globals().__setitem__("cash", cash - 50_000_000)))
on("2026-10-11", deposit(250_000_000))
on("2026-10-11", lambda d: trade(d, "BETA", 40_000))

values.append(dict(date=iso_date(START), cash=0, holdings=0, options=0))
for d in days[1:] if days[0] == START else days:
    for k in price:
        price[k] *= float(np.exp(np.clip(rng.normal(0.0011, 0.017), -0.05, 0.05)))
    for fn in events.get(d, []):
        fn(d)
    opt_value = 0.0
    if option is not None:
        left = max((option["expiry"] - d).days, 0) / max((option["expiry"] - option["start"]).days, 1)
        opt_value = option["n"] * max(price["BETA"] - option["strike"], 0.0) + option["tv"] * left
    holdings = sum(q * px(s) for s, q in qty.items())
    values.append(dict(date=iso_date(d), cash=round(cash), holdings=round(holdings), options=round(opt_value)))

pd.DataFrame(txns).to_csv(out / "transactions.csv", index=False)
pd.DataFrame(values).to_csv(out / "daily_values.csv", index=False)

# Same account plus one transaction type the rule table does not know.
unknown = pd.DataFrame(txns)
extra = dict(txn_id="T9001", date="2026-09-01", account_id="U001", type="LOYALTY_REWARD", amount=5_000_000,
             side="", ref="", symbol="", description="type not in the rule table")
pd.concat([unknown, pd.DataFrame([extra])], ignore_index=True).to_csv(out / "transactions_with_unknown.csv", index=False)
print(f"Wrote {len(txns)} transactions and {len(values)} value rows to {out}")
