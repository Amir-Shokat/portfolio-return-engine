"""Date helpers: Jalali (Solar Hijri) and Gregorian parsing, calendar-month arithmetic.

Iranian back-office exports usually carry Jalali dates such as ``1405/07/30``. All
calculations run on Gregorian ``pandas.Timestamp`` values normalised to midnight;
Jalali strings are converted exactly with ``jdatetime`` (1 Farvardin 1405 = 21 March 2026).
"""

from __future__ import annotations

import calendar as _calendar
import datetime as _dt

import jdatetime
import pandas as pd

GREGORIAN = "gregorian"
JALALI = "jalali"


def parse_date(value) -> pd.Timestamp:
    """Parse a Gregorian or Jalali date into a normalised Gregorian Timestamp.

    Strings like ``1405/07/30`` or ``1405-07-30`` (year below 1700) are read as Jalali;
    ``2026-10-22`` as Gregorian. Datetime-like values are normalised to midnight.
    """
    if isinstance(value, (pd.Timestamp, _dt.datetime, _dt.date)) and not isinstance(value, str):
        ts = pd.Timestamp(value)
        if ts.tzinfo is not None:
            raise ValueError("dates must be timezone-naive")
        return ts.normalize()
    if value is None or (isinstance(value, float) and pd.isna(value)):
        raise ValueError("missing date")
    text = str(value).strip().replace("-", "/")
    parts = text.split("/")
    if len(parts) == 3 and all(p.strip().isdigit() for p in parts):
        y, m, d = (int(p) for p in parts)
        if y < 1700:
            return pd.Timestamp(jdatetime.date(y, m, d).togregorian())
        return pd.Timestamp(_dt.date(y, m, d))
    ts = pd.Timestamp(str(value))
    if ts.tzinfo is not None:
        raise ValueError("dates must be timezone-naive")
    return ts.normalize()


def to_jalali(ts) -> str:
    """Format a Gregorian date as a Jalali string ``YYYY/MM/DD``."""
    ts = pd.Timestamp(ts)
    return jdatetime.date.fromgregorian(date=ts.date()).strftime("%Y/%m/%d")


def jalali_year(ts) -> int:
    return jdatetime.date.fromgregorian(date=pd.Timestamp(ts).date()).year


def jalali_year_start(year: int) -> pd.Timestamp:
    """Gregorian date of 1 Farvardin of the Jalali ``year``."""
    return pd.Timestamp(jdatetime.date(year, 1, 1).togregorian())


def jalali_year_end(year: int) -> pd.Timestamp:
    """Gregorian date of the last day of Esfand (29th, or 30th in a leap year)."""
    return jalali_year_start(year + 1) - pd.Timedelta(1, "D")


def _jalali_month_length(year: int, month: int) -> int:
    if month <= 6:
        return 31
    if month <= 11:
        return 30
    return 30 if jdatetime.date(year, 1, 1).isleap() else 29


def months_back(end, months: int, calendar: str = GREGORIAN) -> pd.Timestamp:
    """The same day ``months`` calendar months earlier, clipped to the month end.

    Gregorian: 31 March 2026 minus one month is 28 February 2026.
    Jalali: 31 Farvardin 1405 minus one month is 29 Esfand 1404.
    Calendar months are never replaced by 30/90/180/365 fixed days.
    """
    end = parse_date(end)
    if months < 0:
        raise ValueError("months must be non-negative")
    if calendar == GREGORIAN:
        total = end.year * 12 + (end.month - 1) - months
        y, m = divmod(total, 12)
        day = min(end.day, _calendar.monthrange(y, m + 1)[1])
        return pd.Timestamp(_dt.date(y, m + 1, day))
    if calendar == JALALI:
        j = jdatetime.date.fromgregorian(date=end.date())
        total = j.year * 12 + (j.month - 1) - months
        y, m = divmod(total, 12)
        day = min(j.day, _jalali_month_length(y, m + 1))
        return pd.Timestamp(jdatetime.date(y, m + 1, day).togregorian())
    raise ValueError(f"unknown calendar {calendar!r}")
