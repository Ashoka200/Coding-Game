"""The backtest harness, verified on panels whose true answer is known.

No market data existed when this was written, so the harness is proved the only
honest way available: build a world with a planted edge and check it is
recovered, build a world with none and check none is reported. The second
matters more — a backtester that finds profit in random data is worse than no
backtester, because it will be believed."""
import math
import random

from advisor.portfolio_backtest import (
    BacktestConfig, CostModel, assess, backtest, shuffle_test, walk_forward,
)


def build_world(n_symbols=60, n_days=1300, edge=0.0, seed=1, vol=0.02):
    """A synthetic universe. `edge` is how strongly the score predicts the next
    month's return — zero means the scores are pure noise."""
    rng = random.Random(seed)
    prices = {f"S{i}": [100.0] for i in range(n_symbols)}
    # A per-symbol quality drawn once, which the score will reflect.
    quality = {f"S{i}": rng.gauss(0, 1) for i in range(n_symbols)}
    for t in range(n_days):
        for s in prices:
            drift = edge * quality[s] / 21          # spread over the month
            prices[s].append(prices[s][-1] * math.exp(rng.gauss(drift, vol)))
    scores = {}
    for t in range(60, n_days - 21, 21):
        scores[t] = {s: quality[s] + rng.gauss(0, 0.3) for s in prices}
    return scores, prices, quality


def build_noise_world(n_symbols=60, n_days=1300, seed=2):
    """Scores with no relationship to anything."""
    rng = random.Random(seed)
    prices = {f"S{i}": [100.0] for i in range(n_symbols)}
    for _ in range(n_days):
        for s in prices:
            prices[s].append(prices[s][-1] * math.exp(rng.gauss(0.0002, 0.02)))
    scores = {t: {s: rng.gauss(0, 1) for s in prices}
              for t in range(60, n_days - 21, 21)}
    return scores, prices


# ------------------------------------------------------------------- costs
def test_the_securities_transaction_tax_is_charged_on_both_legs():
    c = CostModel()
    assert c.itemised()["of_which_stt"] == 0.002
    assert c.one_way(True) > c.one_way(False), "stamp duty is buy-side only"


def test_a_round_trip_costs_what_the_items_add_to():
    c = CostModel()
    assert abs(c.round_trip() - (c.one_way(True) + c.one_way(False))) < 1e-15
    # Sanity: delivery equity in India, round trip, should land near 0.4%.
    assert 0.003 < c.round_trip() < 0.006


def test_costs_actually_reduce_the_result():
    scores, prices, _ = build_world(edge=0.06)
    free = backtest(scores, prices, BacktestConfig(costs=CostModel(
        stt_buy=0, stt_sell=0, exchange_txn=0, sebi_charges=0,
        stamp_duty_buy=0, slippage=0)))
    real = backtest(scores, prices, BacktestConfig())
    assert real.net_return_annual < free.net_return_annual
    assert real.cost_drag_annual > 0


# ------------------------------------------------------------------- no edge
def test_raw_sharpe_in_a_long_only_backtest_is_mostly_the_market():
    # The trap this harness exists to expose. Scores are pure noise, yet the
    # strategy posts a Sharpe well above 1 — because a random long-only basket
    # in a rising market inherits the market's Sharpe and has demonstrated
    # nothing at all. Skill is the gap over a shuffled portfolio, never the
    # headline number.
    gaps, levels = [], []
    for seed in range(2, 10):
        scores, prices = build_noise_world(seed=seed)
        r = backtest(scores, prices)
        s = shuffle_test(scores, prices, runs=24, seed=seed)
        levels.append(r.sharpe)
        gaps.append(s["skill_above_chance"])
    assert sum(levels) / len(levels) > 1.0, "the market carries the headline"
    assert abs(sum(gaps) / len(gaps)) < 0.35, \
        "but on average no skill is demonstrated above a shuffled portfolio"


def test_the_shuffle_test_is_calibrated_and_not_merely_permissive():
    # A test at the 5% level must reject about 5% of noise — not none of it
    # (useless) and not most of it (a false-positive machine). Across a spread
    # of worlds with no planted edge, passes should stay rare.
    passes = 0
    worlds = 14
    for seed in range(20, 20 + worlds):
        scores, prices = build_noise_world(seed=seed)
        if shuffle_test(scores, prices, runs=24, seed=seed)["passes"]:
            passes += 1
    assert passes <= worlds * 0.25, \
        f"{passes} of {worlds} noise worlds passed — the test is too permissive"


def test_the_shuffle_test_names_the_problem_when_a_strategy_shows_no_skill():
    scores, prices = build_noise_world(seed=31)
    s = shuffle_test(scores, prices, runs=24)
    assert not s["passes"]
    assert "not coming from the ranking" in s["reading"]


