"""Portfolio return engine: TWR, MWR (XIRR) and wealth change for a brokerage account.

Modules: ``transactions`` (external-flow rules), ``valuation`` (daily table), ``credit``,
``twr``, ``xirr``, ``mwr``, ``wealth_change``, ``horizons``, ``dates``, ``display_policy``,
``quality`` and ``engine`` (end-to-end run). See README.md and docs/.
"""

from .engine import Report, analyse
from .transactions import RULES, TxnType, classify
from .twr import MIN_CAPITAL_DEFAULT, daily_return, daily_returns, horizon_twr
from .xirr import xirr

__all__ = ["Report", "analyse", "RULES", "TxnType", "classify", "MIN_CAPITAL_DEFAULT",
           "daily_return", "daily_returns", "horizon_twr", "xirr"]
__version__ = "1.0.0"
