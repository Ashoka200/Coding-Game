"""Statistics of price movement — what the numbers can and cannot support.

This module exists because most trading mistakes are statistical, not analytical.
A stop is placed where it feels safe rather than where noise cannot reach it. A
position is sized by conviction rather than by variance. A target is set at a
round number rather than at a distance the drift can actually carry price to.
And a return goal is chosen by wishing rather than by asking what Sharpe ratio
it implies.

Everything here answers one of four questions:

  1. How does this stock actually move?      describe_returns
  2. Where can a stop live without being      noise_stop_probability
     hit by randomness alone?
  3. What are the odds this trade reaches     barrier_probability
     its target before its stop?
  4. How much may I risk, and what return     kelly_fraction, risk_of_ruin,
     is even reachable?                       feasible_target

No function here forecasts a price. They describe distributions, and a
distribution is an honest object: it comes with its own error bars.
"""
from __future__ import annotations

import math
import random
from dataclasses import asdict, dataclass

TRADING_DAYS = 250


# --------------------------------------------------------------------------
# basic distribution shape
# --------------------------------------------------------------------------
def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def log_returns(closes: list[float]) -> list[float]:
    """Log returns. Log, not simple: they add across time, which every formula
    below relies on, and they cannot produce a price below zero."""
    out = []
    for a, b in zip(closes, closes[1:]):
        if a and b and a > 0 and b > 0:
            out.append(math.log(b / a))
    return out


@dataclass
class ReturnProfile:
    n: int
    daily_mean: float
    daily_vol: float
    annual_drift: float
    annual_vol: float
    sharpe: float
    skew: float
    excess_kurtosis: float
    tail_days_observed: int
    tail_days_normal_would_predict: float
    max_drawdown: float
    worst_day: float
    best_day: float

    def to_dict(self) -> dict:
        return asdict(self)


def describe_returns(closes: list[float], risk_free: float = 0.065) -> ReturnProfile | None:
    """How this stock actually moves, measured rather than assumed.

    The two numbers worth reading first are `annual_vol` — which sets every
    sensible stop distance and position size below — and the pair of tail
    counts. A normal distribution predicts a 3-sigma day about once in 370;
    Indian equities deliver them several times more often. That gap is why
    position sizing, not stop placement, is what actually limits loss: a gap
    down opens past your stop and fills wherever it likes.
    """
    r = log_returns(closes)
    n = len(r)
    if n < 60:
        return None

    mean = sum(r) / n
    var = sum((x - mean) ** 2 for x in r) / (n - 1)
    sd = math.sqrt(var)
    if sd == 0:
        return None

    m3 = sum((x - mean) ** 3 for x in r) / n
    m4 = sum((x - mean) ** 4 for x in r) / n
    skew = m3 / sd ** 3
    kurt = m4 / sd ** 4 - 3.0

    annual_drift = mean * TRADING_DAYS
    annual_vol = sd * math.sqrt(TRADING_DAYS)

    # How often price moved more than three standard deviations, against how
    # often a normal distribution says it should have.
    tails = sum(1 for x in r if abs(x - mean) > 3 * sd)
    expected_tails = n * 2 * (1 - _norm_cdf(3.0))

    # Max drawdown on the actual path, not on the returns.
    peak, mdd = closes[0], 0.0
    for c in closes:
        if c > peak:
            peak = c
        if peak > 0:
            mdd = min(mdd, c / peak - 1.0)

    return ReturnProfile(
        n=n, daily_mean=mean, daily_vol=sd,
        annual_drift=annual_drift, annual_vol=annual_vol,
        sharpe=(annual_drift - risk_free) / annual_vol if annual_vol else 0.0,
        skew=skew, excess_kurtosis=kurt,
        tail_days_observed=tails,
        tail_days_normal_would_predict=expected_tails,
        max_drawdown=mdd,
        worst_day=min(r), best_day=max(r),
    )


