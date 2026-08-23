"""Prediction, done the way it can actually work.

There are two kinds of "AI prediction" in markets. One asks a model to name a
price six months out; it produces a confident number with no evidence behind it,
and it is the reason most retail AI tools are worthless. The other asks a
narrower, answerable question:

    "Historically, when this stock looked EXACTLY like it looks today, what
     happened over the next twenty sessions — and how often?"

That is a base rate, computed from stored history, with a sample size and a
confidence interval attached. It is a genuine forecast: falsifiable, bounded,
and improvable. This module does the second kind.

Three disciplines make it honest:

1. NO FORECAST WITHOUT A SAMPLE. Below `MIN_SAMPLES` matching days the module
   returns no probability at all. A 70% hit rate from six observations is noise
   wearing a percentage sign.
2. ALWAYS COMPARED TO THE BASE RATE. Indian equities rise on roughly 53% of
   twenty-day windows. A signal that predicts "up" 55% of the time has almost no
   edge, and saying "55% chance of a gain" without that context is misleading.
3. NO LOOK-AHEAD. Outcomes are measured strictly forward from each historical
   match, and the current bar is never included in its own sample.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field

MIN_SAMPLES = 30           # below this there is no forecast, only an anecdote
DEFAULT_HORIZON = 20       # sessions ≈ one month


@dataclass
class Forecast:
    symbol: str
    horizon_days: int
    state: dict
    samples: int = 0
    prob_up: float | None = None
    ci_low: float | None = None
    ci_high: float | None = None
    median_return: float | None = None
    p25: float | None = None
    p75: float | None = None
    worst: float | None = None
    base_rate_prob_up: float | None = None
    edge_vs_base: float | None = None
    verdict: str | None = None
    caveats: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Confidence interval for a proportion that behaves sensibly at small n.

    The naive interval implies impossible precision from few observations, which
    is exactly the error this module exists to avoid.
    """
    if n == 0:
        return (0.0, 1.0)
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - margin), min(1.0, centre + margin))


def describe_state(close: list[float], high: list[float], low: list[float],
                   i: int) -> dict | None:
    """The signal configuration on bar `i`, using only data up to and including i.

    Deliberately coarse: fine-grained states match almost nothing, which produces
    tiny samples and false precision.
    """
    if i < 210 or i >= len(close):
        return None
    window = close[: i + 1]
    price = window[-1]
    sma200 = sum(window[-200:]) / 200
    sma50 = sum(window[-50:]) / 50
    prior200 = sum(window[-221:-21]) / 200 if len(window) >= 221 else None
    if prior200 is None:
        return None

    # trend stage, as the technical engine defines it
    rising = sma200 > prior200
    if price > sma200 and rising and price > sma50:
        stage = 2
    elif price < sma200 and not rising:
        stage = 4
    else:
        stage = 1 if rising else 3

    # RSI-14 on the window
    up = down = 0.0
    for j in range(i - 13, i + 1):
        d = close[j] - close[j - 1]
        if d > 0:
            up += d
        else:
            down -= d
    up /= 14
    down /= 14
    rsi = 100.0 if down == 0 else 100 - 100 / (1 + up / down)

    # six-month momentum and realised volatility, both bucketed
    mom = price / window[-126] - 1 if len(window) >= 126 else 0.0
    rets = [close[j] / close[j - 1] - 1 for j in range(i - 59, i + 1)]
    vol = (sum(r * r for r in rets) / len(rets)) ** 0.5

    return {
        "stage": stage,
        "rsi_band": "high" if rsi > 70 else "low" if rsi < 30 else "mid",
        "momentum_band": "strong" if mom > 0.20 else "weak" if mom < -0.10 else "flat",
        "vol_band": "high" if vol > 0.025 else "low" if vol < 0.012 else "normal",
    }


