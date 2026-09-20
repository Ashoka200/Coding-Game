"""The statistics of movement: the results these are guarding are the ones that
are easy to state wrongly and expensive to get wrong."""
import math

from advisor.stats import (
    barrier_probability, describe_returns, feasible_target, grade_trade,
    kelly_fraction, minimum_safe_stop, noise_stop_probability,
    recommended_risk_fraction, risk_of_ruin,
)


def _walk(n=600, drift=0.0004, vol=0.018, seed=3):
    import random
    rng = random.Random(seed)
    p, out = 100.0, [100.0]
    for _ in range(n):
        p *= math.exp(rng.gauss(drift, vol))
        out.append(p)
    return out


# ---------------------------------------------------------------- distribution
def test_describe_recovers_the_parameters_it_was_given():
    prof = describe_returns(_walk(drift=0.0004, vol=0.018), risk_free=0.0)
    assert abs(prof.daily_vol - 0.018) < 0.002
    assert abs(prof.annual_vol - 0.018 * math.sqrt(250)) < 0.03
    assert prof.max_drawdown <= 0


def test_too_little_history_returns_nothing_rather_than_a_shaky_number():
    assert describe_returns([100, 101, 102]) is None


# ---------------------------------------------------------------- stops
def test_a_tight_stop_is_hit_by_noise_far_more_often_than_a_wide_one():
    tight = noise_stop_probability(0.02, 0.02, 20)
    wide = noise_stop_probability(0.12, 0.02, 20)
    assert tight > 0.75, "a 2% stop on a 2%-a-day stock is noise, not risk control"
    assert wide < 0.25
    assert tight > wide


def test_the_reflection_factor_is_not_forgotten():
    # The chance of *touching* -d at any point must exceed the chance of merely
    # *ending* below it. Reasoning about the endpoint is the classic error.
    from advisor.stats import _norm_cdf
    d, sigma = 0.05, 0.02 * math.sqrt(20)
    endpoint = 1 - _norm_cdf(abs(math.log(1 - d)) / sigma)
    touch = noise_stop_probability(d, 0.02, 20)
    assert touch > endpoint * 1.9


def test_minimum_safe_stop_round_trips():
    vol = 0.021
    d = minimum_safe_stop(vol, 20, tolerated_noise_hit=0.25)
    assert abs(noise_stop_probability(d, vol, 20) - 0.25) < 0.01


# ---------------------------------------------------------------- barriers
def test_driftless_odds_are_the_gamblers_ruin_result():
    o = barrier_probability(100, 110, 90)
    # log distances are near-symmetric here, so the odds sit near even
    assert abs(o.p_target_first - 0.5) < 0.03


def test_no_drift_means_no_edge_whatever_ratio_you_choose():
    # The result worth internalising: with no drift, the chance of reaching the
    # target first is EXACTLY the breakeven win rate the ratio demands. Widening
    # the target cannot manufacture an edge — it only moves both numbers.
    for target, stop in ((120, 90), (150, 95), (105, 99), (200, 50)):
        o = barrier_probability(100, target, stop)
        assert abs(o.p_target_first - o.breakeven_win_rate) < 1e-9
        assert abs(o.expectancy_r) < 1e-9


def test_a_two_to_one_trade_works_only_a_third_of_the_time_by_chance():
    o = barrier_probability(100, 100 * math.exp(0.20), 100 * math.exp(-0.10))
    assert abs(o.reward_to_risk - 2.0) < 1e-9
    assert abs(o.p_target_first - 1 / 3) < 0.01


def test_positive_drift_tilts_the_odds_toward_the_target():
    flat = barrier_probability(100, 120, 90, 0.0, 0.02)
    up = barrier_probability(100, 120, 90, 0.0012, 0.02)
    assert up.p_target_first > flat.p_target_first


def test_a_target_below_entry_is_refused():
    assert barrier_probability(100, 95, 90) is None
    assert barrier_probability(100, 120, 105) is None


# ---------------------------------------------------------------- sizing
def test_kelly_matches_the_textbook_case():
    assert abs(kelly_fraction(0.5, 2.0) - 0.25) < 1e-12
    assert kelly_fraction(0.3, 2.0) == 0.0, "no edge means no bet, not a small bet"


def test_recommendation_is_a_quarter_of_kelly_and_then_capped():
    r = recommended_risk_fraction(0.5, 2.0, cap=0.02)
    assert abs(r["quarter_kelly"] - 0.0625) < 1e-12
    assert r["recommended"] == 0.02 and r["capped_by_policy"]


def test_overbetting_a_real_edge_still_ruins_you():
    # Identical, genuinely positive edge in every case. Only the bet size moves.
    small = risk_of_ruin(0.5, 2.0, 0.02)
    full_kelly = risk_of_ruin(0.5, 2.0, 0.25)
    assert small < 0.02
    assert full_kelly > 0.9, "full Kelly on an estimated edge is a near-certain drawdown"


def test_no_edge_no_ruin_only_because_no_bet():
    assert risk_of_ruin(0.5, 2.0, 0.0) == 0.0


# ---------------------------------------------------------------- feasibility
def test_thirty_percent_a_day_names_its_own_impossibility():
    f = feasible_target(0.30)
    assert f.required_sharpe > 11
    # Starting from ten lakh, it would pass world GDP inside one quarter.
    assert f.days_to_exceed_world_gdp < 100
    assert "not reachable" in f.verdict


def test_the_ladder_is_monotonic_and_the_reachable_end_is_sane():
    sharpes = [feasible_target(t).required_sharpe
               for t in (0.0005, 0.002, 0.01, 0.05, 0.30)]
    assert sharpes == sorted(sharpes)
    modest = feasible_target(0.0005)          # 0.05% a day
    assert 0.10 < modest.target_annual < 0.16  # about 13% a year
    assert "reachable" in modest.verdict


def test_sharpe_two_is_reported_as_the_realistic_comparison():
    f = feasible_target(0.30)
    # Sharpe 2 at optimal leverage: growth of 2, so e^2 - 1 per year.
    assert abs(f.reachable_annual_at_sharpe_2 - (math.exp(2.0) - 1)) < 1e-9


# ---------------------------------------------------------------- grading
def test_grade_flags_a_stop_noise_will_eat():
    prof = describe_returns(_walk(vol=0.025))
    g = grade_trade(entry=100, target=112, stop=98, profile=prof)
    assert g["ok"]
    assert g["noise_stop_probability"] > 0.5
    assert any("noise" in f for f in g["flags"])
    assert g["verdict"] != "sound"


def test_grade_accepts_a_plan_drawn_with_room():
    prof = describe_returns(_walk(vol=0.012, drift=0.0006))
    g = grade_trade(entry=100, target=125, stop=90, profile=prof)
    assert g["ok"]
    assert g["noise_stop_probability"] < 0.35
    assert g["sizing"]["recommended"] <= 0.02


def test_grade_refuses_an_impossible_geometry():
    prof = describe_returns(_walk())
    assert grade_trade(entry=100, target=90, stop=95, profile=prof)["ok"] is False