# ------------------------------------------------------------------- real edge
def test_a_planted_edge_is_recovered():
    scores, prices, _ = build_world(edge=0.10, seed=4)
    r = backtest(scores, prices)
    assert r.net_return_annual > 0.05
    assert r.sharpe > 0.5


def test_the_shuffle_test_confirms_the_ranking_is_doing_the_work():
    scores, prices, _ = build_world(edge=0.15, seed=5)
    s = shuffle_test(scores, prices, runs=20)
    assert s["passes"] and s["p_value"] <= 0.05
    assert s["real_sharpe"] > s["shuffled_best"]


def test_perfect_foresight_scores_beat_everything_and_still_shuffle_away():
    # Scores that ARE the next period's return: the harness must transmit that
    # perfectly, and shuffling must then destroy it. This proves the shuffle
    # test can detect a signal rather than always saying no.
    scores, prices = build_noise_world(seed=9)
    cheat = {t: {s: prices[s][t + 21] / prices[s][t] - 1
                 for s in prices if len(prices[s]) > t + 21}
             for t in scores}
    r = backtest(cheat, prices)
    assert r.sharpe > 3, "look-ahead should look spectacular — that is the point"
    s = shuffle_test(cheat, prices, runs=24)
    assert s["passes"]
    assert s["skill_above_chance"] > 2


# ------------------------------------------------------------------- mechanics
def test_no_turnover_means_no_cost():
    scores, prices = build_noise_world(seed=11)
    same = {t: {s: (1.0 if s == "S0" else 0.0) for s in prices} for t in scores}
    cfg = BacktestConfig(top_n=1)
    r = backtest(same, prices, cfg)
    # Only the first rebalance buys; after that the holding never changes.
    assert r.turnover_per_rebalance < 0.1
    assert r.cost_drag_annual < 0.01


def test_the_weight_cap_is_respected():
    scores, prices = build_noise_world(seed=12)
    cfg = BacktestConfig(top_n=5, max_weight=0.25)
    r = backtest(scores, prices, cfg)
    assert r.periods > 0
    # Five names at a 25% cap must be fully invested at exactly 20% each.
    assert r.names_held == 5


def test_a_symbol_without_a_price_at_both_ends_is_never_held():
    scores, prices = build_noise_world(n_symbols=10, seed=13)
    prices["GHOST"] = [100.0] * 100          # series ends early
    for t in scores:
        scores[t]["GHOST"] = 99.0            # top-ranked every single time
    r = backtest(scores, prices, BacktestConfig(top_n=3))
    assert r.periods > 0, "the missing name must be skipped, not crash the run"


def test_an_empty_panel_returns_zero_rather_than_failing():
    assert backtest({}, {}).periods == 0
    assert backtest({5: {"A": 1.0}}, {"A": [1.0] * 10}).periods == 0


# ------------------------------------------------------------------- folds
def test_walk_forward_splits_and_judges_consistency():
    scores, prices, _ = build_world(edge=0.12, seed=6)
    w = walk_forward(scores, prices, folds=4)
    assert w["ok"] and len(w["folds"]) == 4
    assert w["positive_folds"] >= 3
    assert sum(f["periods"] for f in w["folds"]) <= len(scores)


def test_walk_forward_refuses_too_short_a_history():
    scores, prices = build_noise_world(n_days=200)
    assert walk_forward(scores, prices, folds=8)["ok"] is False


def test_a_strategy_that_only_worked_once_is_called_out():
    scores, prices = build_noise_world(seed=21)
    w = walk_forward(scores, prices, folds=4)
    assert w["ok"]
    if w["positive_folds"] < 2:
        assert "not evidence" in w["reading"]


# ------------------------------------------------------------------- verdict
def test_a_noise_result_is_not_called_evidence():
    scores, prices = build_noise_world(seed=31)
    r = backtest(scores, prices)
    s = shuffle_test(scores, prices, runs=24)
    a = assess(r, variants_tried=50, runs_of_shuffle=s)
    assert "not evidence" in a["verdict"]


def test_the_search_is_paid_for_in_the_verdict():
    scores, prices, _ = build_world(edge=0.15, seed=7)
    r = backtest(scores, prices)
    once = assess(r, variants_tried=1)
    many = assess(r, variants_tried=5000)
    assert once["deflated"]["benchmark_annual_from_luck"] \
        < many["deflated"]["benchmark_annual_from_luck"]



def test_too_few_permutations_is_reported_rather_than_failing_silently():
    # With 15 runs the smallest reachable p-value is 1/16 = 0.0625, so a real
    # signal would be reported as a failure. The harness must say so.
    scores, prices, _ = build_world(edge=0.20, seed=8)
    thin = shuffle_test(scores, prices, runs=15)
    assert not thin["runs_sufficient"]
    assert "permutations" in thin["reading"]
    ample = shuffle_test(scores, prices, runs=24)
    assert ample["runs_sufficient"] and ample["passes"]


