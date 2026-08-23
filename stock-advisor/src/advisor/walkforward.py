"""Walk-forward validation (knowledge 11) — the quant-desk answer to curve-fitting.

Splits history into sequential folds, runs the strategy fresh in each, and judges
CONSISTENCY, not the headline number: a strategy that only worked in one regime
fails here even if the full-sample backtest looks great.
"""
from __future__ import annotations

import pandas as pd

from .backtest import BTConfig, BTResult, backtest_breakout

WARMUP_DAYS = 260   # each fold carries this much prior data for indicators only


def walk_forward(prices: dict[str, pd.DataFrame], n_folds: int = 4,
                 cfg: BTConfig | None = None) -> dict:
    cfg = cfg or BTConfig()
    all_dates = sorted({d for df in prices.values() for d in df.index})
    if len(all_dates) < (WARMUP_DAYS + 60) * 2:
        return {"note": "insufficient history for walk-forward", "folds": []}

    usable = all_dates[WARMUP_DAYS:]
    fold_size = len(usable) // n_folds
    folds = []
    for k in range(n_folds):
        start = usable[k * fold_size]
        end = usable[min((k + 1) * fold_size, len(usable)) - 1]
        window = {}
        for sym, df in prices.items():
            # warmup slice included so indicators are warm, but trades only count
            # inside the fold (filter below)
            sub = df[df.index <= end]
            if len(sub) >= WARMUP_DAYS + 20:
                window[sym] = sub
        result: BTResult = backtest_breakout(window, cfg)
        trades = result.trades
        if not trades.empty:
            trades = trades[trades["entry_date"] >= start]
        stats = {}
        if not trades.empty:
            wins = trades["net_r"] > 0
            stats = {"n_trades": int(len(trades)),
                     "hit_rate": round(float(wins.mean()), 3),
                     "avg_r": round(float(trades["net_r"].mean()), 3)}
        folds.append({"fold": k + 1, "start": str(start.date()),
                      "end": str(end.date()), **stats})

    with_trades = [f for f in folds if f.get("n_trades")]
    positive = [f for f in with_trades if f["avg_r"] > 0]
    verdict = ("ROBUST: positive expectancy in every fold with trades"
               if with_trades and len(positive) == len(with_trades)
               else "MIXED: expectancy is regime-dependent — deploy at reduced size, "
                    "lean on the regime filter"
               if positive
               else "FAILED: no fold shows positive expectancy — do not deploy")
    return {"folds": folds, "verdict": verdict,
            "folds_positive": f"{len(positive)}/{len(with_trades) or 0}"}
