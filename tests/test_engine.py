import numpy as np
import pandas as pd
import pytest

from portfolio_returns import analyse
from portfolio_returns.cli import main
from portfolio_returns.quality import unexplained_changes
from portfolio_returns.transactions import classify
from portfolio_returns.valuation import build_daily_table

AS_OF = "2026-10-21"


@pytest.fixture(scope="module")
def report(example_frames):
    t, v, _ = example_frames
    return analyse(t, v, AS_OF)


def test_example_runs_cleanly(report):
    assert set(report.audit["status"]) <= {"external", "internal"}
    assert report.controls["invalid_days"] == 0
    assert (report.horizons["twr_status"] == "CALCULATED").all()


def test_every_horizon_adds_up(report):
    h = report.horizons
    assert np.allclose(h["bv"] + h["wc"] + h["net_flow"], h["ev"])


def test_calendar_years_link_to_all(report):
    assert report.horizons.attrs["years_link_to_all"] is True
    assert list(report.years["horizon"]) == ["2025", "2026"]


def test_chart_starts_at_zero(report):
    for series in report.charts.values():
        assert series.iloc[0] == 0.0


def test_same_day_deposit_and_withdrawal_in_daily_table(report):
    # The synthetic event falls on a weekend and is posted on the next session.
    day = report.daily.loc["2026-05-11"]
    assert day["inflow"] == day["outflow"] == 200_000_000


def test_unknown_type_blocks_only_windows_that_contain_it(example_frames):
    t, v, tu = example_frames
    rep = analyse(tu, v, AS_OF).horizons.set_index("horizon")
    assert rep.at["1M", "twr_status"] == "CALCULATED"           # 2026-09-01 is before the 1M window
    for h in ["3M", "6M", "1Y", "YTD", "ALL"]:
        assert rep.at[h, "twr_status"] == "RETURN_UNAVAILABLE"
        assert rep.at[h, "wc_display"] == "HIDDEN"


def test_cli(example_frames, capsys, tmp_path):
    from conftest import EXAMPLES
    out = tmp_path / "h.csv"
    assert main(["--transactions", str(EXAMPLES / "transactions.csv"), "--values",
                 str(EXAMPLES / "daily_values.csv"), "--as-of", AS_OF, "--years", "--csv", str(out)]) == 0
    text = capsys.readouterr().out
    assert "Horizon" in text and "Calendar years link to ALL: True" in text
    assert len(pd.read_csv(out)) == 6


def test_levels_carry_forward_flows_do_not():
    v = pd.DataFrame({"date": ["2026-05-01", "2026-05-04"], "cash": [100.0, 120.0], "holdings": [0.0, 0.0]})
    a = classify(pd.DataFrame({"date": ["2026-05-02"], "type": ["DEPOSIT"], "amount": [20.0]}))
    d, warnings, _ = build_daily_table(v, a)
    assert d["total_value"].tolist() == [100, 100, 100, 120]
    assert d["inflow"].tolist() == [0, 20, 0, 0]
    assert any("FLOW_ON_STALE_VALUE" in w for w in warnings)


def test_missing_and_conflicting_values_are_unknown():
    v = pd.DataFrame({"date": ["2026-05-01", "2026-05-02", "2026-05-03", "2026-05-03"],
                      "cash": [100.0, None, 5.0, 6.0], "holdings": [0.0, 0.0, 0.0, 0.0]})
    d, warnings, _ = build_daily_table(v, classify(pd.DataFrame(columns=["date", "type", "amount"])))
    assert d["flag"].fillna("").tolist() == ["", "MISSING_VALUATION", "DUPLICATE_DAILY_RECORD"]
    assert warnings


def test_late_deposit_is_flagged_by_quality_check():
    idx = pd.date_range("2026-05-01", periods=3, name="date")
    d = pd.DataFrame({"total_value": [100e6, 200e6, 201e6], "inflow": [0, 0, 100e6],
                      "net_flow": [0, 0, 100e6]}, index=idx)
    q = unexplained_changes(d)
    assert q.loc["2026-05-02", "code"] == "LIKELY_LATE_FLOW"
