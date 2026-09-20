"""Cross-sectional portfolio backtest — the evidence layer for a ranker.

The existing backtester tests one setup on one stock. This one tests what the
system actually does: rank a universe, hold the top names, rebalance, and pay
for the turnover. Those are different questions and the second is the one that
decides whether a return target is reachable.

Everything here is built around one conviction: **a backtest's job is to fail.**
Most published backtests are broken in one of four ways, and each has a guard:

  * *Look-ahead.* A score that contains the future produces a beautiful curve
    and no live return. The harness computes forward returns itself from prices,
    so a caller's score is never handed data beyond its own date — and
    `shuffle_test` catches the remaining case by permuting scores across symbols:
    if the curve survives that, the edge was never in the scores.

  * *Costs waved away.* Indian delivery equity pays securities transaction tax
    on both legs, and at monthly rebalancing that alone is a serious drag. The
    cost model is explicit and itemised so it can be argued with.

  * *Survivorship.* A universe of today's constituents backtested over ten years
    has quietly excluded everything that failed. The harness takes whatever
    universe it is given per date and never fills a gap.

  * *Multiple testing.* The tenth variation tried is not the same evidence as
    the first. Results carry the number of variants so the deflated Sharpe can
    price the search.

No market data was available when this was written — the store was empty and the
sandbox could not reach an exchange — so it is verified against synthetic panels
with known properties instead: a panel with a planted edge, which the harness
must recover, and a panel with none, which it must report as none.
"""
from __future__ import annotations

import math
import random
from dataclasses import asdict, dataclass, field

TRADING_DAYS = 250


# --------------------------------------------------------------------------
# what a round trip actually costs in Indian cash equity
# --------------------------------------------------------------------------
@dataclass
class CostModel:
    """Delivery-segment costs, itemised so each can be checked or changed.

    Securities transaction tax is the one that hurts: it is charged on both the
    buy and the sell, so it is paid in full on every rebalance regardless of
    whether the trade worked.
    """
    stt_buy: float = 0.001            # 0.1% on delivery buy
    stt_sell: float = 0.001           # 0.1% on delivery sell
    exchange_txn: float = 0.0000297   # NSE transaction charge
    sebi_charges: float = 0.000001
    stamp_duty_buy: float = 0.00015   # buy side only
    brokerage: float = 0.0            # zero-brokerage delivery
    gst_rate: float = 0.18            # on brokerage plus exchange charges
    slippage: float = 0.0010          # conservative for liquid large caps

    def one_way(self, is_buy: bool) -> float:
        stt = self.stt_buy if is_buy else self.stt_sell
        taxable = self.brokerage + self.exchange_txn
        gst = taxable * self.gst_rate
        stamp = self.stamp_duty_buy if is_buy else 0.0
        return (stt + self.exchange_txn + self.sebi_charges + stamp
                + self.brokerage + gst + self.slippage)

    def round_trip(self) -> float:
        return self.one_way(True) + self.one_way(False)

    def itemised(self) -> dict:
        return {
            "buy_side": self.one_way(True),
            "sell_side": self.one_way(False),
            "round_trip": self.round_trip(),
            "of_which_stt": self.stt_buy + self.stt_sell,
            "of_which_slippage": self.slippage * 2,
        }


@dataclass
class BacktestConfig:
    top_n: int = 20
    rebalance_every: int = 21          # trading days; 21 is roughly monthly
    max_weight: float = 0.10
    weighting: str = "equal"           # "equal" or "inverse_vol"
    costs: CostModel = field(default_factory=CostModel)


@dataclass
class BacktestResult:
    periods: int
    gross_return_annual: float
    net_return_annual: float
    annual_vol: float
    sharpe: float
    max_drawdown: float
    turnover_per_rebalance: float
    cost_drag_annual: float
    hit_rate: float
    period_returns: list[float] = field(default_factory=list)
    equity: list[float] = field(default_factory=list)
    names_held: float = 0.0

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("period_returns", None)
        d.pop("equity", None)
        return d


