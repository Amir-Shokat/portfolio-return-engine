"""ISO/Gregorian date parsing and calendar-month arithmetic."""

from __future__ import annotations

import calendar as _calendar
import datetime as _dt

import pandas as pd

GREGORIAN = "gregorian"


def parse_date(value) -> pd.Timestamp:
    """Parse an ISO/Gregorian date into a timezone-naive midnight timestamp."""
    if isinstance(value, (pd.Timestamp, _dt.datetime, _dt.date)) and not isinstance(value, str):
        ts = pd.Timestamp(value)
    else:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            raise ValueError("missing date")
        ts = pd.Timestamp(str(value))
    if ts.tzinfo is not None:
        raise ValueError("dates must be timezone-naive")
    return ts.normalize()


def format_date(value) -> str:
    """Format a date as ISO ``YYYY-MM-DD``."""
    return parse_date(value).strftime("%Y-%m-%d")


def calendar_year(value) -> int:
    return parse_date(value).year


def calendar_year_end(year: int) -> pd.Timestamp:
    return pd.Timestamp(_dt.date(year, 12, 31))


def months_back(end, months: int, calendar: str = GREGORIAN) -> pd.Timestamp:
    """The same day ``months`` calendar months earlier, clipped to month end."""
    if calendar != GREGORIAN:
        raise ValueError("only the Gregorian calendar is supported")
    end = parse_date(end)
    if months < 0:
        raise ValueError("months must be non-negative")
    total = end.year * 12 + (end.month - 1) - months
    year, month0 = divmod(total, 12)
    day = min(end.day, _calendar.monthrange(year, month0 + 1)[1])
    return pd.Timestamp(_dt.date(year, month0 + 1, day))