# --------------------------------------------------------------------------
# where a stop can live
# --------------------------------------------------------------------------
def noise_stop_probability(stop_distance_pct: float, daily_vol: float,
                           horizon_days: int = 20) -> float:
    """Odds that ordinary noise alone drags price to a stop this close.

    Uses the reflection principle: for a driftless random walk, the chance the
    *minimum* over N days breaches -d is twice the chance the *endpoint* is
    below -d. Traders reason about the endpoint and are then surprised by how
    often they are stopped out of a position that finishes higher — this is
    exactly the factor of two they left out.

    A stop that noise reaches more than about a third of the time is not a risk
    control, it is a donation schedule.
    """
    if stop_distance_pct <= 0 or daily_vol <= 0 or horizon_days <= 0:
        return 1.0
    sigma = daily_vol * math.sqrt(horizon_days)
    d = abs(math.log(1 - min(stop_distance_pct, 0.99)))
    p = 2 * (1 - _norm_cdf(d / sigma))
    return min(1.0, max(0.0, p))


def minimum_safe_stop(daily_vol: float, horizon_days: int = 20,
                      tolerated_noise_hit: float = 0.25) -> float:
    """The closest a stop may sit while noise still reaches it no more often
    than `tolerated_noise_hit`. Anything tighter is being hit by randomness
    rather than by the thesis failing."""
    if daily_vol <= 0:
        return 0.0
    sigma = daily_vol * math.sqrt(horizon_days)
    # invert the reflection formula for d
    from statistics import NormalDist
    z = NormalDist().inv_cdf(1 - tolerated_noise_hit / 2)
    return 1 - math.exp(-z * sigma)


# --------------------------------------------------------------------------
# target before stop
# --------------------------------------------------------------------------
@dataclass
class BarrierOdds:
    p_target_first: float
    p_stop_first: float
    reward_to_risk: float
    breakeven_win_rate: float
    edge_over_breakeven: float
    expectancy_r: float

    def to_dict(self) -> dict:
        return asdict(self)


def barrier_probability(entry: float, target: float, stop: float,
                        daily_drift: float = 0.0, daily_vol: float = 0.0) -> BarrierOdds | None:
    """Odds of touching the target before the stop, and what that implies.

    This is the gambler's-ruin result applied to a price. With no drift the
    answer is startlingly simple and almost nobody internalises it: the chance
    of reaching the target first is the *stop* distance divided by the total
    distance. A trade with a 2:1 reward-to-risk ratio therefore works only one
    time in three by chance alone — so a 2:1 setup needs better than a 33% hit
    rate to be worth taking, not better than 50%.

    Drift shifts this, but far less than people expect: over a few weeks the
    drift of an Indian equity is a rounding error beside its volatility. If a
    setup only works because of assumed drift, it does not work.
    """
    if entry <= 0 or target <= entry or stop <= 0 or stop >= entry:
        return None

    a = math.log(target / entry)      # distance up, in log space
    b = -math.log(stop / entry)       # distance down, positive
    if a <= 0 or b <= 0:
        return None

    if daily_vol > 0 and abs(daily_drift) > 1e-12:
        k = 2 * daily_drift / (daily_vol ** 2)
        # P(hit +a before -b) for Brownian motion with drift
        try:
            p_up = (1 - math.exp(k * b)) / (math.exp(-k * a) - math.exp(k * b))
        except (OverflowError, ZeroDivisionError):
            p_up = b / (a + b)
    else:
        p_up = b / (a + b)            # driftless: the classic result

    p_up = min(1.0, max(0.0, p_up))
    rr = a / b
    breakeven = 1 / (1 + rr)
    return BarrierOdds(
        p_target_first=p_up,
        p_stop_first=1 - p_up,
        reward_to_risk=rr,
        breakeven_win_rate=breakeven,
        edge_over_breakeven=p_up - breakeven,
        expectancy_r=p_up * rr - (1 - p_up),
    )