# --------------------------------------------------------------------------
def _weights(symbols: list[str], prices: dict, t: int,
             cfg: BacktestConfig) -> dict[str, float]:
    """Portfolio weights at a rebalance, using only history up to t."""
    if not symbols:
        return {}
    if cfg.weighting == "inverse_vol":
        inv = {}
        for s in symbols:
            series = prices[s][max(0, t - 60):t + 1]
            rets = [b / a - 1 for a, b in zip(series, series[1:]) if a]
            if len(rets) < 20:
                inv[s] = 1.0
                continue
            m = sum(rets) / len(rets)
            v = sum((x - m) ** 2 for x in rets) / (len(rets) - 1)
            sd = math.sqrt(v)
            inv[s] = 1 / sd if sd > 0 else 1.0
        total = sum(inv.values()) or 1.0
        raw = {s: inv[s] / total for s in symbols}
    else:
        raw = {s: 1 / len(symbols) for s in symbols}

    # Apply the cap, then renormalise so the book is still fully invested.
    capped = {s: min(w, cfg.max_weight) for s, w in raw.items()}
    total = sum(capped.values())
    return {s: w / total for s, w in capped.items()} if total > 0 else {}


def backtest(scores_by_t: dict[int, dict[str, float]],
             prices: dict[str, list[float]],
             cfg: BacktestConfig | None = None) -> BacktestResult:
    """Run the ranker over the panel and pay for what it does.

    `scores_by_t` maps a rebalance index to the scores known AT that index.
    Forward returns are computed here, from the prices, between one rebalance
    and the next — the caller never supplies them and therefore cannot
    accidentally supply the future.
    """
    cfg = cfg or BacktestConfig()
    ts = sorted(scores_by_t)
    if len(ts) < 2:
        return BacktestResult(0, 0, 0, 0, 0, 0, 0, 0, 0)

    equity = [1.0]
    period_returns: list[float] = []
    turnovers: list[float] = []
    held: dict[str, float] = {}
    names: list[int] = []

    for i, t in enumerate(ts[:-1]):
        nxt = ts[i + 1]
        scores = scores_by_t[t]
        # Only names that have a price at both ends can be held. A name that
        # disappears is simply absent — never back-filled, never assumed flat.
        eligible = [s for s, v in scores.items()
                    if v is not None and s in prices
                    and len(prices[s]) > nxt
                    and prices[s][t] and prices[s][nxt]]
        picks = sorted(eligible, key=lambda s: scores[s], reverse=True)[:cfg.top_n]
        w = _weights(picks, prices, t, cfg)
        names.append(len(picks))

        gross = sum(wt * (prices[s][nxt] / prices[s][t] - 1) for s, wt in w.items())

        # Turnover is the one-way change in weights; both legs are then charged.
        allsyms = set(w) | set(held)
        turnover = sum(abs(w.get(s, 0.0) - held.get(s, 0.0)) for s in allsyms) / 2
        turnovers.append(turnover)
        cost = turnover * cfg.costs.round_trip()

        net = gross - cost
        period_returns.append(net)
        equity.append(equity[-1] * (1 + net))
        held = w

    n = len(period_returns)
    if n == 0:
        return BacktestResult(0, 0, 0, 0, 0, 0, 0, 0, 0)

    per_year = TRADING_DAYS / cfg.rebalance_every
    mean = sum(period_returns) / n
    var = (sum((x - mean) ** 2 for x in period_returns) / (n - 1)) if n > 1 else 0.0
    sd = math.sqrt(var)
    ann_vol = sd * math.sqrt(per_year)
    ann_net = (equity[-1] ** (per_year / n) - 1) if equity[-1] > 0 else -1.0
    avg_turn = sum(turnovers) / len(turnovers)
    cost_drag = avg_turn * cfg.costs.round_trip() * per_year

    peak, mdd = equity[0], 0.0
    for e in equity:
        peak = max(peak, e)
        mdd = min(mdd, e / peak - 1)

    return BacktestResult(
        periods=n,
        gross_return_annual=ann_net + cost_drag,
        net_return_annual=ann_net,
        annual_vol=ann_vol,
        sharpe=(ann_net / ann_vol) if ann_vol > 0 else 0.0,
        max_drawdown=mdd,
        turnover_per_rebalance=avg_turn,
        cost_drag_annual=cost_drag,
        hit_rate=sum(1 for r in period_returns if r > 0) / n,
        period_returns=period_returns,
        equity=equity,
        names_held=sum(names) / len(names) if names else 0.0,
    )