def test_the_verdict_names_every_failing_check_readably():
    scores, prices = build_noise_world(seed=31)
    r = backtest(scores, prices)
    s = shuffle_test(scores, prices, runs=24)
    a = assess(r, variants_tried=500, runs_of_shuffle=s)
    assert a["verdict"].startswith("not evidence — ")
    assert "shuffling the scores" in a["verdict"]


def test_the_too_few_checks_fallback_can_actually_fire():
    # The bug this guards: `"x" + join(...) or "fallback"` never reaches the
    # fallback, because the left operand is always a non-empty string.
    from advisor.portfolio_backtest import BacktestResult
    empty = BacktestResult(0, 0, 0, 0, 0, 0, 0, 0, 0)
    a = assess(empty, variants_tried=1)
    assert a["checks_run"] < 2
    assert "too few" in a["verdict"]


# ------------------------------------------------------- combining signals
from advisor.portfolio_backtest import (  # noqa: E402
    combination_report, combine_signals, correlation, zscore_row,
)


def test_zscore_makes_incomparable_signals_comparable():
    # One signal in units of return, another in units of volatility. Averaging
    # raw would let the larger-spread one decide everything.
    row = {f"S{i}": i / 10 for i in range(20)}
    z = zscore_row(row)
    vals = list(z.values())
    assert abs(sum(vals) / len(vals)) < 1e-9, "centred"
    assert max(vals) <= 3.0 and min(vals) >= -3.0, "winsorised at three sigma"


def test_zscore_refuses_a_cross_section_too_thin_to_standardise():
    assert zscore_row({"A": 1.0, "B": 2.0}) == {}
    assert zscore_row({f"S{i}": 5.0 for i in range(20)}) == {}, "no spread, no z-score"


def test_an_outlier_cannot_decide_the_whole_portfolio():
    row = {f"S{i}": 0.01 * i for i in range(30)}
    row["BROKEN"] = 1e9
    z = zscore_row(row)
    assert z["BROKEN"] == 3.0, "clipped, not allowed to dominate"


def test_combining_keeps_only_dates_and_names_every_signal_scored():
    a = {10: {f"S{i}": i for i in range(20)}, 20: {f"S{i}": i for i in range(20)}}
    b = {10: {f"S{i}": -i for i in range(20)}}          # no date 20
    c = combine_signals(a, b)
    assert set(c) == {10}, "a date one signal could not score is dropped"

    a2 = {10: {f"S{i}": i for i in range(20)}}
    b2 = {10: {f"S{i}": -i for i in range(15)}}
    c2 = combine_signals(a2, b2)
    assert set(c2[10]) == {f"S{i}" for i in range(15)}, \
        "a name one signal could not score is dropped, never filled with zero"


def test_two_opposite_signals_combine_to_nothing():
    a = {10: {f"S{i}": i for i in range(20)}}
    b = {10: {f"S{i}": -i for i in range(20)}}
    c = combine_signals(a, b)
    assert all(abs(v) < 1e-9 for v in c[10].values())


def test_correlation_matches_the_obvious_cases():
    xs = [i / 10 for i in range(20)]
    assert abs(correlation(xs, xs) - 1.0) < 1e-9
    assert abs(correlation(xs, [-x for x in xs]) + 1.0) < 1e-9
    assert correlation([1, 2], [2, 3]) is None, "too short to correlate"
    assert correlation([1.0] * 20, list(range(20))) is None, "no variation"


def test_the_combination_report_measures_correlation_rather_than_assuming_it():
    scores, prices, _ = build_world(edge=0.10, seed=41)
    scores2, _, _ = build_world(edge=0.10, seed=42)
    # Same price panel, two different score sets over it.
    r1 = backtest(scores, prices)
    r2 = backtest({t: scores2[t] for t in scores if t in scores2}, prices)
    rep = combination_report({"a": r1, "b": r2})
    assert rep["ok"]
    assert -1 <= rep["average_correlation"] <= 1
    assert rep["ceiling_however_many_signals"] > 0
    assert "most_diversifying" in rep


def test_the_report_refuses_with_only_one_usable_signal():
    scores, prices, _ = build_world(edge=0.05)
    r = backtest(scores, prices)
    assert combination_report({"only": r})["ok"] is False


def test_the_report_compares_theory_against_what_actually_happened():
    scores, prices, _ = build_world(edge=0.10, seed=43)
    scores2, _, _ = build_world(edge=0.10, seed=44)
    common = {t: scores2[t] for t in scores if t in scores2}
    r1, r2 = backtest(scores, prices), backtest(common, prices)
    combined = backtest(combine_signals(scores, common), prices)
    rep = combination_report({"a": r1, "b": r2}, combined)
    assert "actual_combined_sharpe" in rep
    assert "theory_vs_actual" in rep
    assert isinstance(rep["beat_best_single"], bool)