# --------------------------------------------------------------------------
# how much to risk
# --------------------------------------------------------------------------
def kelly_fraction(win_rate: float, reward_to_risk: float) -> float:
    """The bet size that maximises long-run growth. Almost never the size to use.

    Kelly assumes you know your edge exactly. You do not — win rate is estimated
    from a small, non-stationary sample — and the penalty for overbetting is
    brutally asymmetric: at twice Kelly the long-run growth rate is zero no
    matter how good the edge, and beyond that it is negative. Betting half of
    Kelly gives up a quarter of the growth and removes most of the ruin risk,
    which is why practitioners use a quarter to a half and this system caps at
    a quarter.
    """
    if reward_to_risk <= 0:
        return 0.0
    f = win_rate - (1 - win_rate) / reward_to_risk
    return max(0.0, f)


def recommended_risk_fraction(win_rate: float, reward_to_risk: float,
                              cap: float = 0.02) -> dict:
    """Quarter-Kelly, then capped. The cap binds far more often than the maths,
    which is the point: an estimate this uncertain should not be trusted to size
    anything on its own."""
    full = kelly_fraction(win_rate, reward_to_risk)
    quarter = full / 4
    return {
        "full_kelly": full,
        "quarter_kelly": quarter,
        "recommended": min(quarter, cap),
        "capped_by_policy": quarter > cap,
        "note": ("no edge — Kelly says do not bet" if full <= 0 else
                 "capped at the house limit" if quarter > cap else
                 "below the house limit, sized by the maths"),
    }


def risk_of_ruin(win_rate: float, reward_to_risk: float, risk_fraction: float,
                 drawdown_limit: float = 0.5, trades: int = 250,
                 sims: int = 4000, seed: int = 7) -> float:
    """Odds of losing `drawdown_limit` of capital inside `trades`, by simulation.

    Closed forms exist only for even-money bets; this is a fixed-fractional
    sequence with uneven payoffs, so it is simulated. The seed is fixed so the
    answer is reproducible — a risk number that changes every time you look at
    it teaches nobody anything.
    """
    if risk_fraction <= 0:
        return 0.0
    rng = random.Random(seed)
    floor = 1 - drawdown_limit
    ruined = 0
    for _ in range(sims):
        equity, peak = 1.0, 1.0
        for _ in range(trades):
            if rng.random() < win_rate:
                equity *= 1 + risk_fraction * reward_to_risk
            else:
                equity *= 1 - risk_fraction
            peak = max(peak, equity)
            if equity <= peak * floor:
                ruined += 1
                break
    return ruined / sims


# --------------------------------------------------------------------------
# what return is even reachable
# --------------------------------------------------------------------------
@dataclass
class Feasibility:
    target_daily: float
    target_annual: float
    required_log_growth: float
    required_sharpe: float
    benchmark_note: str
    days_to_exceed_world_gdp: float | None
    verdict: str
    reachable_daily_at_sharpe_2: float
    reachable_annual_at_sharpe_2: float

    def to_dict(self) -> dict:
        return asdict(self)


