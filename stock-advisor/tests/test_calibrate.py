"""Thresholds that move with the market.

The property under test throughout: the same company, judged against two
different markets, gets two different answers — while each investor's relative
stance stays exactly where the doctrine put it."""
import math

from advisor.calibrate import (
    MarketContext, build_context, detect_decay, measure_correlation,
    measure_skill, percentile_of, risk_parameters, value_at_percentile,
)
from advisor.masters import apply_all, buffett, damani, jhunjhunwala


def market(roes, des, sector="Consumer staples"):
    return [{"sector": sector, "roe": r, "debtToEquity": d}
            for r, d in zip(roes, des)]


# ----------------------------------------------------------------- mechanics
def test_percentiles_need_a_real_population():
    assert percentile_of(0.5, [0.1, 0.2, 0.3]) is None, "three peers is not a distribution"
    assert value_at_percentile([1, 2, 3], 0.5) is None


def test_percentile_and_its_inverse_agree():
    pop = [i / 100 for i in range(1, 101)]
    v = value_at_percentile(pop, 0.75)
    assert abs(percentile_of(v, pop) - 0.75) < 0.02


def test_lower_is_better_metrics_are_ranked_upside_down():
    ctx = MarketContext(as_of="t", universe=market([0.1] * 20,
                                                   [i / 20 for i in range(20)]))
    # Almost no debt must rank near the top, not the bottom.
    assert ctx.rank("debtToEquity", 0.02) > 0.9
    assert ctx.rank("debtToEquity", 0.9) < 0.15


def test_a_thin_sector_falls_back_to_the_whole_market():
    rows = market([0.2] * 20, [0.3] * 20, sector="Consumer staples")
    rows += [{"sector": "Shipping", "roe": 0.05, "debtToEquity": 2.0}] * 3
    ctx = MarketContext(as_of="t", universe=rows)
    # Three shipping companies cannot define a distribution, so the rank must
    # still be produced — from the whole market.
    assert ctx.rank("roe", 0.05, sector="Shipping") is not None


def test_no_context_means_no_judgement_rather_than_a_wrong_one():
    ctx = MarketContext(as_of="t", universe=[])
    assert ctx.meets("roe", 0.2, "strict") is None
    assert ctx.rank("roe", 0.2) is None


# ----------------------------------------------------------------- adaptation
def test_the_same_company_is_judged_differently_in_different_markets():
    firm = {"sector": "Consumer staples", "roe": 0.16, "debtToEquity": 0.35}

    # A market where everyone earns 25%+: 16% is now unremarkable.
    rich = MarketContext(as_of="t", universe=market(
        [0.22 + i / 200 for i in range(20)], [0.3] * 20))
    # A market where 8% is typical: the same 16% is excellent.
    poor = MarketContext(as_of="t", universe=market(
        [0.04 + i / 400 for i in range(20)], [0.3] * 20))

    assert rich.meets("roe", 0.16, "moderate") is False
    assert poor.meets("roe", 0.16, "moderate") is True

    hot = buffett(firm, rich)
    cold = buffett(firm, poor)
    assert hot.score < cold.score, \
        "the same balance sheet must read differently against different peers"


def test_the_relative_stances_survive_calibration():
    # One market, one company. Damani must still be stricter on debt than
    # Buffett — the doctrine is fixed even though the level floats.
    universe = market([0.2] * 30, [i / 30 for i in range(30)])
    ctx = MarketContext(as_of="t", universe=universe)
    firm = {"sector": "Consumer staples", "roe": 0.2, "debtToEquity": 0.30}
    d = [c for c in damani(firm, ctx).criteria if c.theme == "debt"][0]
    b = [c for c in buffett(firm, ctx).criteria if c.theme == "debt"][0]
    assert b.passed is True and d.passed is False


def test_the_criterion_reports_the_peer_comparison_it_used():
    ctx = MarketContext(as_of="t", universe=market([0.1] * 25, [0.5] * 25))
    c = [x for x in buffett({"sector": "Consumer staples", "roe": 0.30},
                            ctx).criteria if x.theme == "returns"][0]
    assert "better than" in c.seen


