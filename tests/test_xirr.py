import numpy as np
import pytest

from portfolio_returns.xirr import spreadsheet_xirr, xirr, xnpv


def test_one_year_ten_percent():
    res = xirr(["2025-01-01", "2026-01-01"], [-100, 110])
    assert res.status == "OK" and res.rate == pytest.approx(0.10, abs=1e-12)


def test_matches_spreadsheet_on_ordinary_flows():
    d = ["2025-01-01", "2025-04-10", "2025-09-01", "2026-02-15"]
    c = [-1_000, -500, 300, 1_400]
    res = xirr(d, c)
    assert res.rate == pytest.approx(spreadsheet_xirr(d, c), abs=1e-9)
    assert xnpv(res.rate, d, c) == pytest.approx(0.0, abs=1e-6)


def test_short_period_large_move_where_newton_fails():
    # +10% in two days is about 3.6e7 % a year.
    d, c = ["2026-01-01", "2026-01-03"], [-100, 110]
    res = xirr(d, c)
    assert res.status == "OK"
    assert res.rate == pytest.approx(1.1 ** (365 / 2) - 1, rel=1e-9)
    assert spreadsheet_xirr(d, c) is None


def test_multiple_roots_are_reported():
    # -100 x^2 + 230 x - 132 = 0 with x = 1 + r: roots 10% and 20%.
    res = xirr(["2025-01-01", "2026-01-01", "2027-01-01"], [-100, 230, -132])
    assert res.status == "MULTIPLE_ROOTS"
    assert res.rate == pytest.approx(0.10, abs=1e-10)
    assert res.roots == pytest.approx((0.10, 0.20), abs=1e-10)


@pytest.mark.parametrize("d,c,status", [
    (["2025-01-01", "2026-01-01"], [-100, -10], "NO_SIGN_CHANGE"),
    (["2025-01-01", "2025-01-01"], [-100, 110], "NO_ELAPSED_TIME"),
    (["2025-01-01", "2026-01-01"], [-100, np.nan], "INVALID_INPUT"),
    (["2025-01-01"], [], "INVALID_INPUT"),
])
def test_failure_statuses_never_invent_a_rate(d, c, status):
    res = xirr(d, c)
    assert res.status == status and res.rate is None and not res.ok


def test_total_loss_is_near_minus_one():
    res = xirr(["2025-01-01", "2026-01-01"], [-100, 1e-6])
    assert res.ok and res.rate == pytest.approx(-1.0, abs=1e-6)
