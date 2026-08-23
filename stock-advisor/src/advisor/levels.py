"""Entry/stop/target/size calculator (modules 04 & 05)."""
from __future__ import annotations

from dataclasses import dataclass, asdict


@dataclass
class TradePlan:
    symbol: str
    setup: str
    entry_low: float
    entry_high: float
    stop: float
    target1: float
    target2: float
    risk_per_share: float
    shares: int
    capital_at_risk: float
    position_value: float
    notes: list[str]

    def to_dict(self) -> dict:
        return asdict(self)


def propose_levels(symbol: str, f: dict, setup: str, capital: float,
                   risk_pct: float = 0.0075, max_position_pct: float = 0.08,
                   liquidity_participation: float = 0.25) -> TradePlan | None:
    """Build a trade plan from a feature snapshot for a fired setup.

    Stop = structural (20d swing low) sanity-checked against 2×ATR (nearer wins,
    per module 04: if structure implies too-large risk, size shrinks — never widen).
    Targets at 1.5R / 2.5R. Size = fixed-fractional, capped by max position weight
    and by liquidity (exit ≤ ~1 week at 25% of median daily turnover / 5 days).
    """
    notes: list[str] = []
    close, atr = f["close"], f["atr14"]

    if setup in ("base_breakout", "new_52w_high"):
        entry_low, entry_high = close, close + 0.5 * atr
    elif setup == "pullback_in_trend":
        entry_low, entry_high = min(f["ema20"], close), close
    elif setup == "mean_reversion_quality":
        entry_low, entry_high = close - 0.25 * atr, close
        notes.append("time_stop_5_sessions")
    else:
        return None

    entry_mid = (entry_low + entry_high) / 2
    structural = f["swing_low_20d"]
    atr_stop = entry_mid - 2 * atr
    stop = max(structural, atr_stop)          # nearer (tighter) of the two
    if stop >= entry_low:
        stop = atr_stop                       # structure above entry → ATR stop only
        notes.append("structural_stop_invalid_used_atr")
    risk_per_share = entry_mid - stop
    if risk_per_share <= 0:
        return None

    target1 = entry_mid + 1.5 * risk_per_share
    target2 = entry_mid + 2.5 * risk_per_share

    shares = int((capital * risk_pct) / risk_per_share)
    max_shares_weight = int((capital * max_position_pct) / entry_mid)
    if shares > max_shares_weight:
        shares = max_shares_weight
        notes.append("capped_by_max_position_weight")
    daily_turnover = f.get("median_turnover") or 0
    if daily_turnover > 0:
        max_shares_liq = int(liquidity_participation * 5 * daily_turnover
                             / max(entry_mid, 1e-9) / 5)
        if shares > max_shares_liq:
            shares = max_shares_liq
            notes.append("capped_by_liquidity")
    if shares <= 0:
        return None

    return TradePlan(
        symbol=symbol, setup=setup,
        entry_low=round(entry_low, 2), entry_high=round(entry_high, 2),
        stop=round(stop, 2), target1=round(target1, 2), target2=round(target2, 2),
        risk_per_share=round(risk_per_share, 2), shares=shares,
        capital_at_risk=round(shares * risk_per_share, 2),
        position_value=round(shares * entry_mid, 2), notes=notes,
    )