def forecast(symbol: str, close: list[float], high: list[float], low: list[float],
             horizon: int = DEFAULT_HORIZON,
             min_samples: int = MIN_SAMPLES) -> Forecast:
    """What happened, historically, from states like today's."""
    n_bars = len(close)
    if n_bars < 260 + horizon:
        f = Forecast(symbol, horizon, {},
                     caveats=[f"Only {n_bars} sessions stored; at least "
                              f"{260 + horizon} are needed before a base rate means "
                              "anything."])
        f.verdict = "no forecast — insufficient history"
        return f

    today = describe_state(close, high, low, n_bars - 1)
    if today is None:
        f = Forecast(symbol, horizon, {}, caveats=["Could not describe today's state."])
        f.verdict = "no forecast"
        return f

    # every historical bar whose state matched, with room for the full horizon
    matches, all_forward = [], []
    for i in range(210, n_bars - horizon - 1):
        fwd = close[i + horizon] / close[i] - 1
        all_forward.append(fwd)
        st = describe_state(close, high, low, i)
        if st == today:
            matches.append(fwd)

    f = Forecast(symbol, horizon, today, samples=len(matches))
    if all_forward:
        ups = sum(1 for r in all_forward if r > 0)
        f.base_rate_prob_up = round(ups / len(all_forward), 3)

    if len(matches) < min_samples:
        f.caveats.append(
            f"Only {len(matches)} historical days matched this configuration — below "
            f"the {min_samples} needed. No probability is offered, because one computed "
            "from this few observations would be noise wearing a percentage sign.")
        f.verdict = "no forecast — too few comparable days"
        return f

    matches.sort()
    wins = sum(1 for r in matches if r > 0)
    f.prob_up = round(wins / len(matches), 3)
    lo, hi = wilson_interval(wins, len(matches))
    f.ci_low, f.ci_high = round(lo, 3), round(hi, 3)
    f.median_return = round(matches[len(matches) // 2], 4)
    f.p25 = round(matches[len(matches) // 4], 4)
    f.p75 = round(matches[(3 * len(matches)) // 4], 4)
    f.worst = round(matches[0], 4)
    if f.base_rate_prob_up is not None:
        f.edge_vs_base = round(f.prob_up - f.base_rate_prob_up, 3)

    # A forecast whose interval straddles the base rate is not a signal.
    straddles = (f.base_rate_prob_up is not None
                 and f.ci_low <= f.base_rate_prob_up <= f.ci_high)
    if straddles:
        f.verdict = "no edge — indistinguishable from the base rate"
        f.caveats.append(
            f"The confidence interval ({f.ci_low:.0%}–{f.ci_high:.0%}) contains the "
            f"unconditional base rate of {f.base_rate_prob_up:.0%}, so this "
            "configuration tells you nothing the calendar does not.")
    elif f.prob_up > (f.base_rate_prob_up or 0.5):
        f.verdict = "favourable versus the base rate"
    else:
        f.verdict = "unfavourable versus the base rate"

    f.caveats.append(
        f"Based on {len(matches)} historical days in the same configuration. The worst "
        f"of them lost {abs(f.worst):.1%} — the median is not the risk.")
    f.caveats.append(
        "A base rate is not a prediction about this instance. It is the frequency of "
        "outcomes in similar past conditions, and conditions change.")
    return f


def blend_with_sentiment(f: Forecast, sentiment_score: float | None,
                         max_shift: float = 0.05) -> Forecast:
    """Let news nudge the probability, bounded — never lead it.

    Sentiment is soft evidence about a hard-to-observe state. It is allowed to
    move the estimate a little; it is not allowed to manufacture a forecast where
    the history did not support one.
    """
    if f.prob_up is None or sentiment_score is None:
        if sentiment_score is not None and f.prob_up is None:
            f.caveats.append("News sentiment was available but is not used: with no "
                             "usable base rate there is nothing for it to adjust.")
        return f
    shift = max(-max_shift, min(max_shift, sentiment_score * max_shift))
    adjusted = max(0.01, min(0.99, f.prob_up + shift))
    f.caveats.append(
        f"News sentiment moved the probability from {f.prob_up:.0%} to {adjusted:.0%}. "
        "The adjustment is capped so that a strong headline cannot override a weak "
        "historical record.")
    f.prob_up = round(adjusted, 3)
    if f.base_rate_prob_up is not None:
        f.edge_vs_base = round(f.prob_up - f.base_rate_prob_up, 3)
    return f
