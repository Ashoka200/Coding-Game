"""The two things that make this better than the five checklists alone:
knowing when each method is in its blind spot, and the mathematics that says
what a combination of methods can and cannot reach."""
import math

from advisor.ensemble import (
    breadth_required, combine_sharpe, effective_breadth, information_ratio,
    paths_to_target, realised_vol, requirements_for, signals_needed,
    volatility_target,
)
from advisor.failures import (
    accounting_divergence, crowding, cyclical_peg_illusion, discount_lenses,
    momentum_reversal_risk, quality_trap, run_all, value_trap,
)
from advisor.masters import apply_all


# ------------------------------------------------------------- Grinold
def test_the_law_is_skill_times_root_breadth():
    assert abs(information_ratio(0.05, 400) - 1.0) < 1e-12
    # Quadrupling breadth only doubles the ratio — the square root is the point.
    assert abs(information_ratio(0.05, 1600) - 2.0) < 1e-12


def test_transfer_coefficient_is_not_optional():
    full = information_ratio(0.05, 400, 1.0)
    real = information_ratio(0.05, 400, 0.5)
    assert abs(real - full / 2) < 1e-12, \
        "constraints halve the signal before a trade is placed"


def test_breadth_required_inverts_the_law():
    br = breadth_required(0.9, 0.05, 1.0)
    assert abs(information_ratio(0.05, br, 1.0) - 0.9) < 1e-9
    assert breadth_required(0.9, 0.0) is None


def test_correlation_destroys_gross_breadth():
    assert effective_breadth(600, 0.0) == 600
    assert effective_breadth(600, 0.4) < 5, \
        "600 correlated bets carry almost no independent information"
    assert effective_breadth(600, 0.05) > effective_breadth(600, 0.4)


# ------------------------------------------------------------- combination
def test_uncorrelated_signals_combine_as_root_n():
    c = combine_sharpe(0.5, 4, 0.0)
    assert abs(c.combined_sharpe - 1.0) < 1e-12


def test_identical_signals_combine_to_nothing_extra():
    c = combine_sharpe(0.5, 10, 0.999)
    assert abs(c.combined_sharpe - 0.5) < 0.02


def test_the_ceiling_is_real_and_correlation_sets_it():
    c = combine_sharpe(0.5, 5, 0.25)
    assert abs(c.ceiling_however_many_signals - 0.5 / math.sqrt(0.25)) < 1e-12
    huge = combine_sharpe(0.5, 10000, 0.25)
    assert huge.combined_sharpe < c.ceiling_however_many_signals


def test_a_sixth_lens_adds_less_when_lenses_overlap():
    diverse = combine_sharpe(0.5, 5, 0.1).marginal_gain_from_one_more
    same = combine_sharpe(0.5, 5, 0.8).marginal_gain_from_one_more
    assert diverse > same * 5, \
        "overlapping methods are what make more methods pointless"


def test_a_target_above_the_ceiling_is_called_unreachable_not_expensive():
    r = signals_needed(target_sharpe=2.0, average_sharpe=0.5,
                       average_correlation=0.35)
    assert r["reachable"] is False
    assert "however many signals" in r["why"]


def test_a_target_below_the_ceiling_returns_a_count():
    r = signals_needed(target_sharpe=0.7, average_sharpe=0.5,
                       average_correlation=0.1)
    assert r["reachable"] and r["signals_needed"] >= 2


def test_paths_say_what_would_have_to_change():
    paths = paths_to_target(0.90, single_signal_sharpe=0.5)
    assert paths[0]["max_average_correlation"] < 0.35, \
        "at 0.35 correlation the target is out of reach, so the path must ask for less"
    assert all(p["max_average_correlation"] <= 0.999 for p in paths)


# ------------------------------------------------------------- vol targeting
def test_volatility_estimate_never_peeks_at_today():
    rets = [0.01] * 30 + [0.10] * 5
    vols = realised_vol(rets, lookback=20)
    assert vols[:20] == [None] * 20
    # The spike starts at index 30; the estimate at index 30 must not contain it.
    assert vols[30] < vols[34]


def test_volatility_targeting_helps_when_volatility_clusters():
    import random
    rng = random.Random(5)
    rets, v = [], 0.012
    for _ in range(1500):
        v = 0.90 * v + 0.10 * 0.012 + (0.004 if rng.random() < 0.05 else 0)
        rets.append(rng.gauss(0.0006, v))
    r = volatility_target(rets, 0.15)
    assert r["ok"]
    assert r["vol_targeted"]["sharpe"] > r["unscaled"]["sharpe"]
    assert r["vol_targeted"]["annual_vol"] < r["unscaled"]["annual_vol"]


def test_leverage_is_capped_so_a_quiet_market_cannot_max_the_position():
    rets = [0.0001] * 400              # almost no volatility at all
    r = volatility_target(rets, 0.15, max_leverage=2.0)
    assert r["ok"] and r["max_exposure"] <= 2.0


