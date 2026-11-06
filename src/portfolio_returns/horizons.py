"""Reporting horizons and their dates.

Every horizon is a window ``(anchor, end]``:

* ``anchor`` is a closing value date. Its value is the starting capital (BV); its own
  daily return is *not* part of the window.
* the first included day is ``anchor + 1 day``; flows from that day to ``end`` count.
* ``end`` is the reporting (as-of) date, included.

TWR, MWR and wealth change for a horizon always use the same anchor and end, and the
cumulative chart starts at 0% on the anchor.

Monthly horizons use Gregorian calendar months with month-end clipping (``1M`` ending
22 Oct 2026 is anchored on the 22 Sep 2026 close and starts on 23 Sep). YTD and yearly
history use standard calendar years.

When the investor started after the requested anchor, the window starts at entry
(``SINCE_ENTRY``). Entry is the last known-zero close before the first funded day when
the data shows one (the first day's performance is then measured from zero), otherwise
the first funded close. Two history policies are supported:

* ``all_since_entry`` (default): every horizon longer than the history falls back to
  since entry, so 6M, 1Y and ALL can show the same number.
* ``nearest_only``: only the shortest incomplete monthly horizon shows a since-entry
  number; longer ones are ``INSUFFICIENT_HISTORY``. An exact anniversary stays in the
  lower bucket.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .dates import GREGORIAN, calendar_year, calendar_year_end, format_date, months_back, parse_date


@dataclass(frozen=True)
class Horizon:
    label: str
    kind: str              # "months", "ytd", "since_start", "year"
    months: int | None = None
    year: int | None = None


STANDARD = (Horizon("1M", "months", 1), Horizon("3M", "months", 3), Horizon("6M", "months", 6),
            Horizon("1Y", "months", 12), Horizon("YTD", "ytd"), Horizon("ALL", "since_start"))
EXTENDED = STANDARD[:4] + (Horizon("3Y", "months", 36), Horizon("5Y", "months", 60)) + STANDARD[4:]


@dataclass
class Window:
    label: str
    requested_anchor: pd.Timestamp | None
    anchor: pd.Timestamp | None
    end: pd.Timestamp | None
    basis: str   # FULL_PERIOD, SINCE_ENTRY, INSUFFICIENT_HISTORY, NO_INVESTMENT, NO_ELAPSED_TIME
    note: str = ""

    @property
    def usable(self) -> bool:
        return self.basis in ("FULL_PERIOD", "SINCE_ENTRY")

    @property
    def first_day(self) -> pd.Timestamp | None:
        return None if self.anchor is None else self.anchor + pd.Timedelta(1, "D")

    @property
    def days(self) -> int:
        return 0 if self.anchor is None or self.end is None else (self.end - self.anchor).days

    def describe(self) -> str:
        if self.anchor is None:
            return self.basis
        return f"{format_date(self.first_day)} to {format_date(self.end)}"


def entry_anchor(daily: pd.DataFrame) -> pd.Timestamp | None:
    """Anchor for since-entry windows (see module docstring)."""
    tv = daily["total_value"]
    funded = tv.index[tv > 0]
    if not len(funded):
        return None
    first = funded[0]
    prev = first - pd.Timedelta(1, "D")
    if prev in tv.index and tv[prev] == 0:
        return prev
    return first


def resolve_windows(daily: pd.DataFrame, as_of, horizons=STANDARD, calendar: str = GREGORIAN,
                    history_policy: str = "all_since_entry") -> list[Window]:
    """Resolve each horizon to an effective window on the daily table."""
    if history_policy not in ("all_since_entry", "nearest_only"):
        raise ValueError("history_policy must be 'all_since_entry' or 'nearest_only'")
    end = parse_date(as_of)
    entry = entry_anchor(daily)
    starts_mid_life = entry is not None and entry == daily.index.min() and daily["total_value"].iloc[0] > 0
    out: list[Window] = []
    since_entry_used = False
    order = sorted(horizons, key=lambda h: (h.kind != "months", h.months or 0))
    for h in order:
        if h.kind == "months":
            req = months_back(end, h.months, calendar)
        elif h.kind == "ytd":
            req = calendar_year_end(calendar_year(end) - 1)
        elif h.kind == "since_start":
            req = entry
        elif h.kind == "year":
            req = calendar_year_end(h.year - 1)
        else:
            raise ValueError(f"unknown horizon kind {h.kind!r}")
        w_end = min(end, calendar_year_end(h.year)) if h.kind == "year" else end
        if w_end not in daily.index:
            out.append(Window(h.label, req, None, w_end, "INSUFFICIENT_HISTORY", "no value on the end date"))
            continue
        if entry is None or entry > w_end:
            out.append(Window(h.label, req, None, w_end, "NO_INVESTMENT", "no funded day before the end date"))
            continue
        note = "history starts mid-investment; earlier performance is unknown" if starts_mid_life else ""
        if h.kind == "since_start":
            anchor, basis = entry, "SINCE_ENTRY"
        elif req >= entry and not (history_policy == "nearest_only" and h.kind == "months" and req == entry):
            anchor, basis, note = req, "FULL_PERIOD", ""
        elif history_policy == "nearest_only" and h.kind == "months" and since_entry_used:
            out.append(Window(h.label, req, None, w_end, "INSUFFICIENT_HISTORY",
                              "longer than the history; only the nearest horizon shows since entry"))
            continue
        else:
            anchor, basis = entry, "SINCE_ENTRY"
            if h.kind == "months":
                since_entry_used = True
        if anchor >= w_end:
            out.append(Window(h.label, req, anchor, w_end, "NO_ELAPSED_TIME", "anchor and end are the same day"))
            continue
        out.append(Window(h.label, req, anchor, w_end, basis, note))
    by_label = {w.label: w for w in out}
    return [by_label[h.label] for h in horizons]


def calendar_year_horizons(daily: pd.DataFrame, as_of) -> tuple[Horizon, ...]:
    """One horizon per calendar year from the entry year to the as-of year."""
    entry = entry_anchor(daily)
    end = parse_date(as_of)
    if entry is None:
        return ()
    first_year = calendar_year(entry + pd.Timedelta(1, "D"))
    return tuple(Horizon(str(y), "year", year=y) for y in range(first_year, calendar_year(end) + 1))
