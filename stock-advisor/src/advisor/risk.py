"""Portfolio risk analytics (module 04) — the Aladdin-for-one-person layer.

Shrinkage covariance (Ledoit-Wolf constant-correlation target), parametric and
historical VaR, CVaR (expected shortfall), stress scenarios replaying the crisis
library, correlation diagnostics, and risk-based weight suggestions.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import db

TRADING_DAYS = 252

# Crisis library (module 10): 1-month equity index shocks to replay through beta.
STRESS_SCENARIOS = {
    "GFC_2008_worst_month": -0.26,
    "taper_2013": -0.11,
    "covid_2020_crash": -0.30,
    "rate_shock_2022": -0.10,
    "single_sector_blowup": -0.08,   # applied portfolio-wide as contagion floor
}


def returns_panel(symbols: list[str], min_days: int = 200) -> pd.DataFrame:
    """Daily close-to-close returns panel (date × symbol) from the DB."""
    frames = {}
    with db.connect() as conn:
        for sym in symbols:
            px = pd.read_sql_query(
                "SELECT date, close FROM prices_eod WHERE symbol=? AND source='yfinance' "
                "ORDER BY date", conn, params=[sym], parse_dates=["date"])
            if len(px) >= min_days:
                frames[sym] = px.set_index("date")["close"].pct_change()
    return pd.DataFrame(frames).dropna(how="all").dropna(axis=0)


def shrink_cov(returns: pd.DataFrame, shrink: float = 0.3) -> pd.DataFrame:
    """Covariance shrunk toward the constant-correlation target (Ledoit-Wolf
    style). `shrink` is a fixed intensity — honest simplification: the optimal
    LW intensity estimator adds complexity for little gain at this universe size;
    0.3 is a defensible practitioner default for ~1-2y daily data."""
    S = returns.cov().values
    std = np.sqrt(np.diag(S))
    corr = S / np.outer(std, std)
    n = corr.shape[0]
    avg_r = (corr.sum() - n) / (n * (n - 1)) if n > 1 else 0.0
    target = avg_r * np.outer(std, std)
    np.fill_diagonal(target, std ** 2)
    shrunk = shrink * target + (1 - shrink) * S
    return pd.DataFrame(shrunk, index=returns.columns, columns=returns.columns)


def portfolio_var(weights: dict[str, float], returns: pd.DataFrame,
                  horizon_days: int = 21, alpha: float = 0.95) -> dict:
    """Parametric + historical VaR and CVaR as FRACTIONS of portfolio value."""
    syms = [s for s in weights if s in returns.columns]
    if not syms:
        return {}
    w = np.array([weights[s] for s in syms])
    w = w / w.sum()
    rts = returns[syms]

    cov = shrink_cov(rts).values
    port_daily_vol = float(np.sqrt(w @ cov @ w))
    z = 1.6449 if alpha == 0.95 else 2.3263
    var_param = z * port_daily_vol * np.sqrt(horizon_days)

    port_rets = rts.values @ w
    n = len(port_rets) - horizon_days
    horizon_rets = np.array([np.prod(1 + port_rets[i:i + horizon_days]) - 1
                             for i in range(max(n, 1))])
    var_hist = float(-np.quantile(horizon_rets, 1 - alpha))
    tail = horizon_rets[horizon_rets <= np.quantile(horizon_rets, 1 - alpha)]
    cvar_hist = float(-tail.mean()) if len(tail) else var_hist

    return {"alpha": alpha, "horizon_days": horizon_days,
            "var_parametric": round(var_param, 4),
            "var_historical": round(var_hist, 4),
            "cvar_historical": round(cvar_hist, 4),
            "ann_vol": round(port_daily_vol * np.sqrt(TRADING_DAYS), 4)}


def portfolio_beta(weights: dict[str, float], returns: pd.DataFrame) -> float:
    """Beta vs the equal-weight universe index built from the same panel."""
    syms = [s for s in weights if s in returns.columns]
    w = np.array([weights[s] for s in syms]); w = w / w.sum()
    port = returns[syms].values @ w
    market = returns.mean(axis=1).values
    var_m = np.var(market)
    return float(np.cov(port, market)[0, 1] / var_m) if var_m > 0 else 1.0


def stress_test(weights: dict[str, float], returns: pd.DataFrame) -> dict:
    """Scenario losses (fraction of value): beta-scaled crisis shocks + the
    worst realized month in the panel itself. Correlations→1 assumption: no
    diversification credit is taken in scenarios (module 04)."""
    beta = portfolio_beta(weights, returns)
    out = {name: round(shock * max(beta, 1.0), 4)
           for name, shock in STRESS_SCENARIOS.items()}
    syms = [s for s in weights if s in returns.columns]
    w = np.array([weights[s] for s in syms]); w = w / w.sum()
    port = pd.Series(returns[syms].values @ w, index=returns.index)
    month = (1 + port).rolling(21).apply(np.prod, raw=True) - 1
    if month.notna().any():
        out["worst_realized_month_in_data"] = round(float(month.min()), 4)
    out["portfolio_beta"] = round(beta, 2)
    return out


def correlation_diagnostics(returns: pd.DataFrame) -> dict:
    corr = returns.corr()
    n = len(corr)
    avg = float((corr.values.sum() - n) / (n * (n - 1))) if n > 1 else 0.0
    return {"avg_pairwise_corr": round(avg, 3),
            "diversification_illusion": avg > 0.6,
            "n_assets": n}


def inverse_vol_weights(returns: pd.DataFrame) -> dict[str, float]:
    """Risk-based weighting for the satellite book — needs only vol, not
    forecast returns (module 03: MPT with adult supervision)."""
    vol = returns.std()
    inv = 1 / vol.replace(0, np.nan)
    w = (inv / inv.sum()).fillna(0)
    return {k: round(float(v), 4) for k, v in w.items()}


def portfolio_risk_report(capital: float | None = None) -> dict:
    """Full risk report for current open holdings (value-weighted)."""
    from .portfolio import snapshot

    snap = snapshot()
    pos = snap["positions"]
    if pos.empty:
        return {"note": "no open positions"}
    weights = {r["symbol"]: float(r["value"]) for _, r in pos.iterrows()
               if pd.notna(r["value"])}
    rts = returns_panel(list(weights))
    if rts.empty:
        return {"note": "insufficient price history for holdings"}
    total = sum(weights.values())
    report = {
        "total_value": round(total, 2),
        "var": portfolio_var(weights, rts),
        "stress": stress_test(weights, rts),
        "correlation": correlation_diagnostics(rts[list(
            s for s in weights if s in rts.columns)]),
        "suggested_inverse_vol_weights": inverse_vol_weights(
            rts[[s for s in weights if s in rts.columns]]),
    }
    v = report["var"]
    if v:
        report["plain_english"] = (
            f"A bad month (95%) ≈ -₹{v['var_historical'] * total:,.0f}; "
            f"if it's worse than that, expect ≈ -₹{v['cvar_historical'] * total:,.0f}.")
    return report