def test_lenses_still_run_with_no_context_at_all():
    v = apply_all({"roe": 0.25, "debtToEquity": 0.2, "pe": 20})
    assert all(x.judged >= 1 for x in v)


# ----------------------------------------------------------------- risk params
def test_risk_parameters_fall_back_without_context():
    r = risk_parameters(None)
    assert r["stop_atr_multiple"] == 2.0 and "defaults" in r["basis"]


def test_a_noisier_market_widens_stops_and_shrinks_positions():
    calm = risk_parameters(MarketContext(as_of="t", index_annual_vol=0.12))
    wild = risk_parameters(MarketContext(as_of="t", index_annual_vol=0.34))
    assert wild["stop_atr_multiple"] > calm["stop_atr_multiple"]
    assert wild["max_position"] < calm["max_position"]
    assert wild["vol_target"] < calm["vol_target"]


def test_a_drawdown_cuts_exposure_again_on_top_of_volatility():
    flat = risk_parameters(MarketContext(as_of="t", index_annual_vol=0.20,
                                         index_drawdown=-0.02))
    deep = risk_parameters(MarketContext(as_of="t", index_annual_vol=0.20,
                                         index_drawdown=-0.25))
    assert deep["max_position"] < flat["max_position"] * 0.6


# ----------------------------------------------------------------- measuring
def test_correlation_between_lenses_is_measured_not_assumed():
    same = [i / 20 for i in range(20)]
    hist = {"a": same, "b": same, "c": [1 - x for x in same]}
    m = measure_correlation(hist)
    assert m["ok"]
    assert m["pairs"]["a vs b"] > 0.99
    assert m["pairs"]["a vs c"] < -0.99
    assert m["most_diversifying"] == "a vs c"


def test_correlation_refuses_a_thin_history():
    assert measure_correlation({"a": [1, 2], "b": [2, 3]})["ok"] is False


def test_skill_is_measured_from_closed_calls():
    # Scores that genuinely predicted the outcome.
    good = [{"score": i / 50, "forward_return": i / 50 + (0.01 if i % 2 else -0.01)}
            for i in range(50)]
    m = measure_skill(good)
    assert m["ok"] and m["ic"] > 0.9 and m["significant"]


def test_skill_refuses_to_report_an_ic_from_too_few_calls():
    m = measure_skill([{"score": 0.5, "forward_return": 0.1}] * 10)
    assert m["ok"] is False and "thirty" in m["why"]


def test_a_weak_ic_is_reported_as_not_yet_distinguishable():
    import random
    rng = random.Random(4)
    noise = [{"score": rng.random(), "forward_return": rng.gauss(0, 0.05)}
             for _ in range(40)]
    m = measure_skill(noise)
    assert m["ok"] and not m["significant"]
    assert "provisional" in m["reading"]


def test_decay_is_detected_when_a_signal_stops_working():
    dead = detect_decay([0.08, 0.07, 0.09, 0.08, 0.01, 0.00, -0.01, 0.00])
    assert dead["ok"] and dead["decayed"]
    assert "halve" in dead["action"]


def test_a_steady_signal_is_not_flagged():
    alive = detect_decay([0.06, 0.07, 0.05, 0.06, 0.07, 0.06, 0.05, 0.07])
    assert alive["ok"] and not alive["decayed"]


def test_decay_needs_enough_history_to_compare():
    assert detect_decay([0.05, 0.04])["ok"] is False


# ----------------------------------------------------------------- building it
def test_context_derives_regime_from_the_index_itself():
    rising = [100 * (1.0004 ** i) for i in range(300)]
    calm = build_context([], rising)
    assert calm.regime in ("normal", "unsettled")
    assert calm.index_annual_vol is not None and calm.index_drawdown > -0.02

    crashed = rising + [rising[-1] * (1 - 0.30)]
    crisis = build_context([], crashed)
    assert crisis.regime == "crisis" and crisis.index_drawdown <= -0.20


def test_context_survives_having_almost_no_data():
    ctx = build_context([], None)
    assert ctx.regime == "unknown" and ctx.index_annual_vol is None
    assert risk_parameters(ctx)["stop_atr_multiple"] == 2.0
