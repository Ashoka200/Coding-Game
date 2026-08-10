"""F&O analytics (module 07): Black-Scholes pricing/Greeks, implied vol, and the
defined-risk strategy selector. Doctrine enforced in code: undefined-risk
structures are not representable outputs."""
from __future__ import annotations

import math
from dataclasses import dataclass


def _norm_cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def _norm_pdf(x: float) -> float:
    return math.exp(-x * x / 2) / math.sqrt(2 * math.pi)


@dataclass
class Greeks:
    price: float
    delta: float
    gamma: float
    theta_per_day: float
    vega_per_pct: float


def black_scholes(spot: float, strike: float, t_years: float, iv: float,
                  rate: float = 0.065, kind: str = "call") -> Greeks:
    if t_years <= 0 or iv <= 0:
        intrinsic = max(0.0, (spot - strike) if kind == "call" else (strike - spot))
        return Greeks(intrinsic, 1.0 if intrinsic and kind == "call" else 0.0, 0, 0, 0)
    d1 = (math.log(spot / strike) + (rate + iv * iv / 2) * t_years) / (iv * math.sqrt(t_years))
    d2 = d1 - iv * math.sqrt(t_years)
    disc = math.exp(-rate * t_years)
    if kind == "call":
        price = spot * _norm_cdf(d1) - strike * disc * _norm_cdf(d2)
        delta = _norm_cdf(d1)
        theta = (-spot * _norm_pdf(d1) * iv / (2 * math.sqrt(t_years))
                 - rate * strike * disc * _norm_cdf(d2))
    else:
        price = strike * disc * _norm_cdf(-d2) - spot * _norm_cdf(-d1)
        delta = _norm_cdf(d1) - 1
        theta = (-spot * _norm_pdf(d1) * iv / (2 * math.sqrt(t_years))
                 + rate * strike * disc * _norm_cdf(-d2))
    gamma = _norm_pdf(d1) / (spot * iv * math.sqrt(t_years))
    vega = spot * _norm_pdf(d1) * math.sqrt(t_years) / 100
    return Greeks(price, delta, gamma, theta / 365, vega)


def implied_vol(target_price: float, spot: float, strike: float, t_years: float,
                rate: float = 0.065, kind: str = "call") -> float | None:
    lo, hi = 0.01, 3.0
    for _ in range(80):
        mid = (lo + hi) / 2
        p = black_scholes(spot, strike, t_years, mid, rate, kind).price
        if abs(p - target_price) < 1e-4:
            return round(mid, 4)
        if p < target_price:
            lo = mid
        else:
            hi = mid
    return round((lo + hi) / 2, 4)


def iv_percentile(current_iv: float, iv_history: list[float]) -> float:
    """Fraction of the last year's IV readings below current (IVP, module 07)."""
    if not iv_history:
        return 0.5
    return round(sum(1 for v in iv_history if v < current_iv) / len(iv_history), 3)


BANNED = ["naked_short_call", "naked_short_put", "short_straddle", "short_strangle"]


def suggest_strategy(view: str, ivp: float, is_index: bool = True,
                     holding_underlying: bool = False) -> dict:
    """Module-07 strategy menu. view ∈ bullish|bearish|rangebound|hedge|event."""
    high_iv = ivp >= 0.6
    if view == "event":
        return {"strategy": "stay_out",
                "why": "IV crush around events eats directional wins (module 07)"}
    if view == "hedge":
        return {"strategy": "protective_put_or_collar", "legs": "buy OTM index put; "
                "optionally finance with covered OTM call", "defined_risk": True}
    if view == "rangebound":
        if not is_index:
            return {"strategy": "no_trade", "why": "condors on single stocks: gap risk"}
        return ({"strategy": "iron_condor", "defined_risk": True,
                 "exit": "at 50-60% max profit or 2x credit loss"}
                if high_iv else
                {"strategy": "no_trade", "why": "selling cheap IV has no edge"})
    if view == "bullish":
        strat = "bull_put_spread" if high_iv else "bull_call_spread"
    elif view == "bearish":
        strat = "bear_call_spread" if high_iv else "bear_put_spread"
    else:
        raise ValueError(f"unknown view {view}")
    out = {"strategy": strat, "defined_risk": True,
           "exit": "credit: 50-60% max profit; debit: thesis level or 50% loss"}
    if holding_underlying and view == "bullish":
        out["alternative"] = "covered_call for income if moderately bullish"
    return out


def spread_max_loss(width: float, net_premium: float, is_credit: bool, lot: int) -> float:
    """Max loss in ₹ for a vertical spread — this is the 'entry−stop' quantity that
    module 04 sizing consumes."""
    per_share = (width - net_premium) if is_credit else net_premium
    return round(max(0.0, per_share) * lot, 2)
