"""Market regime state machine (module 10) — indicator-driven, no LLM.

Signals available from our own DB (breadth, equal-weight index drawdown/trend,
correlation proxy). External signals (India VIX, credit spreads, PMI) are optional
inputs; absent data widens uncertainty but never blocks a reading.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import pandas as pd

from . import db
from .indicators import sma

STATES = ["EXPANSION", "CAUTION", "STRESS", "CRISIS", "RECOVERY"]


@dataclass
class RegimeReading:
    state: str
    breadth_200: float          # % of universe above its 200SMA
    breadth_50: float
    index_drawdown: float       # equal-weight universe index drawdown from 1y high
    index_above_200sma: bool
    signals: list[str]

    def risk_on(self) -> bool:
        return self.state in ("EXPANSION", "RECOVERY")


def _universe_panel(min_days: int = 220) -> pd.DataFrame:
    """Close-price panel (date × symbol) for active universe from the DB."""
    with db.connect() as conn:
        df = pd.read_sql_query(
            """
            SELECT p.date, p.symbol, p.close FROM prices_eod p
            JOIN stocks s ON s.symbol = p.symbol
            WHERE s.active=1 AND p.source='yfinance'
            """,
            conn, parse_dates=["date"],
        )
    if df.empty:
        return pd.DataFrame()
    panel = df.pivot_table(index="date", columns="symbol", values="close")
    return panel.dropna(axis=1, thresh=min_days)


def compute_regime(panel: pd.DataFrame | None = None,
                   prev_state: str | None = None) -> RegimeReading | None:
    panel = panel if panel is not None else _universe_panel()
    if panel.empty or len(panel) < 220:
        return None

    above200 = panel.iloc[-1] > panel.rolling(200).mean().iloc[-1]
    above50 = panel.iloc[-1] > panel.rolling(50).mean().iloc[-1]
    breadth_200 = float(above200.mean())
    breadth_50 = float(above50.mean())

    eq_index = panel.pct_change().mean(axis=1).add(1).cumprod()
    dd = float(eq_index.iloc[-1] / eq_index.iloc[-252:].max() - 1)
    idx_above = bool(eq_index.iloc[-1] > sma(eq_index, 200).iloc[-1])

    signals: list[str] = []
    if breadth_200 < 0.25:
        signals.append("breadth_washout")
    if dd < -0.10:
        signals.append("drawdown_gt_10")
    if dd < -0.20:
        signals.append("drawdown_gt_20")
    if not idx_above:
        signals.append("index_below_200sma")

    # State resolution (2 confirming signals to escalate — module 10 dwell rule)
    if dd < -0.20 and breadth_200 < 0.20:
        state = "CRISIS"
    elif dd < -0.10 and (not idx_above or breadth_200 < 0.35):
        state = "STRESS"
    elif (not idx_above) or breadth_200 < 0.40:
        state = "CAUTION"
    else:
        state = "EXPANSION"
    # Recovery: washout in recent past + breadth thrust now
    if state in ("EXPANSION", "CAUTION") and prev_state in ("STRESS", "CRISIS"):
        if breadth_50 > 0.55:
            state = "RECOVERY"
            signals.append("breadth_thrust")

    return RegimeReading(state=state, breadth_200=round(breadth_200, 3),
                         breadth_50=round(breadth_50, 3),
                         index_drawdown=round(dd, 3),
                         index_above_200sma=idx_above, signals=signals)


def record_regime(reading: RegimeReading) -> None:
    with db.connect() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS regime_log (
                   run_at TEXT, state TEXT, breadth_200 REAL, breadth_50 REAL,
                   index_drawdown REAL, signals TEXT)""")
        conn.execute(
            "INSERT INTO regime_log VALUES (?, ?, ?, ?, ?, ?)",
            (datetime.now(timezone.utc).isoformat(timespec="seconds"), reading.state,
             reading.breadth_200, reading.breadth_50, reading.index_drawdown,
             ",".join(reading.signals)),
        )


def last_state() -> str | None:
    with db.connect() as conn:
        try:
            row = conn.execute(
                "SELECT state FROM regime_log ORDER BY run_at DESC LIMIT 1").fetchone()
        except Exception:
            return None
    return row[0] if row else None
