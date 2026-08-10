"""Backtester for the module-05 breakout setup — the evidence layer.

Deliberately simple and honest: next-day-open entries, ATR/structural stops,
scale-out at 1.5R with a 2.5R final target, time stop, and real Indian costs
(~0.3% per round trip large caps; default 0.5% to be conservative). No intrabar
fantasy fills: stop and target both touched in one bar counts as a stop (worst case).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from . import indicators as ind


@dataclass
class BTConfig:
    risk_pct: float = 0.0075
    cost_round_trip: float = 0.005
    time_stop_days: int = 60
    vol_mult: float = 1.5          # breakout volume confirmation
    initial_capital: float = 1_000_000


@dataclass
class BTResult:
    trades: pd.DataFrame
    stats: dict = field(default_factory=dict)


def _detect_breakouts(df: pd.DataFrame, cfg: BTConfig) -> list[int]:
    """Indices where a 60d-high breakout with volume confirmation fires (module 05)."""
    close, high, vol = df["close"], df["high"], df["volume"]
    sma200 = close.rolling(200).mean()
    hi60 = high.shift(1).rolling(60).max()
    vol50 = vol.rolling(50).mean()
    fired = ((close > hi60) & (close > sma200) & (sma200 > sma200.shift(21))
             & (vol > cfg.vol_mult * vol50))
    return [i for i, v in enumerate(fired.values) if v and i < len(df) - 2]


def backtest_breakout(prices: dict[str, pd.DataFrame],
                      cfg: BTConfig | None = None) -> BTResult:
    """Run the breakout strategy over {symbol: OHLCV df}. One open trade per symbol."""
    cfg = cfg or BTConfig()
    records = []
    for sym, df in prices.items():
        if len(df) < 260:
            continue
        atr = ind.atr(df, 14)
        entries = _detect_breakouts(df, cfg)
        i = 0
        busy_until = -1
        for e in entries:
            if e <= busy_until:
                continue
            entry_i = e + 1                      # next-day open, no lookahead
            entry = float(df["open"].iloc[entry_i])
            stop = entry - 2 * float(atr.iloc[e])
            risk = entry - stop
            if risk <= 0:
                continue
            t1, t2 = entry + 1.5 * risk, entry + 2.5 * risk
            exit_price, exit_i, reason = None, None, None
            scaled = False
            realized = 0.0
            for j in range(entry_i, min(entry_i + cfg.time_stop_days, len(df))):
                lo, hi = float(df["low"].iloc[j]), float(df["high"].iloc[j])
                if lo <= stop:                   # worst-case: stop checked first
                    exit_price, exit_i, reason = stop, j, "stop"
                    break
                if not scaled and hi >= t1:
                    realized += 0.5 * (t1 - entry)   # scale out half at 1.5R
                    scaled = True
                    stop = max(stop, entry)          # move stop to breakeven
                if scaled and hi >= t2:
                    exit_price, exit_i, reason = t2, j, "target"
                    break
            if exit_price is None:
                exit_i = min(entry_i + cfg.time_stop_days, len(df)) - 1
                exit_price, reason = float(df["close"].iloc[exit_i]), "time"
            weight = 0.5 if scaled else 1.0
            realized += weight * (exit_price - entry)
            gross_r = realized / risk
            net_r = gross_r - cfg.cost_round_trip * entry / risk
            records.append({"symbol": sym, "entry_date": df.index[entry_i],
                            "exit_date": df.index[exit_i], "entry": entry,
                            "stop_init": entry - risk, "exit": exit_price,
                            "reason": reason, "gross_r": gross_r, "net_r": net_r})
            busy_until = exit_i
            i += 1

    trades = pd.DataFrame(records)
    stats = {}
    if not trades.empty:
        wins = trades["net_r"] > 0
        stats = {
            "n_trades": len(trades),
            "hit_rate": round(float(wins.mean()), 3),
            "avg_r": round(float(trades["net_r"].mean()), 3),
            "profit_factor": round(
                float(trades.loc[wins, "net_r"].sum()
                      / max(1e-9, -trades.loc[~wins, "net_r"].sum())), 2),
            "expectancy_pct_per_trade": round(
                float(trades["net_r"].mean() * cfg.risk_pct * 100), 4),
        }
    return BTResult(trades=trades, stats=stats)


def load_prices_from_db(symbols: list[str] | None = None) -> dict[str, pd.DataFrame]:
    from . import db
    from .universe import active_symbols

    out = {}
    with db.connect() as conn:
        for sym in symbols or active_symbols():
            df = pd.read_sql_query(
                "SELECT date, open, high, low, close, volume FROM prices_eod "
                "WHERE symbol=? AND source='yfinance' ORDER BY date",
                conn, params=[sym], parse_dates=["date"]).set_index("date")
            if not df.empty:
                out[sym] = df
    return out
