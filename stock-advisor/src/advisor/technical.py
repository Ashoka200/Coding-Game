"""Technical engine: stage analysis, setup detection, technical score (module 05)."""
from __future__ import annotations

import pandas as pd

from . import indicators as ind

MIN_HISTORY = 260  # ~1 trading year needed for a full read


def compute_features(df: pd.DataFrame) -> dict | None:
    """Latest-bar feature snapshot for one symbol. None if insufficient history."""
    if df is None or len(df) < MIN_HISTORY:
        return None
    close, high, low, vol = df["close"], df["high"], df["low"], df["volume"]
    ema20, ema50 = ind.ema(close, 20), ind.ema(close, 50)
    sma200 = ind.sma(close, 200)
    atr14 = ind.atr(df, 14)
    vol50 = vol.rolling(50).mean()
    f = {
        "close": float(close.iloc[-1]),
        "ema20": float(ema20.iloc[-1]),
        "ema50": float(ema50.iloc[-1]),
        "sma200": float(sma200.iloc[-1]),
        "sma200_slope": float(sma200.iloc[-1] / sma200.iloc[-21] - 1),
        "rsi14": float(ind.rsi(close, 14).iloc[-1]),
        "rsi2": float(ind.rsi(close, 2).iloc[-1]),
        "adx": float(ind.adx(df).iloc[-1]),
        "atr14": float(atr14.iloc[-1]),
        "atr_pct": float(atr14.iloc[-1] / close.iloc[-1]),
        "high_52w": float(close.rolling(252).max().iloc[-1]),
        "dist_52w_high": float(close.iloc[-1] / close.rolling(252).max().iloc[-1] - 1),
        "high_60d_prior": float(high.iloc[-61:-1].max()),
        "vol_ratio": float(vol.iloc[-1] / vol50.iloc[-1]) if vol50.iloc[-1] else 0.0,
        "mom_12_1": ind.momentum_12_1(close),
        "ret_63d": float(ind.returns(close, 63).iloc[-1]),
        "median_turnover": float((close * vol).rolling(60).median().iloc[-1]),
        "swing_low_20d": float(low.iloc[-20:].min()),
        # base contraction measured BEFORE the current bar, so a wide breakout
        # bar doesn't mask the tight base that preceded it
        "range_contraction": float(
            ind.true_range(df).iloc[-11:-1].mean() / ind.true_range(df).iloc[-61:-11].mean()
        ),
    }
    return f


def stage(f: dict) -> int:
    """Weinstein stage from a feature snapshot: 2=advance (buyable), 4=decline."""
    above, rising = f["close"] > f["sma200"], f["sma200_slope"] > 0
    if above and rising and f["close"] > f["ema50"]:
        return 2
    if not above and not rising:
        return 4
    return 3 if not rising else 1


def detect_setups(f: dict, fundamental_score: float | None = None) -> list[str]:
    """Which module-05 setups fire on the latest bar."""
    setups = []
    st = stage(f)
    if st == 2:
        if (f["close"] > f["high_60d_prior"] and f["vol_ratio"] >= 1.5
                and f["range_contraction"] < 1.0):
            setups.append("base_breakout")
        near_ema = min(abs(f["close"] / f["ema20"] - 1), abs(f["close"] / f["ema50"] - 1))
        if near_ema <= 0.02 and 35 <= f["rsi14"] <= 60:
            setups.append("pullback_in_trend")
        if f["dist_52w_high"] > -0.005 and f["vol_ratio"] >= 1.3:
            setups.append("new_52w_high")
    if (f["rsi2"] < 10 and f["close"] > f["sma200"] and f["sma200_slope"] > 0
            and (fundamental_score or 0) >= 70):
        setups.append("mean_reversion_quality")
    return setups


def technical_score(f: dict) -> float:
    """0-100: trend structure 40, momentum 30, setup quality context 30."""
    s = 0.0
    st = stage(f)
    s += {2: 40, 1: 20, 3: 10, 4: 0}[st]
    if f["mom_12_1"] is not None:
        s += max(0.0, min(15.0, f["mom_12_1"] * 50))       # 30% 12-1 mom → full 15
    s += max(0.0, min(15.0, (f["dist_52w_high"] + 0.25) * 60))  # near highs → up to 15
    if f["adx"] > 20:
        s += 10
    if 1.0 <= f["vol_ratio"] <= 4.0:
        s += 10
    if f["range_contraction"] < 0.9:
        s += 10
    return round(min(s, 100.0), 1)
