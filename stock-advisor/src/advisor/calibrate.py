"""Thresholds that move with the market instead of being frozen into the code.

A rule like "return on equity above 15%" is a snapshot of one market in one
decade wearing the costume of a principle. Fifteen percent was unremarkable for
an Indian large cap in 2007 and genuinely good in 2020; a price-earnings ratio
of 40 was absurd when the ten-year bond paid 9% and ordinary when it paid 6%.
Freeze the number and the rule silently stops meaning what it meant.

What should be fixed is the *stance*, not the level. Damani being stricter on
debt than Buffett is doctrine — it is what makes them different investors. That
one asks for 0.3 and the other for 0.5 is a calibration, and calibrations
belong to the market, not to the source code.

So every threshold here is expressed as a position in a live distribution:

    "low debt"  ->  debt in the cleanest 40% of comparable companies today
    "cheap"     ->  a multiple in the lowest quartile of this sector right now
    "high ROE"  ->  top third of the sector, not a number from a book

Three further things are measured rather than assumed, because assuming them is
how a system stops learning:

  * how much the lenses actually overlap, from their own score history;
  * how much forecasting skill the system really has, from the journal of its
    own past calls against what happened;
  * whether a signal that used to work still does.

Everything degrades gracefully. With no market context supplied, the callers
fall back to their previous fixed thresholds, so a thin data day produces the
old behaviour rather than no behaviour.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field

# How strict each stance is, as a position in the live distribution. These are
# the only numbers in this file that are deliberately fixed, because they encode
# what the words mean rather than what the market is doing.
STANCE = {
    "demanding": 0.80,     # top fifth of comparable companies
    "strict": 0.70,
    "moderate": 0.50,      # simply better than the median peer
    "lenient": 0.30,
    "permissive": 0.20,
}

# Metrics where a LOW number is the good one.
LOWER_IS_BETTER = {"debtToEquity", "pe", "pb", "peg", "evEbitda", "annualVol"}


def percentile_of(value: float, population: list[float]) -> float | None:
    """Where a value sits in a population, 0 to 1. None if there is no population."""
    vals = sorted(v for v in population if v is not None and not _nan(v))
    if len(vals) < 8:            # too few peers to speak of a distribution
        return None
    below = sum(1 for v in vals if v < value)
    equal = sum(1 for v in vals if v == value)
    return (below + 0.5 * equal) / len(vals)


def value_at_percentile(population: list[float], p: float) -> float | None:
    vals = sorted(v for v in population if v is not None and not _nan(v))
    if len(vals) < 8:
        return None
    idx = p * (len(vals) - 1)
    lo, hi = int(math.floor(idx)), int(math.ceil(idx))
    if lo == hi:
        return vals[lo]
    return vals[lo] + (vals[hi] - vals[lo]) * (idx - lo)


def _nan(x) -> bool:
    return isinstance(x, float) and x != x


@dataclass
class MarketContext:
    """The live cross-section every adaptive threshold is measured against.

    Sector-relative wherever the sector is known, because a 15% return on equity
    is weak for a consumer brand and strong for a capital-heavy manufacturer.
    Comparing a bank to a software company is how a screen ends up holding one
    sector and calling it stock selection.
    """
    as_of: str
    universe: list[dict] = field(default_factory=list)
    index_annual_vol: float | None = None
    index_drawdown: float | None = None
    regime: str = "unknown"
    risk_free: float | None = None

    _cache: dict = field(default_factory=dict, repr=False)

    # ---------------------------------------------------------------- pools
    def pool(self, metric: str, sector: str | None = None) -> list[float]:
        key = (metric, sector or "")
        if key in self._cache:
            return self._cache[key]
        rows = self.universe
        if sector:
            same = [r for r in rows if (r.get("sector") or "").lower() == sector.lower()]
            # Fall back to the whole market when a sector is too thin to describe
            # a distribution — a five-company "sector percentile" is noise.
            if len(same) >= 8:
                rows = same
        out = [r.get(metric) for r in rows
               if r.get(metric) is not None and not _nan(r.get(metric))]
        self._cache[key] = out
        return out

    def threshold(self, metric: str, stance: str,
                  sector: str | None = None) -> float | None:
        """The live number this stance corresponds to, for this metric today."""
        p = STANCE.get(stance)
        if p is None:
            return None
        pop = self.pool(metric, sector)
        if metric in LOWER_IS_BETTER:
            p = 1 - p            # "demanding" on debt means the LOW end
        return value_at_percentile(pop, p)

    def rank(self, metric: str, value, sector: str | None = None) -> float | None:
        """Where this company sits among its peers, 0 to 1, good end high."""
        if value is None:
            return None
        p = percentile_of(value, self.pool(metric, sector))
        if p is None:
            return None
        return 1 - p if metric in LOWER_IS_BETTER else p

    def meets(self, metric: str, value, stance: str,
              sector: str | None = None) -> bool | None:
        """Does this value clear the stance, measured against peers today?"""
        r = self.rank(metric, value, sector)
        if r is None:
            return None
        return r >= STANCE.get(stance, 0.5)

    def describe(self, metric: str, value, sector: str | None = None) -> str:
        r = self.rank(metric, value, sector)
        if value is None:
            return "not disclosed"
        if r is None:
            return f"{value:.2f} (too few peers to rank it)"
        return f"{value:.2f} — better than {r * 100:.0f}% of peers"

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("_cache", None)
        d["universe_size"] = len(self.universe)
        d.pop("universe", None)
        return d


# --------------------------------------------------------------------------
# risk parameters that follow the market rather than a constant
# --------------------------------------------------------------------------
def risk_parameters(ctx: MarketContext | None,
                    base_stop_atr: float = 2.0,
                    base_vol_target: float = 0.15,
                    base_max_position: float = 0.08) -> dict:
    """Stop width, volatility target and position cap, scaled to conditions.

    A 2×ATR stop is not a constant risk — ATR already moves with volatility, so
    the stop widens on its own. What does not adjust by itself is how much
    capital should be exposed when the whole market is unstable, and that is
    what this scales.

    The asymmetry is deliberate: exposure falls faster than it rises. Volatility
    arrives suddenly and decays slowly, so a rule that de-risks quickly and
    re-risks slowly matches the thing it is reacting to.
    """
    if ctx is None or ctx.index_annual_vol is None:
        return {"stop_atr_multiple": base_stop_atr,
                "vol_target": base_vol_target,
                "max_position": base_max_position,
                "basis": "defaults — no market context supplied"}

    normal_vol = 0.16                       # long-run Indian index volatility
    ratio = ctx.index_annual_vol / normal_vol
    # Wider stops when the market itself is noisier, so ordinary movement does
    # not trigger an exit that was meant for a thesis failing.
    stop = base_stop_atr * min(1.6, max(0.85, ratio ** 0.5))
    # Exposure scales down with volatility and down again in a drawdown.
    scale = min(1.15, 1 / max(0.6, ratio))
    dd = ctx.index_drawdown or 0.0
    if dd <= -0.10:
        scale *= 0.75
    if dd <= -0.20:
        scale *= 0.70
    return {
        "stop_atr_multiple": round(stop, 2),
        "vol_target": round(base_vol_target * min(1.1, max(0.5, 1 / ratio)), 4),
        "max_position": round(base_max_position * scale, 4),
        "basis": (f"index volatility {ctx.index_annual_vol * 100:.0f}% against a "
                  f"long-run {normal_vol * 100:.0f}%, drawdown {dd * 100:.0f}%"),
    }


# --------------------------------------------------------------------------
# measuring what was previously assumed
# --------------------------------------------------------------------------
def measure_correlation(score_history: dict[str, list[float]]) -> dict:
    """Actual overlap between the lenses, from their own scores.

    The ensemble maths needs an average correlation, and until now it took one
    as an argument — which meant the most consequential number in the model was
    a guess. This measures it from how the lenses have actually scored the same
    companies.
    """
    names = [k for k, v in score_history.items() if len(v) >= 12]
    if len(names) < 2:
        return {"ok": False, "why": "need at least two lenses with twelve scores each"}

    def corr(a, b):
        n = min(len(a), len(b))
        a, b = a[:n], b[:n]
        ma, mb = sum(a) / n, sum(b) / n
        va = sum((x - ma) ** 2 for x in a)
        vb = sum((x - mb) ** 2 for x in b)
        if va <= 0 or vb <= 0:
            return None
        cov = sum((x - ma) * (y - mb) for x, y in zip(a, b))
        return cov / math.sqrt(va * vb)

    pairs = {}
    for i, x in enumerate(names):
        for y in names[i + 1:]:
            c = corr(score_history[x], score_history[y])
            if c is not None:
                pairs[f"{x} vs {y}"] = c
    if not pairs:
        return {"ok": False, "why": "scores had no variation to correlate"}
    avg = sum(pairs.values()) / len(pairs)
    return {
        "ok": True, "average_correlation": avg, "pairs": pairs,
        "most_redundant": max(pairs, key=pairs.get),
        "most_diversifying": min(pairs, key=pairs.get),
        "reading": ("the lenses are close to one signal — adding more of the same "
                    "kind will not help" if avg >= 0.7 else
                    "substantial overlap, as expected from methods that all reward "
                    "quality" if avg >= 0.4 else
                    "genuinely diversifying"),
    }


def measure_skill(records: list[dict], horizon_key: str = "forward_return",
                  score_key: str = "score") -> dict:
    """Information coefficient from the journal: forecasts against outcomes.

    The system's own skill, measured on its own past calls rather than assumed
    at a plausible-sounding 0.05. Everything downstream — how much breadth a
    target needs, how much to risk — depends on this number, so it is the one
    that most deserves to be real.
    """
    pairs = [(r.get(score_key), r.get(horizon_key)) for r in records]
    pairs = [(s, f) for s, f in pairs
             if s is not None and f is not None and not _nan(s) and not _nan(f)]
    n = len(pairs)
    if n < 30:
        return {"ok": False, "n": n,
                "why": "fewer than thirty closed calls — any IC from this would be noise"}
    xs = [p[0] for p in pairs]
    ys = [p[1] for p in pairs]
    mx, my = sum(xs) / n, sum(ys) / n
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    if vx <= 0 or vy <= 0:
        return {"ok": False, "n": n, "why": "no variation in scores or outcomes"}
    ic = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / math.sqrt(vx * vy)
    # Standard error of a correlation is roughly 1/sqrt(n).
    se = 1 / math.sqrt(n)
    t = ic / se
    return {
        "ok": True, "ic": ic, "n": n, "standard_error": se, "t_stat": t,
        "significant": abs(t) >= 2,
        "reading": (f"information coefficient {ic:.3f} over {n} calls"
                    + (" — distinguishable from zero" if abs(t) >= 2 else
                       " — not yet distinguishable from luck, so treat downstream "
                       "sizing as provisional")),
    }


def detect_decay(ic_by_period: list[float], window: int = 4) -> dict:
    """Has a signal that used to work stopped working?

    Edges decay as they become known, and the failure is always the same: a
    strategy keeps its position size long after its edge has gone, because
    nobody was measuring. Comparing the recent window against the earlier
    record is the cheapest possible guard against that.
    """
    if len(ic_by_period) < window * 2:
        return {"ok": False,
                "why": f"need at least {window * 2} periods to compare recent with earlier"}
    recent = ic_by_period[-window:]
    earlier = ic_by_period[:-window]
    r_avg = sum(recent) / len(recent)
    e_avg = sum(earlier) / len(earlier)
    drop = e_avg - r_avg
    decayed = e_avg > 0 and (r_avg <= 0 or drop / abs(e_avg) >= 0.5)
    return {
        "ok": True, "recent_ic": r_avg, "earlier_ic": e_avg, "drop": drop,
        "decayed": decayed,
        "action": ("halve the weight on this signal and re-measure next quarter; a "
                   "signal whose edge has halved should not keep its old size"
                   if decayed else
                   "no decay worth acting on — the recent window is in line with "
                   "the record"),
    }


# --------------------------------------------------------------------------
# building the context from whatever data is on hand
# --------------------------------------------------------------------------
def build_context(universe: list[dict], index_closes: list[float] | None = None,
                  as_of: str = "", risk_free: float | None = None) -> MarketContext:
    """Assemble the live picture. Anything absent simply stays None.

    Deliberately tolerant: a context built from a partial universe still gives
    useful percentiles for the metrics it does have, and the thresholds that
    cannot be calibrated fall back rather than failing.
    """
    vol = dd = None
    regime = "unknown"
    if index_closes and len(index_closes) >= 60:
        rets = [math.log(b / a) for a, b in zip(index_closes, index_closes[1:])
                if a > 0 and b > 0]
        if len(rets) >= 40:
            m = sum(rets) / len(rets)
            v = sum((x - m) ** 2 for x in rets) / (len(rets) - 1)
            vol = math.sqrt(v * 250)
        peak = max(index_closes)
        dd = index_closes[-1] / peak - 1 if peak > 0 else None
        if dd is not None and vol is not None:
            if dd <= -0.20:
                regime = "crisis"
            elif dd <= -0.10:
                regime = "stress"
            elif vol > 0.22:
                regime = "unsettled"
            else:
                regime = "normal"
    return MarketContext(as_of=as_of, universe=universe, index_annual_vol=vol,
                         index_drawdown=dd, regime=regime, risk_free=risk_free)