def test_too_little_history_gets_no_answer():
    assert volatility_target([0.01] * 40, 0.15)["ok"] is False


# ------------------------------------------------------------- failure modes
QUALITY_TRAPPED = dict(
    roe=0.28, pe=72.0, pe_percentile=0.93,
    earningsGrowth=0.04, earningsCagr3y=0.18,
)


def test_quality_trap_needs_all_three_conditions():
    assert quality_trap(QUALITY_TRAPPED).triggered is True
    # Rich and high-quality but still growing: not a trap.
    assert quality_trap(dict(QUALITY_TRAPPED, earningsGrowth=0.20)).triggered is False
    # Decelerating but cheap against its own history: not a trap either.
    assert quality_trap(dict(QUALITY_TRAPPED, pe_percentile=0.30)).triggered is False


def test_quality_trap_suspends_exactly_the_quality_lenses():
    m = quality_trap(QUALITY_TRAPPED)
    assert "Raamdeo Agrawal" in m.invalidates and "Warren Buffett" in m.invalidates
    assert "Peter Lynch" not in m.invalidates


def test_value_trap_is_the_mirror_image():
    trapped = dict(pe=8.0, roe=0.06, roe_3y_ago=0.19, above200dma=False)
    assert value_trap(trapped).triggered is True
    assert value_trap(dict(trapped, above200dma=True)).triggered is False
    assert value_trap(dict(trapped, roe=0.20)).triggered is False


def test_peg_illusion_fires_only_for_cyclicals_at_peak_margins():
    peak = dict(sector="Metals & mining", peg=0.5, opMargin=0.24,
                opMargin_5y_high=0.25)
    assert cyclical_peg_illusion(peak).triggered is True
    # Same numbers, non-cyclical business: not the illusion.
    assert cyclical_peg_illusion(dict(peak, sector="Consumer staples")).triggered is False
    # Cyclical but mid-cycle margins: fine.
    assert cyclical_peg_illusion(dict(peak, opMargin=0.10)).triggered is False


def test_momentum_reversal_fires_in_the_rebound_not_the_fall():
    assert momentum_reversal_risk({"market_drawdown": -0.32,
                                   "market_rebounding": True}).triggered is True
    assert momentum_reversal_risk({"market_drawdown": -0.32,
                                   "market_rebounding": False}).triggered is False


def test_accounting_divergence_overrides_everything():
    m = accounting_divergence({"cashConversion": 0.35,
                               "cashConversion_3y_avg": 0.95,
                               "earningsGrowth": 0.22})
    assert m.triggered is True and m.severity == "serious"
    assert len(m.invalidates) == 5, "this one breaks every lens at once"


def test_an_untestable_mode_says_so_instead_of_passing():
    for m in run_all({}):
        assert m.triggered is None and m.severity == "unknown"
        assert "needs" in m.evidence or "need" in m.evidence


# ------------------------------------------------------------- the join
CLEAN = dict(
    sector="Consumer staples", roe=0.26, roce=0.29, netMargin=0.16,
    debtToEquity=0.12, interestCover=22.0, cashConversion=0.95,
    earningsCagr3y=0.19, revenueCagr3y=0.14, earningsGrowth=0.18,
    pe=34.0, currentRatio=1.8, dividendYield=0.011, annualVol=0.22,
    above200dma=True, revenue_history=[100, 112, 127, 141, 160, 182],
)


def test_endorsements_survive_when_no_failure_mode_is_active():
    facts = dict(CLEAN, pe_percentile=0.45, roe_3y_ago=0.24,
                 cashConversion_3y_avg=0.92, institutionalHolding=0.30,
                 market_drawdown=-0.04, market_rebounding=False,
                 opMargin=0.18, opMargin_5y_high=0.21, peg=1.8)
    d = discount_lenses(facts, apply_all(facts))
    assert not d["fired"]
    assert d["endorsements_still_standing"]
    assert "face value" in d["headline"]


def test_a_quality_trap_removes_the_quality_endorsements():
    facts = dict(CLEAN, pe=72.0, pe_percentile=0.93, earningsGrowth=0.04,
                 roe_3y_ago=0.24, cashConversion_3y_avg=0.92,
                 institutionalHolding=0.30, market_drawdown=-0.04,
                 market_rebounding=False, opMargin=0.18, opMargin_5y_high=0.21,
                 peg=1.8)
    d = discount_lenses(facts, apply_all(facts))
    assert "Quality trap" in [m["name"] for m in d["fired"]]
    assert "Raamdeo Agrawal" in d["suspended_authors"]
    assert "Raamdeo Agrawal" not in d["endorsements_still_standing"]


def test_untestable_modes_are_reported_not_hidden():
    d = discount_lenses({}, apply_all({}))
    assert len(d["untestable"]) == 6
    assert "could not be tested" in d["headline"]
