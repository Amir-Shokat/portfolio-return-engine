import pandas as pd
import pytest

from portfolio_returns.dates import JALALI, jalali_year_end, months_back, parse_date, to_jalali
from portfolio_returns.horizons import STANDARD, resolve_windows

M = 1_000_000


def test_jalali_conversion_is_exact():
    assert parse_date("1405/01/01") == pd.Timestamp("2026-03-21")
    assert parse_date("1405-07-30") == pd.Timestamp("2026-10-22")
    assert parse_date("2026-10-22") == pd.Timestamp("2026-10-22")
    assert to_jalali("2026-03-20") == "1404/12/29"
    assert jalali_year_end(1404) == pd.Timestamp("2026-03-20")   # 1404 is not a leap year


def test_calendar_months_clip_to_month_end():
    assert months_back("2026-03-31", 1) == pd.Timestamp("2026-02-28")
    assert months_back("2026-10-22", 12) == pd.Timestamp("2025-10-22")
    assert months_back("1405/01/31", 1, JALALI) == parse_date("1404/12/29")


def daily(start, values):
    idx = pd.date_range(start, periods=len(values), freq="D", name="date")
    return pd.DataFrame({"total_value": values}, index=idx)


def test_full_period_and_ytd_anchors():
    d = daily("2025-01-01", [100 * M] * 700)
    end = d.index[-1]                                      # 2026-12-01
    w = {x.label: x for x in resolve_windows(d, end)}
    assert w["1M"].anchor == pd.Timestamp("2026-11-01") and w["1M"].first_day == pd.Timestamp("2026-11-02")
    assert w["YTD"].anchor == pd.Timestamp("2026-03-20") and to_jalali(w["YTD"].first_day) == "1405/01/01"
    assert all(w[k].basis == "FULL_PERIOD" for k in ["1M", "3M", "6M", "1Y", "YTD"])
    assert w["ALL"].basis == "SINCE_ENTRY"


def test_short_history_falls_back_to_since_entry():
    d = daily("2026-07-01", [0.0] * 10 + [100 * M] * 72)   # funded from 11 July, as of 21 Sep
    w = {x.label: x for x in resolve_windows(d, d.index[-1])}
    assert w["1M"].basis == "FULL_PERIOD"
    assert w["3M"].basis == w["6M"].basis == "SINCE_ENTRY"
    assert w["3M"].anchor == pd.Timestamp("2026-07-10")    # last known-zero close before entry
    w2 = {x.label: x for x in resolve_windows(d, d.index[-1], history_policy="nearest_only")}
    assert w2["3M"].basis == "SINCE_ENTRY" and w2["6M"].basis == "INSUFFICIENT_HISTORY"


def test_no_funded_day_is_no_investment():
    d = daily("2026-07-01", [0.0] * 40)
    assert {x.basis for x in resolve_windows(d, d.index[-1], STANDARD)} == {"NO_INVESTMENT"}


def test_end_date_without_value_is_insufficient_history():
    d = daily("2026-07-01", [100 * M] * 10)
    assert resolve_windows(d, "2026-08-01")[0].basis == "INSUFFICIENT_HISTORY"
