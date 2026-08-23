"""Scout/screener: ties engines together into ranked shortlists (modules 05/06).

Conviction weights per book (module 01): investing 70/20/10 fund/tech/RS,
trading 20/60/20. Regime filter (module 05): trading book returns no new longs
when the regime is risk-off.
"""
from __future__ import annotations

import pandas as pd

from . import db, levels, regime as regime_mod, technical
from .fundamentals import fundamental_score, latest_fundamentals

VETO_FLAGS = {"high_leverage"}  # module-02 hard vetoes available from free data


def _load_symbol_df(conn, symbol: str) -> pd.DataFrame:
    df = pd.read_sql_query(
        "SELECT date, open, high, low, close, volume FROM prices_eod "
        "WHERE symbol=? AND source='yfinance' ORDER BY date",
        conn, params=[symbol], parse_dates=["date"])
    return df.set_index("date")


def run_screen(book: str = "trading", capital: float = 1_000_000,
               top_n: int = 15, min_turnover: float = 1e7) -> dict:
    """Returns {'regime': RegimeReading|None, 'candidates': DataFrame, 'plans': [TradePlan]}."""
    assert book in ("investing", "trading")
    from .universe import active_symbols

    reading = regime_mod.compute_regime(prev_state=regime_mod.last_state())

    rows = []
    with db.connect() as conn:
        for sym in active_symbols():
            df = _load_symbol_df(conn, sym)
            f = technical.compute_features(df)
            if f is None or (f["median_turnover"] or 0) < min_turnover:
                continue
            fund = latest_fundamentals(sym)
            fscore, flags = fundamental_score(fund)
            if VETO_FLAGS & set(flags):
                continue
            tscore = technical.technical_score(f)
            setups = technical.detect_setups(f, fundamental_score=fscore)
            rows.append({"symbol": sym, "fund_score": fscore, "tech_score": tscore,
                         "mom_12_1": f["mom_12_1"], "stage": technical.stage(f),
                         "setups": setups, "flags": flags, "features": f})

    if not rows:
        return {"regime": reading, "candidates": pd.DataFrame(), "plans": []}

    cand = pd.DataFrame(rows)
    # Relative strength percentile across the scanned universe (12-1 momentum rank)
    cand["rs_pct"] = cand["mom_12_1"].rank(pct=True).fillna(0) * 100

    if book == "investing":
        cand["conviction"] = (0.70 * cand["fund_score"] + 0.20 * cand["tech_score"]
                              + 0.10 * cand["rs_pct"])
        pool = cand[cand["stage"] != 4]                     # never buy Stage 4
    else:
        cand["conviction"] = (0.20 * cand["fund_score"] + 0.60 * cand["tech_score"]
                              + 0.20 * cand["rs_pct"])
        pool = cand[cand["setups"].map(len) > 0]            # trading needs a live setup
        if reading is not None and not reading.risk_on():
            pool = pool.iloc[0:0]                            # regime filter: cash

    pool = pool.sort_values("conviction", ascending=False).head(top_n)

    plans = []
    if book == "trading":
        for _, r in pool.iterrows():
            plan = levels.propose_levels(r["symbol"], r["features"], r["setups"][0],
                                         capital=capital)
            if plan:
                plans.append(plan)

    cols = ["symbol", "conviction", "fund_score", "tech_score", "rs_pct",
            "stage", "setups", "flags"]
    return {"regime": reading, "candidates": pool[cols].reset_index(drop=True),
            "plans": plans}
