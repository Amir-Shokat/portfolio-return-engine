from pathlib import Path

import pandas as pd
import pytest

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def make_daily(values, inflow=None, outflow=None, start="2026-01-01"):
    """A minimal daily table: total value and gross flows, one row per day."""
    n = len(values)
    idx = pd.date_range(start, periods=n, freq="D", name="date")
    inflow = inflow or [0.0] * n
    outflow = outflow or [0.0] * n
    df = pd.DataFrame({"total_value": values, "inflow": inflow, "outflow": outflow}, index=idx)
    df["net_flow"] = df["inflow"] - df["outflow"]
    return df


@pytest.fixture
def daily_factory():
    return make_daily


@pytest.fixture(scope="session")
def example_frames():
    return (pd.read_csv(EXAMPLES / "transactions.csv"), pd.read_csv(EXAMPLES / "daily_values.csv"),
            pd.read_csv(EXAMPLES / "transactions_with_unknown.csv"))
