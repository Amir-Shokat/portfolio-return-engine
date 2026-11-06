"""Draw the PNG charts in docs/ from the synthetic example account.

    pip install -e ".[charts]"
    python scripts/make_charts.py
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from portfolio_returns import analyse  # noqa: E402
from portfolio_returns.wealth_change import wealth_change  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
BLUE, ORANGE, AQUA, RED = "#2a78d6", "#eb6834", "#1baf7a", "#e34948"
INK, MUTED, GRID, SURFACE = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"

plt.rcParams.update({"font.size": 10, "axes.edgecolor": GRID, "axes.labelcolor": MUTED, "xtick.color": MUTED,
                     "ytick.color": MUTED, "axes.spines.top": False, "axes.spines.right": False,
                     "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "axes.titlecolor": INK,
                     "axes.titlesize": 11, "axes.titleweight": "bold"})

rep = analyse(pd.read_csv(ROOT / "examples/transactions.csv"), pd.read_csv(ROOT / "examples/daily_values.csv"),
              "2026-10-21")

# 1. Cumulative TWR since entry, rebased to 0%, with external flow days marked.
cum = rep.charts["ALL"] * 100
fig, ax = plt.subplots(figsize=(8, 3.6))
ax.axhline(0, color=GRID, lw=1)
ax.plot(cum.index, cum.values, color=BLUE, lw=2)
flows = rep.daily[(rep.daily["inflow"] > 0) | (rep.daily["outflow"] > 0)]
for d in flows.index:
    ax.axvline(d, color=MUTED, lw=0.6, ls=":", alpha=0.6)
ax.set_title("Cumulative time-weighted return since entry (%)", loc="left")
ax.text(0.01, 0.02, "dotted lines: days with deposits, withdrawals, credit or transfers", transform=ax.transAxes,
        color=MUTED, fontsize=8)
ax.annotate(f"{cum.iloc[-1]:+.2f}%", (cum.index[-1], cum.iloc[-1]), xytext=(4, 0), textcoords="offset points",
            color=INK, va="center", fontsize=9)
ax.grid(axis="y", color=GRID, lw=0.6)
fig.tight_layout()
fig.savefig(DOCS / "cumulative_twr.png", dpi=150)
plt.close(fig)

# 2. TWR and MWR per horizon.
h = rep.horizons.set_index("horizon")
labels = list(h.index)
x = range(len(labels))
fig, ax = plt.subplots(figsize=(8, 3.6))
ax.axhline(0, color=MUTED, lw=0.8)
w = 0.36
for off, col, name, colr in [(-w / 2 - 0.01, "twr", "TWR (investment skill)", BLUE),
                             (w / 2 + 0.01, "mwr", "MWR (investor's own return)", ORANGE)]:
    vals = h[col].astype(float) * 100
    ax.bar([i + off for i in x], vals, width=w, color=colr, label=name)
    for i, v in zip(x, vals):
        ax.annotate(f"{v:+.1f}", (i + off, v), xytext=(0, 3 if v >= 0 else -11), textcoords="offset points",
                    ha="center", fontsize=8, color=INK)
ax.set_xticks(list(x), labels)
ax.set_title("TWR and MWR by horizon (%, not annualised)", loc="left")
ax.legend(frameon=False, loc="upper left", fontsize=8)
ax.grid(axis="y", color=GRID, lw=0.6)
ax.set_axisbelow(True)
fig.tight_layout()
fig.savefig(DOCS / "twr_vs_mwr.png", dpi=150)
plt.close(fig)

# 3. Wealth-change waterfall for 1Y, flows split by kind.
row = h.loc["1Y"]
wf = wealth_change(rep.daily, row["anchor"], row["end"]).waterfall()
wf_amt = wf["amount"] / 1e6
level = wf["level"] / 1e6
fig, ax = plt.subplots(figsize=(8, 3.8))
prev = 0.0
for i, (step, amt, lev) in enumerate(zip(wf["step"], wf_amt, level)):
    if step in ("Start value", "End value"):
        ax.bar(i, lev, color=MUTED, width=0.6)
        top = lev
    else:
        ax.bar(i, amt, bottom=prev, color=AQUA if amt >= 0 else RED, width=0.6)
        top = max(prev, prev + amt)
    ax.annotate(f"{amt:+,.0f}" if step not in ("Start value", "End value") else f"{lev:,.0f}", (i, top),
                xytext=(0, 3), textcoords="offset points", ha="center", fontsize=8, color=INK)
    prev = lev
ax.set_xticks(range(len(wf)), [s.replace(", net", "\n(net)").replace("Investment gain", "Investment\ngain")
                                for s in wf["step"]], fontsize=8)
ax.set_ylim(0, float(level.max()) * 1.1)
ax.set_title("Wealth change over 1Y, millions: start + gain + flows = end", loc="left")
ax.grid(axis="y", color=GRID, lw=0.6)
ax.set_axisbelow(True)
fig.tight_layout()
fig.savefig(DOCS / "wealth_change_waterfall.png", dpi=150)
plt.close(fig)
print("charts written to", DOCS)