# --------------------------------------------------------------------------
# the guards
# --------------------------------------------------------------------------
def shuffle_test(scores_by_t: dict[int, dict[str, float]],
                 prices: dict[str, list[float]],
                 cfg: BacktestConfig | None = None,
                 runs: int = 24, seed: int = 17, alpha: float = 0.05) -> dict:
    """Permute the scores across symbols and see whether the edge survives.

    The single most useful check there is. Everything else about the backtest
    stays identical — same universe, same dates, same costs, same turnover — and
    only the mapping from score to symbol is destroyed. A strategy whose real
    return sits inside the shuffled distribution has no demonstrated skill, and
    one that scores far above it has at least shown the signal is doing the work
    rather than some artefact of the construction.
    """
    real = backtest(scores_by_t, prices, cfg)
    rng = random.Random(seed)
    shuffled = []
    for _ in range(runs):
        permuted = {}
        for t, scores in scores_by_t.items():
            syms = list(scores)
            vals = [scores[s] for s in syms]
            rng.shuffle(vals)
            permuted[t] = dict(zip(syms, vals))
        shuffled.append(backtest(permuted, prices, cfg).sharpe)

    shuffled.sort()
    better = sum(1 for s in shuffled if s >= real.sharpe)
    p = (better + 1) / (runs + 1)
    median = shuffled[len(shuffled) // 2]

    # A permutation test cannot report a p-value below 1/(runs+1), so asking for
    # 0.05 with twenty runs is asking for something arithmetically unreachable —
    # a strong signal would be reported as a failure. This caught itself in
    # testing and is now stated rather than silently producing false negatives.
    min_p = 1 / (runs + 1)
    enough = min_p <= alpha
    passes = bool(enough and p <= alpha)

    return {
        "real_sharpe": real.sharpe,
        "shuffled_median": median,
        "shuffled_best": shuffled[-1],
        # The number that actually means skill. Raw Sharpe in a long-only
        # backtest is mostly market exposure: a random portfolio in a rising
        # market posts a fine Sharpe having demonstrated nothing.
        "skill_above_chance": real.sharpe - median,
        "p_value": p,
        "min_achievable_p": min_p,
        "runs_sufficient": enough,
        "passes": passes,
        "reading": (
            f"only {runs} permutations, so no p-value below {min_p:.3f} is "
            f"reachable — run at least {math.ceil(1 / alpha) - 1} to test at "
            f"{alpha:.0%}" if not enough else
            "the ranking is doing the work — shuffling it destroys the result"
            if passes else
            "shuffling the scores produces a comparable result, so the edge is "
            "not coming from the ranking. Suspect look-ahead, a construction "
            "artefact, or simply no signal."),
    }


def walk_forward(scores_by_t: dict[int, dict[str, float]],
                 prices: dict[str, list[float]],
                 folds: int = 4,
                 cfg: BacktestConfig | None = None) -> dict:
    """Run the strategy in sequential slices and judge the consistency.

    The headline number over a full sample can be carried entirely by one
    regime. Folds expose that: a strategy that worked in two of four periods and
    lost in the others has not been shown to work, whatever the total says.
    """
    ts = sorted(scores_by_t)
    if len(ts) < folds * 4:
        return {"ok": False, "why": f"need at least {folds * 4} rebalances for {folds} folds"}

    size = len(ts) // folds
    results = []
    for i in range(folds):
        chunk = ts[i * size:(i + 1) * size] if i < folds - 1 else ts[i * size:]
        sub = {t: scores_by_t[t] for t in chunk}
        r = backtest(sub, prices, cfg)
        results.append({"fold": i + 1, "periods": r.periods,
                        "net_annual": r.net_return_annual, "sharpe": r.sharpe,
                        "max_drawdown": r.max_drawdown})

    positive = sum(1 for r in results if r["sharpe"] > 0)
    sharpes = [r["sharpe"] for r in results]
    spread = max(sharpes) - min(sharpes)
    return {
        "ok": True, "folds": results,
        "positive_folds": positive,
        "consistency": positive / folds,
        "sharpe_spread": spread,
        "reading": (
            "consistent across every slice of history" if positive == folds else
            f"worked in {positive} of {folds} periods — the headline number is "
            f"carried by some regimes and not others" if positive >= folds / 2 else
            "failed in most periods; the full-sample result is not evidence"),
    }


def assess(result: BacktestResult, variants_tried: int = 1,
           runs_of_shuffle: dict | None = None) -> dict:
    """The verdict, after the search has been paid for.

    A backtest is not evidence until three things hold: the shuffle test passes,
    the result survives the multiple-testing correction, and the bootstrap
    interval on period returns excludes zero. Any one of them failing is enough
    to withhold judgement.
    """
    from .stats import bootstrap_ci, deflated_sharpe

    dsr = deflated_sharpe(result.sharpe, result.periods, trials=variants_tried,
                          periods_per_year=1)
    ci = bootstrap_ci(result.period_returns) if result.period_returns else None

    checks = {
        "shuffle": (runs_of_shuffle or {}).get("passes"),
        "deflated_sharpe": dsr.get("passes"),
        "interval_excludes_zero": (None if ci is None else not ci["includes_zero"]),
    }
    decided = [v for v in checks.values() if v is not None]
    passed = all(v for v in decided) and len(decided) >= 2

    # Readable reasons. The previous version concatenated the failing keys and
    # relied on `or` for a fallback — but `+` binds tighter than `or`, so the
    # left side was always a non-empty string and the fallback could never fire.
    REASONS = {
        "shuffle": "shuffling the scores produced a comparable result",
        "deflated_sharpe": "it does not survive the number of variants tried",
        "interval_excludes_zero": "the confidence interval includes zero",
    }
    failed = [REASONS[k] for k, v in checks.items() if v is False]
    if passed:
        verdict = "this result is evidence"
    elif failed:
        verdict = "not evidence — " + "; ".join(failed)
    else:
        verdict = ("not evidence yet — too few of the three checks could be run "
                   "to reach a verdict")

    return {
        "checks": checks,
        "checks_run": len(decided),
        "deflated": dsr,
        "interval": ci,
        "verdict": verdict,
    }


# --------------------------------------------------------------------------
# combining signals — the question the ceiling mathematics actually needs
# --------------------------------------------------------------------------
def zscore_row(row: dict[str, float]) -> dict[str, float]:
    """Standardise one date's scores across the cross-section.

    Raw signals are not comparable: a momentum score runs in units of return, a
    volatility score in units of standard deviation. Averaging them directly
    would silently weight by whichever happens to have the larger spread. The
    z-score is what makes "average of the signals" mean what it says.
    """
    vals = [v for v in row.values() if v is not None]
    n = len(vals)
    if n < 8:
        return {}
    m = sum(vals) / n
    sd = math.sqrt(sum((v - m) ** 2 for v in vals) / (n - 1)) if n > 1 else 0.0
    if sd <= 0:
        return {}
    # Winsorise at three standard deviations: one broken data point should not
    # decide the whole portfolio.
    return {k: max(-3.0, min(3.0, (v - m) / sd))
            for k, v in row.items() if v is not None}


def combine_signals(*score_sets: dict[int, dict[str, float]]) -> dict[int, dict[str, float]]:
    """Average several signals into one, per date, after standardising each.

    Only dates and symbols present in every signal are kept. Filling a gap with
    a neutral zero would let a signal vote on names it could not score, which is
    how a combination quietly becomes whichever signal has the best coverage.
    """
    if not score_sets:
        return {}
    common_t = set(score_sets[0])
    for s in score_sets[1:]:
        common_t &= set(s)

    out: dict[int, dict[str, float]] = {}
    for t in sorted(common_t):
        rows = [zscore_row(s[t]) for s in score_sets]
        if any(not r for r in rows):
            continue
        symbols = set(rows[0])
        for r in rows[1:]:
            symbols &= set(r)
        if len(symbols) < 10:
            continue
        out[t] = {sym: sum(r[sym] for r in rows) / len(rows) for sym in symbols}
    return out


def correlation(a: list[float], b: list[float]) -> float | None:
    """Pearson correlation of two return streams, aligned from the start."""
    n = min(len(a), len(b))
    if n < 8:
        return None
    a, b = a[:n], b[:n]
    ma, mb = sum(a) / n, sum(b) / n
    va = sum((x - ma) ** 2 for x in a)
    vb = sum((y - mb) ** 2 for y in b)
    if va <= 0 or vb <= 0:
        return None
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / math.sqrt(va * vb)


def combination_report(named_results: dict[str, BacktestResult],
                       combined: BacktestResult | None = None) -> dict:
    """What the signals are worth together, measured rather than assumed.

    This replaces the guess that has been driving every reachability verdict in
    this system. The correlation between the signals' own return streams is the
    number that sets the ceiling, and until now it was 0.35 because 0.35 sounded
    reasonable.
    """
    names = [n for n, r in named_results.items() if r.periods >= 8]
    if len(names) < 2:
        return {"ok": False, "why": "need at least two signals with eight periods each"}

    pairs = {}
    for i, x in enumerate(names):
        for y in names[i + 1:]:
            c = correlation(named_results[x].period_returns,
                            named_results[y].period_returns)
            if c is not None:
                pairs[f"{x} + {y}"] = c
    if not pairs:
        return {"ok": False, "why": "return streams had no variation to correlate"}

    avg_corr = sum(pairs.values()) / len(pairs)
    sharpes = [named_results[n].sharpe for n in names]
    avg_sharpe = sum(sharpes) / len(sharpes)
    best_single = max(sharpes)

    from .ensemble import combine_sharpe
    predicted = combine_sharpe(avg_sharpe, len(names), max(0.0, avg_corr))

    report = {
        "ok": True,
        "signals": names,
        "pairwise_correlation": pairs,
        "average_correlation": avg_corr,
        "most_redundant": max(pairs, key=pairs.get),
        "most_diversifying": min(pairs, key=pairs.get),
        "average_single_sharpe": avg_sharpe,
        "best_single_sharpe": best_single,
        "predicted_combined_sharpe": predicted.combined_sharpe,
        "ceiling_however_many_signals": predicted.ceiling_however_many_signals,
        "reading": predicted.reading,
    }
    if combined is not None and combined.periods >= 8:
        report["actual_combined_sharpe"] = combined.sharpe
        report["actual_combined_net_annual"] = combined.net_return_annual
        report["beat_best_single"] = combined.sharpe > best_single
        # Theory predicts the combination from correlation alone. A large gap
        # either way means the assumption of equal, stable pairwise correlation
        # does not hold — worth knowing before trusting the ceiling.
        report["theory_vs_actual"] = combined.sharpe - predicted.combined_sharpe
    return report
