"""Multi-factor ranking engine (module 06) — the quant-desk / Trendlyne-DVM analog.

Sector-neutral z-scores across Value, Quality, Momentum, Low-Vol, winsorized ±3,
composited per book with the module-06 weights, plus the turnover-hysteresis rule
(hold until below the 40th percentile — churn control the pros price in).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import db
from .fundamentals import latest_fundamentals
from .indicators import momentum_12_1

WEIGHTS = {
    "investing": {"quality": 0.40, "value": 0.35, "momentum": 0.25},
    "trading": {"momentum": 0.60, "quality": 0.25, "value": 0.15},
}
HOLD_EXIT_PERCENTILE = 0.40   # hysteresis: sell only below this composite rank


def _winsor_z(s: pd.Series) -> pd.Series:
    z = (s - s.mean()) / (s.std(ddof=0) or 1.0)
    return z.clip(-3, 3)


def _sector_neutral_z(df: pd.DataFrame, col: str, min_group: int = 5) -> pd.Series:
    """Z-score within sector; sectors too small fall back to the global pool."""
    out = pd.Series(index=df.index, dtype=float)
    global_z = _winsor_z(df[col])
    for sector, grp in df.groupby("sector"):
        idx = grp.index
        out.loc[idx] = _winsor_z(grp[col]) if len(grp) >= min_group else global_z.loc[idx]
    return out


def build_factor_table() -> pd.DataFrame:
    """One row per active symbol: raw factor inputs + sector."""
    rows = []
    with db.connect() as conn:
        stocks = conn.execute(
            "SELECT symbol, industry FROM stocks WHERE active=1").fetchall()
        for sym, industry in stocks:
            px = pd.read_sql_query(
                "SELECT date, close FROM prices_eod WHERE symbol=? AND source='yfinance' "
                "ORDER BY date", conn, params=[sym], parse_dates=["date"])
            if len(px) < 260:
                continue
            close = px.set_index("date")["close"]
            f = latest_fundamentals(sym)
            pe, pb = f.get("pe"), f.get("pb")
            de = f.get("debt_to_equity")
            de = (de / 100 if de and de > 5 else de) if de is not None else None
            rows.append({
                "symbol": sym, "sector": industry or "Unknown",
                "earnings_yield": (1 / pe) if pe and pe > 0 else np.nan,
                "book_yield": (1 / pb) if pb and pb > 0 else np.nan,
                "roe": f.get("roe", np.nan),
                "op_margin": f.get("op_margin", np.nan),
                "neg_leverage": -de if de is not None else np.nan,
                "mom_12_1": momentum_12_1(close),
                "neg_vol": -float(close.pct_change().iloc[-252:].std() * np.sqrt(252)),
            })
    return pd.DataFrame(rows)


def rank_factors(table: pd.DataFrame | None = None) -> pd.DataFrame:
    """Sector-neutral composite ranks per book. NaN inputs score neutral (0)."""
    df = table if table is not None else build_factor_table()
    if df.empty:
        return df
    df = df.set_index("symbol")
    z = pd.DataFrame(index=df.index)
    z["value"] = pd.concat(
        [_sector_neutral_z(df, "earnings_yield"), _sector_neutral_z(df, "book_yield")],
        axis=1).mean(axis=1)
    z["quality"] = pd.concat(
        [_sector_neutral_z(df, "roe"), _sector_neutral_z(df, "op_margin"),
         _sector_neutral_z(df, "neg_leverage")], axis=1).mean(axis=1)
    z["momentum"] = _sector_neutral_z(df, "mom_12_1")
    z["low_vol"] = _sector_neutral_z(df, "neg_vol")
    z = z.fillna(0.0)

    out = df[["sector"]].join(z.round(3))
    for book, w in WEIGHTS.items():
        comp = sum(z[k] * wt for k, wt in w.items())
        out[f"{book}_score"] = comp.round(3)
        out[f"{book}_pct"] = comp.rank(pct=True).round(3)
    return out.sort_values("investing_pct", ascending=False)


def hysteresis_action(current_pct: float, held: bool) -> str:
    """Turnover control: BUY needs top-decile-ish entry handled by screener;
    a held name is kept until it decays below the 40th percentile."""
    if held:
        return "HOLD" if current_pct >= HOLD_EXIT_PERCENTILE else "EXIT"
    return "CANDIDATE" if current_pct >= 0.80 else "IGNORE"