def feasible_target(target_daily: float, starting_capital: float = 1_000_000.0,
                    world_gdp_inr: float = 9.0e15) -> Feasibility:
    """What Sharpe ratio a daily return target implies — the honest test.

    The result this rests on: for any strategy, the best long-run compound
    growth rate achievable at optimal leverage is Sharpe² / 2 per year. It is a
    ceiling, not a forecast — no amount of leverage, conviction or effort beats
    it, because leverage past the optimum lowers growth rather than raising it.

    Invert it and any return target names the Sharpe ratio it demands. That
    turns an argument about ambition into an arithmetic question with a
    checkable answer.

    For reference: a good discretionary manager runs a Sharpe around 0.8, an
    excellent systematic fund 1.5 to 2.5, and the best documented record in the
    industry — Renaissance's Medallion — is estimated near 7 before fees, at
    which level it refuses outside money because the capacity is finite.
    """
    g_daily = math.log1p(target_daily)
    annual = math.expm1(g_daily * TRADING_DAYS)
    g_annual = g_daily * TRADING_DAYS
    sharpe = math.sqrt(2 * g_annual) if g_annual > 0 else 0.0

    days = None
    if target_daily > 0 and starting_capital > 0 and world_gdp_inr > starting_capital:
        days = math.log(world_gdp_inr / starting_capital) / g_daily

    if sharpe <= 1.0:
        verdict = "reachable — this is what a disciplined, ordinary process produces"
    elif sharpe <= 2.5:
        verdict = "demanding but real — the range excellent systematic funds occupy"
    elif sharpe <= 7.0:
        verdict = ("beyond any publicly documented fund except Medallion, which "
                   "closed to outside money precisely because it could not scale")
    else:
        verdict = ("not reachable — this exceeds the best record in the history of "
                   "the industry by a wide margin, and no leverage closes the gap")

    if sharpe <= 7:
        bench = f"a Sharpe of {sharpe:.2f}; excellent funds run 1.5 to 2.5"
    else:
        bench = (f"a Sharpe of {sharpe:.1f}, against roughly 7 for the best fund "
                 f"ever documented and 2 for an excellent one")

    # What an excellent-but-real strategy actually delivers, for comparison.
    g2 = (2.0 ** 2) / 2
    return Feasibility(
        target_daily=target_daily,
        target_annual=annual,
        required_log_growth=g_annual,
        required_sharpe=sharpe,
        benchmark_note=bench,
        days_to_exceed_world_gdp=days,
        verdict=verdict,
        reachable_daily_at_sharpe_2=math.expm1(g2 / TRADING_DAYS),
        reachable_annual_at_sharpe_2=math.expm1(g2),
    )


def grade_trade(entry: float, target: float, stop: float,
                profile: ReturnProfile, horizon_days: int = 20,
                assumed_win_rate: float | None = None) -> dict:
    """Put the whole statistical picture on one trade.

    Combines the three questions that decide whether a plan is sound: can noise
    reach this stop, do the barrier odds beat the breakeven the ratio demands,
    and what fraction of capital does that justify risking.
    """
    stop_pct = (entry - stop) / entry if entry > 0 else 0.0
    noise = noise_stop_probability(stop_pct, profile.daily_vol, horizon_days)
    odds = barrier_probability(entry, target, stop,
                               profile.daily_mean, profile.daily_vol)
    if odds is None:
        return {"ok": False, "why": "target and stop must straddle the entry price"}

    win = assumed_win_rate if assumed_win_rate is not None else odds.p_target_first
    sizing = recommended_risk_fraction(win, odds.reward_to_risk)
    ruin = risk_of_ruin(win, odds.reward_to_risk, sizing["recommended"])

    flags = []
    if noise > 0.35:
        flags.append(
            f"the stop is close enough that ordinary noise reaches it "
            f"{noise * 100:.0f}% of the time — widen it and size smaller instead")
    if odds.edge_over_breakeven <= 0:
        flags.append(
            f"a {odds.reward_to_risk:.1f}:1 ratio needs a "
            f"{odds.breakeven_win_rate * 100:.0f}% hit rate just to break even")
    if profile.excess_kurtosis > 3:
        flags.append(
            "returns are fat-tailed, so the stop may be gapped through — the "
            "position size, not the stop, is what actually caps the loss")
    if profile.annual_vol > 0.45:
        flags.append(
            f"annualised volatility is {profile.annual_vol * 100:.0f}%, so every "
            "level here is wider than it looks")

    return {
        "ok": True,
        "stop_distance_pct": stop_pct,
        "noise_stop_probability": noise,
        "minimum_safe_stop_pct": minimum_safe_stop(profile.daily_vol, horizon_days),
        "odds": odds.to_dict(),
        "sizing": sizing,
        "risk_of_ruin_1y": ruin,
        "flags": flags,
        "verdict": ("sound" if not flags else
                    "workable with the caveats below" if len(flags) == 1 else
                    "the statistics do not support this plan as drawn"),
    }
