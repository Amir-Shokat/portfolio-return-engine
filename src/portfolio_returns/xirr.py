"""Dated internal rate of return (XIRR), Actual/365, with explicit failure statuses.

Solves for the annual rate ``r`` in::

    sum_i  C_i / (1 + r) ** ((d_i - d_0).days / 365) = 0

with investor-perspective signs (money put in negative, money taken out positive), the
same equation as the spreadsheet ``XIRR`` function.

Why not a plain Newton iteration from a 10% guess (what spreadsheets do)?

* Short periods with large moves have huge annual rates (+10% in two days is about
  3.6e7 % a year); Newton on ``r`` overshoots or crosses ``r <= -1`` and fails.
* Cash flows that change sign more than once can have several valid roots; Newton
  returns whichever one it falls into and says nothing.

So the solver works on ``y = log(1 + r)`` (always defined), scans a wide grid of ``y`` for
sign changes, refines every bracket with a safeguarded Newton step (bisection whenever
Newton leaves the bracket), checks the scaled NPV residual, and reports all roots.

Statuses: ``OK``, ``MULTIPLE_ROOTS`` (the root closest to 0% is returned and all roots are
listed), ``NO_SIGN_CHANGE`` (all flows have one sign), ``NO_ELAPSED_TIME``, ``NO_ROOT``,
``NOT_CONVERGED`` and ``INVALID_INPUT``. A rate is never made up when the status says it
could not be solved.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

DAYS_PER_YEAR = 365.0
_GRID = np.concatenate([np.linspace(-40.0, -5.0, 351), np.linspace(-5.0, 5.0, 2001)[1:],
                        np.linspace(5.0, 120.0, 1151)[1:]])


@dataclass
class XirrResult:
    rate: float | None
    status: str
    roots: tuple = field(default_factory=tuple)
    residual: float | None = None
    message: str = ""

    @property
    def ok(self) -> bool:
        return self.status in ("OK", "MULTIPLE_ROOTS")


def _prepare(dates, amounts):
    d = pd.to_datetime(pd.Series(list(dates))).dt.normalize()
    c = pd.Series(np.asarray(list(amounts), dtype=float))
    if len(d) != len(c) or len(c) == 0:
        raise ValueError("dates and amounts must be non-empty and the same length")
    if not np.isfinite(c.to_numpy()).all() or d.isna().any():
        raise ValueError("dates and amounts must be valid and finite")
    s = c.groupby(d.to_numpy()).sum()          # same-date flows can be netted for the IRR
    s = s[s != 0]
    return s.index, s.to_numpy()


def xnpv(rate: float, dates, amounts) -> float:
    """Net present value at an annual ``rate`` with Actual/365 discounting from the first date."""
    d = pd.to_datetime(pd.Series(list(dates)))
    t = ((d - d.min()).dt.days / DAYS_PER_YEAR).to_numpy()
    return float(np.sum(np.asarray(list(amounts), dtype=float) / (1.0 + rate) ** t))


class _Npv:
    """NPV as a function of y = log(1 + r), scaled so it never overflows."""

    def __init__(self, t, c):
        self.t, self.c = t, c / np.max(np.abs(c))

    def terms(self, y):
        e = -y * self.t
        return self.c * np.exp(e - e.max())

    def f(self, y):
        return float(self.terms(y).sum())

    def rel(self, y):
        v = self.terms(y)
        return float(v.sum() / np.abs(v).sum())

    def df(self, y):
        return float((-self.t * self.terms(y)).sum())


def _refine(npv: _Npv, lo, hi):
    """Safeguarded Newton inside a sign-change bracket [lo, hi]."""
    flo = npv.rel(lo)
    y = 0.5 * (lo + hi)
    for _ in range(200):
        fy = npv.rel(y)
        if fy == 0.0 or hi - lo < 1e-14:
            return y
        if (fy > 0) == (flo > 0):
            lo, flo = y, fy
        else:
            hi = y
        # Newton step on the unshifted scale; accept only if it stays inside the bracket.
        terms = npv.terms(y)
        slope = float((-npv.t * terms).sum())
        step = terms.sum() / slope if slope else np.inf
        candidate = y - step
        y = candidate if lo < candidate < hi and np.isfinite(candidate) else 0.5 * (lo + hi)
    return y


def xirr(dates, amounts, guess: float = 0.1) -> XirrResult:
    """Robust XIRR. See the module docstring for the method and the statuses."""
    dates, amounts = list(dates), list(amounts)
    try:
        when, c = _prepare(dates, amounts)
    except ValueError as exc:
        return XirrResult(None, "INVALID_INPUT", message=str(exc))
    if pd.to_datetime(pd.Series(dates)).dt.normalize().nunique() == 1:
        # Checked before netting: same-date flows would otherwise net to one flow and be
        # reported as NO_SIGN_CHANGE, which hides the real reason.
        return XirrResult(None, "NO_ELAPSED_TIME", message="all flows fall on the same date")
    if not ((c > 0).any() and (c < 0).any()):
        return XirrResult(None, "NO_SIGN_CHANGE", message="need at least one positive and one negative flow")
    t = np.asarray((pd.DatetimeIndex(when) - when.min()).days, dtype=float) / DAYS_PER_YEAR
    if t.max() <= 0:
        return XirrResult(None, "NO_ELAPSED_TIME", message="all flows fall on the same date")
    npv = _Npv(t, c)
    vals = np.array([npv.rel(y) for y in _GRID])
    roots = [float(y) for y, v in zip(_GRID, vals) if v == 0.0]
    for i in range(len(_GRID) - 1):
        if vals[i] * vals[i + 1] < 0:
            roots.append(_refine(npv, _GRID[i], _GRID[i + 1]))
    if not roots:
        # A tangent root (no sign change) can still exist: try Newton from the guess.
        y = math.log1p(guess) if guess > -1 else 0.0
        for _ in range(100):
            slope = npv.df(y)
            if slope == 0 or not np.isfinite(slope):
                break
            y -= npv.f(y) / slope
            if not np.isfinite(y) or abs(y) > 120:
                break
        if np.isfinite(y) and abs(npv.rel(y)) < 1e-10:
            roots = [y]
        else:
            return XirrResult(None, "NO_ROOT", message="no rate between -100% and the search limit solves the equation")
    unique: list[float] = []
    for y in sorted(roots):
        if not unique or abs(y - unique[-1]) > 1e-9:
            unique.append(y)
    rates = tuple(math.expm1(y) for y in unique)
    best = min(unique, key=abs)
    residual = npv.rel(best)
    if abs(residual) > 1e-9:
        return XirrResult(None, "NOT_CONVERGED", rates, residual, "residual check failed")
    status = "OK" if len(unique) == 1 else "MULTIPLE_ROOTS"
    msg = "" if status == "OK" else f"{len(unique)} rates solve the equation; the one closest to 0% is returned"
    return XirrResult(math.expm1(best), status, rates, residual, msg)


def spreadsheet_xirr(dates, amounts, guess: float = 0.1, max_iter: int = 100, tol: float = 1e-10):
    """Plain Newton iteration on ``r`` from ``guess``, as spreadsheet XIRR does.

    Kept to compare against the robust solver. Returns ``None`` where a spreadsheet would
    show an error (no convergence, or the iteration leaves ``r > -1``).
    """
    when, c = _prepare(dates, amounts)
    t = np.asarray((pd.DatetimeIndex(when) - when.min()).days, dtype=float) / DAYS_PER_YEAR
    r = guess
    for _ in range(max_iter):
        if r <= -1:
            return None
        with np.errstate(all="ignore"):
            disc = (1.0 + r) ** t
            f = np.sum(c / disc)
            df = np.sum(-t * c / (disc * (1.0 + r)))
        if not (np.isfinite(f) and np.isfinite(df)) or df == 0:
            return None
        new = r - f / df
        if abs(new - r) < tol:
            return float(new) if new > -1 else None
        r = new
    return None
