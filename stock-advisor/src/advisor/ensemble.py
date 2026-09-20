"""The mathematics of doing better than any single method.

Five investors' checklists, however good, are five opinions about the same few
hundred companies. Adding a sixth great investor barely moves the result,
because their opinions overlap. What moves it is the structure of the
combination, and that structure has known mathematics behind it.

Three results govern everything here, and each one is a constraint before it is
an opportunity.

**Grinold's fundamental law.** The information ratio you can achieve is your
skill multiplied by the square root of how many independent bets you make:

    IR = TC x IC x sqrt(breadth)

Skill (IC) is the correlation between your forecasts and what happened, and for
genuinely good stock selection it is about 0.03 to 0.06 — which sounds like
nothing and is in fact excellent. The square root is the cruel part: to double
your information ratio you need four times the independent decisions.

**The diversification ceiling.** Combining k signals whose average correlation
is rho gives

    S_combined = S_average x sqrt(k / (1 + (k-1) x rho))

and as k grows this does not grow without bound — it converges on
S_average / sqrt(rho). If your signals correlate at 0.3 and each earns a Sharpe
of 0.5, no number of additional signals ever takes you past 0.91. That ceiling
is why "add more strategies" stops working, and why *uncorrelated* matters far
more than *good*.

**Volatility targeting.** Scaling exposure inversely to recent volatility
raises risk-adjusted return for a reason specific to markets: volatility is
strongly autocorrelated while returns are barely autocorrelated at all. So
recent volatility predicts tomorrow's volatility, which means position size can
be adjusted with information that is genuinely there — unlike direction.

Nothing here forecasts a price. These functions size and combine forecasts made
elsewhere, and mostly they say what is not achievable.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass

TRADING_DAYS = 250


# --------------------------------------------------------------------------
# Grinold: skill x breadth
# --------------------------------------------------------------------------
def information_ratio(ic: float, breadth: float,
                      transfer_coefficient: float = 1.0) -> float:
    """IR = TC x IC x sqrt(breadth).

    The transfer coefficient is the part practitioners forget: it measures how
    much of the forecast actually reaches the portfolio after position limits,
    liquidity, lot sizes and the cash you were holding. A long-only book with
    sector caps typically transfers 0.3 to 0.6 of its own signal, which halves
    the information ratio before a single trade is placed.
    """
    if breadth <= 0:
        return 0.0
    return transfer_coefficient * ic * math.sqrt(breadth)


def breadth_required(target_ir: float, ic: float,
                     transfer_coefficient: float = 1.0) -> float | None:
    """How many independent decisions a target demands, at a given skill.

    This is the law inverted, and it is the most useful direction to read it.
    A return target stops being a wish and becomes a statement about how many
    genuinely separate bets must be made each year — which is checkable against
    how many the strategy actually makes.
    """
    denom = transfer_coefficient * ic
    if denom <= 0 or target_ir <= 0:
        return None
    return (target_ir / denom) ** 2


def effective_breadth(n_bets: int, average_correlation: float) -> float:
    """Independent bets, not gross bets.

    Fifty Indian large caps rebalanced monthly is six hundred decisions a year
    on paper. If those names move together at a correlation of 0.4 — which is
    ordinary for one country's equity market — the independent content collapses
    to almost nothing, and that collapse is what the law actually takes.

    Which correlation to pass in is the whole question, and getting it wrong in
    either direction is expensive. For a long-only book it is the raw
    correlation between holdings, which in a single equity market runs 0.3 to
    0.6 and leaves brutally little breadth. For a market-neutral book it is the
    correlation of the RESIDUALS once the market move is hedged out, typically
    0.05 to 0.15 — and that difference, not any difference in stock-picking
    skill, is the main reason hedged books can claim breadth a long-only book
    cannot. Passing raw correlation for a hedged strategy understates it
    enormously; passing residual correlation for a long-only one is a fantasy.
    """
    if n_bets <= 0:
        return 0.0
    rho = max(0.0, min(0.999, average_correlation))
    return n_bets / (1 + (n_bets - 1) * rho)


# --------------------------------------------------------------------------
# combining signals
# --------------------------------------------------------------------------
@dataclass
class Combination:
    n_signals: int
    average_sharpe: float
    average_correlation: float
    combined_sharpe: float
    ceiling_however_many_signals: float
    marginal_gain_from_one_more: float
    reading: str

    def to_dict(self) -> dict:
        return asdict(self)


def combine_sharpe(average_sharpe: float, n_signals: int,
                   average_correlation: float) -> Combination:
    """What k signals of a given quality and correlation actually produce.

    The result worth sitting with is the ceiling. Correlation, not quality,
    is what limits a combination — and the five investor lenses in this system
    correlate heavily with one another, because they all reward high returns on
    capital and low debt. Their combination is therefore worth much less than
    five times one of them, and the honest response is to add methods that are
    *different* rather than methods that are better.
    """
    k = max(1, int(n_signals))
    rho = max(0.0, min(0.999, average_correlation))
    def s_of(n):
        return average_sharpe * math.sqrt(n / (1 + (n - 1) * rho))
    combined = s_of(k)
    ceiling = average_sharpe / math.sqrt(rho) if rho > 0 else float("inf")
    marginal = s_of(k + 1) - combined

    if rho >= 0.8:
        reading = ("these signals are nearly the same signal — combining them adds "
                   "almost nothing and the ceiling is already close")
    elif rho >= 0.4:
        reading = ("substantially overlapping; the combination helps but most of the "
                   "available gain is already taken")
    elif rho > 0:
        reading = "genuinely diversifying — this is where combination earns its keep"
    else:
        reading = ("independent signals, which essentially never happens in one "
                   "equity market — treat this figure as an upper bound")

    return Combination(
        n_signals=k, average_sharpe=average_sharpe, average_correlation=rho,
        combined_sharpe=combined,
        ceiling_however_many_signals=ceiling,
        marginal_gain_from_one_more=marginal,
        reading=reading,
    )


def signals_needed(target_sharpe: float, average_sharpe: float,
                   average_correlation: float) -> dict:
    """How many signals a target Sharpe needs — or that it cannot be reached.

    Returns the unreachable verdict honestly rather than a very large number,
    because a target above the ceiling is not a question of effort.
    """
    rho = max(0.0, min(0.999, average_correlation))
    if average_sharpe <= 0:
        return {"reachable": False, "why": "a signal with no edge combines to no edge"}
    ceiling = average_sharpe / math.sqrt(rho) if rho > 0 else float("inf")
    if target_sharpe >= ceiling:
        return {
            "reachable": False,
            "ceiling": ceiling,
            "why": (f"at an average correlation of {rho:.2f} the combination cannot "
                    f"exceed a Sharpe of {ceiling:.2f}, however many signals are "
                    f"added — the way past it is signals that are different, not more"),
        }
    r = (target_sharpe / average_sharpe) ** 2
    n = r * (1 - rho) / (1 - r * rho)
    return {"reachable": True, "signals_needed": math.ceil(n), "ceiling": ceiling}


# --------------------------------------------------------------------------
# volatility targeting
# --------------------------------------------------------------------------
def realised_vol(returns: list[float], lookback: int = 20) -> list[float | None]:
    """Trailing volatility, annualised, aligned so each value uses only the past.

    The alignment is the whole point: a volatility estimate that includes today
    is a look-ahead, and look-ahead is what makes bad backtests look brilliant.
    """
    out: list[float | None] = []
    for i in range(len(returns)):
        if i < lookback:
            out.append(None)
            continue
        window = returns[i - lookback:i]           # strictly prior days
        m = sum(window) / lookback
        v = sum((x - m) ** 2 for x in window) / (lookback - 1)
        out.append(math.sqrt(v * TRADING_DAYS))
    return out


def volatility_target(returns: list[float], target_annual_vol: float = 0.15,
                      lookback: int = 20, max_leverage: float = 2.0) -> dict:
    """Scale exposure inversely to recent volatility, and measure the result.

    Measured rather than asserted: the function returns both the original and
    the scaled series' statistics so the improvement can be checked rather than
    believed. It usually helps, and when it does not, this says so.

    The leverage cap is not decoration. Scaling up into a quiet market is how
    volatility targeting fails — quiet markets precede violent ones, and an
    uncapped rule takes its largest position immediately before the move it
    cannot survive.
    """
    vols = realised_vol(returns, lookback)
    scaled, weights = [], []
    for r, v in zip(returns, vols):
        if v is None or v <= 0:
            continue
        w = min(max_leverage, target_annual_vol / v)
        weights.append(w)
        scaled.append(w * r)
    if len(scaled) < 60:
        return {"ok": False, "why": "not enough history after the volatility warm-up"}

    def stats(xs):
        n = len(xs)
        m = sum(xs) / n
        v = sum((x - m) ** 2 for x in xs) / (n - 1)
        sd = math.sqrt(v)
        ann_vol = sd * math.sqrt(TRADING_DAYS)
        return {
            "annual_return": m * TRADING_DAYS,
            "annual_vol": ann_vol,
            "sharpe": (m * TRADING_DAYS) / ann_vol if ann_vol else 0.0,
            "worst_day": min(xs),
        }

    base = stats(returns[lookback:][:len(scaled)])
    tgt = stats(scaled)
    gain = tgt["sharpe"] - base["sharpe"]
    return {
        "ok": True,
        "unscaled": base,
        "vol_targeted": tgt,
        "sharpe_gain": gain,
        "average_exposure": sum(weights) / len(weights),
        "max_exposure": max(weights),
        "reading": (
            "volatility targeting improved risk-adjusted return here, which is the "
            "usual result and comes from volatility being predictable when "
            "direction is not"
            if gain > 0.05 else
            "volatility targeting did not help on this series — worth knowing "
            "before assuming it always does"),
    }


# --------------------------------------------------------------------------
# turning a return target into its requirements
# --------------------------------------------------------------------------
def paths_to_target(target_sharpe: float,
                    single_signal_sharpe: float = 0.5) -> list[dict]:
    """What would actually have to change for a target to become reachable.

    A verdict of "unreachable" is only half an answer. The ceiling is set by two
    quantities and both can be moved, so this shows the correlation a set of
    signals would have to achieve at various levels of individual quality. It
    is usually the correlation that is easier to move — by adding a method that
    works differently rather than a method that works better.
    """
    out = []
    for s_i in (single_signal_sharpe, 0.6, 0.8, 1.0):
        # ceiling = s / sqrt(rho)  =>  rho = (s / target)^2
        rho_needed = (s_i / target_sharpe) ** 2
        out.append({
            "single_signal_sharpe": s_i,
            "max_average_correlation": min(0.999, rho_needed),
            "possible": rho_needed > 0.02,
            "note": ("comfortable — ordinary diversification reaches this"
                     if rho_needed >= 0.30 else
                     "demanding — needs genuinely different methods, not more of the same"
                     if rho_needed >= 0.08 else
                     "requires signals almost perfectly independent, which one equity "
                     "market does not offer"),
        })
    return out


def requirements_for(target_annual_return: float, ic: float = 0.05,
                     transfer_coefficient: float = 0.5,
                     average_correlation: float = 0.35,
                     single_signal_sharpe: float = 0.5) -> dict:
    """What a return target demands, expressed in things that can be counted.

    Rather than pronouncing a target possible or impossible, this converts it
    into the two quantities that actually have to be supplied — how many
    independent decisions per year, and how many genuinely different signals —
    so the answer can be checked against what the system really does.
    """
    g = math.log1p(target_annual_return)
    sharpe = math.sqrt(2 * g) if g > 0 else 0.0
    br = breadth_required(sharpe, ic, transfer_coefficient)
    sig = signals_needed(sharpe, single_signal_sharpe, average_correlation)
    return {
        "target_annual_return": target_annual_return,
        "required_sharpe": sharpe,
        "independent_decisions_per_year": br,
        "independent_decisions_per_trading_day": br / TRADING_DAYS if br else None,
        "assumed_skill_ic": ic,
        "assumed_transfer_coefficient": transfer_coefficient,
        "signal_requirement": sig,
        "paths_if_unreachable": (None if sig.get("reachable")
                                 else paths_to_target(sharpe, single_signal_sharpe)),
    }
