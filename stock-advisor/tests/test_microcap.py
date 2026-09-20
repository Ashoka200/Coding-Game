"""Penny and micro-cap stocks. The property under test throughout: the exit is
evaluated before the business, because in this segment you can be entirely right
about the company and still lose everything to a circuit you cannot sell into."""
import math

from advisor.microcap import (
    ACCEPTABLE_EXIT_DAYS, assess, analyse_exit, circuit_hit_rate, days_to_exit,
    impact_cost, integrity_check, locked_days_to_fall, max_safe_position,
    screen, surveillance_veto,
)


# ----------------------------------------------------------------- liquidity
def test_exit_time_is_position_over_the_share_of_volume_you_may_take():
    # 10 lakh position, 5 lakh a day turnover, 10% participation -> 20 sessions.
    assert abs(days_to_exit(1_000_000, 500_000) - 20) < 1e-9


def test_no_turnover_means_no_answer_rather_than_a_convenient_zero():
    assert days_to_exit(100_000, 0) is None
    assert max_safe_position(None) is None


def test_the_safe_position_is_what_can_be_left_inside_a_week():
    cap = max_safe_position(500_000)
    assert abs(days_to_exit(cap, 500_000) - ACCEPTABLE_EXIT_DAYS) < 1e-9


def test_participation_here_is_far_lower_than_for_a_large_cap():
    from advisor.microcap import SAFE_PARTICIPATION
    assert SAFE_PARTICIPATION <= 0.10, \
        "in a thin stock your own order is the volume"


# ----------------------------------------------------------------- impact
def test_impact_follows_the_square_root_of_participation():
    # Four times the size should cost about twice the impact, not four times.
    small = impact_cost(100_000, 1_000_000, 0.05, spread_pct=0.0)
    big = impact_cost(400_000, 1_000_000, 0.05, spread_pct=0.0)
    assert abs(big / small - 2.0) < 1e-9


def test_the_spread_is_charged_and_it_is_wide_here():
    with_spread = impact_cost(100_000, 1_000_000, 0.05, spread_pct=0.03)
    without = impact_cost(100_000, 1_000_000, 0.05, spread_pct=0.0)
    assert abs((with_spread - without) - 0.015) < 1e-9


# ----------------------------------------------------------------- circuits
def test_a_thirty_percent_fall_in_a_five_percent_band_takes_six_locked_days():
    d = locked_days_to_fall(0.30, 0.05)
    assert 6.9 < d < 7.0 or abs(d - math.log(0.7) / math.log(0.95)) < 1e-9
    # A wider band reaches the same fall faster.
    assert locked_days_to_fall(0.30, 0.20) < d


def test_circuit_hit_rate_is_measured_from_the_actual_path():
    # Ten sessions, every one of them limit-down at 5%.
    locked = [100 * (0.95 ** i) for i in range(50)]
    assert circuit_hit_rate(locked, 0.05) > 0.95
    calm = [100 + i * 0.01 for i in range(50)]
    assert circuit_hit_rate(calm, 0.05) == 0.0


def test_circuit_hit_rate_refuses_a_short_history():
    assert circuit_hit_rate([100, 101], 0.05) is None


# ----------------------------------------------------------------- surveillance
def test_the_severe_stages_block_regardless_of_the_business():
    assert surveillance_veto("gsm_3")["blocked"] is True
    assert surveillance_veto("gsm_4")["blocked"] is True
    assert surveillance_veto("none")["blocked"] is False


def test_the_consequence_is_stated_not_just_the_label():
    v = surveillance_veto("gsm_3")
    assert "ONCE A WEEK" in v["note"]
    v2 = surveillance_veto("gsm_2")
    assert "50%" in v2["note"], "the surveillance deposit is the part that traps you"


def test_an_unknown_stage_is_treated_as_restricted_not_as_safe():
    v = surveillance_veto("something_new")
    assert v["blocked"] is True and "until confirmed" in v["note"]


# ----------------------------------------------------------------- integrity
def test_an_auditor_resignation_fires():
    r = integrity_check({"auditor_resigned": True})
    assert r["fired"] and not r["clean"]
    assert "resign" in r["fired"][0]["why"]


def test_unknown_markers_are_reported_not_assumed_clean():
    r = integrity_check({})
    assert not r["fired"]
    assert len(r["unknown"]) == 7 and not r["clean"]


def test_all_markers_absent_reads_as_clean():
    facts = {k: False for k, _, _ in
             __import__("advisor.microcap", fromlist=["x"]).FRAUD_MARKERS}
    r = integrity_check(facts)
    assert r["clean"] and not r["fired"]


# ----------------------------------------------------------------- business
def test_the_screen_refuses_to_judge_on_too_little():
    assert screen({"netMargin": 0.05})["verdict"] == "too little disclosed to judge"


def test_a_real_small_business_passes():
    r = screen({"netMargin": 0.08, "debtToEquity": 0.2, "cashConversion": 0.8,
                "revenueGrowth": 0.22, "roce": 0.18, "promoterHolding": 0.62})
    assert r["score"] == 1.0 and "real business" in r["verdict"]


def test_a_story_stock_fails():
    r = screen({"netMargin": -0.15, "debtToEquity": 2.4, "cashConversion": 0.1,
                "revenueGrowth": -0.05, "roce": 0.01, "promoterHolding": 0.12})
    assert r["score"] == 0.0 and "do not support" in r["verdict"]


# ----------------------------------------------------------------- the order
GOOD_SMALL = dict(
    surveillance_stage="none", circuit_band=0.10, medianTurnover=8_000_000,
    dailyVol=0.04, spread=0.008,
    netMargin=0.09, debtToEquity=0.25, cashConversion=0.85,
    revenueGrowth=0.26, roce=0.19, promoterHolding=0.58,
    auditor_resigned=False, promoter_pledge_high=False, frequent_preferential=False,
    negative_networth=False, name_changed_recently=False, audit_qualified=False,
    promoter_holding_falling=False,
)


def test_a_clean_liquid_microcap_passes_all_three_gates():
    r = assess(GOOD_SMALL, position_value=200_000)
    assert r["investable"] and "all three gates" in r["headline"]
    assert r["exit"]["days_to_exit"] < ACCEPTABLE_EXIT_DAYS


def test_surveillance_outranks_a_perfect_business():
    r = assess(dict(GOOD_SMALL, surveillance_stage="gsm_3"), 200_000)
    assert not r["investable"]
    assert "surveillance" in r["headline"]
    # The business is still excellent; that is precisely the point.
    assert r["business"]["score"] == 1.0


def test_an_integrity_marker_outranks_a_good_business_too():
    r = assess(dict(GOOD_SMALL, auditor_resigned=True), 200_000)
    assert not r["investable"] and "accounts cannot be relied on" in r["headline"]


def test_an_unexitable_position_is_refused_even_when_everything_else_is_fine():
    thin = dict(GOOD_SMALL, medianTurnover=50_000)
    r = assess(thin, position_value=1_000_000)
    assert not r["investable"]
    assert "cannot be exited" in r["headline"]
    assert r["exit"]["days_to_exit"] > 30


def test_the_same_company_becomes_investable_at_a_smaller_size():
    thin = dict(GOOD_SMALL, medianTurnover=200_000)
    assert not assess(thin, 1_000_000)["investable"]
    assert assess(thin, 50_000)["investable"], \
        "size, not quality, is what changed — and that is the whole lesson"


def test_the_cost_hurdle_is_stated_in_advance():
    r = assess(dict(GOOD_SMALL, medianTurnover=300_000, spread=0.03), 250_000)
    assert r["cost_hurdle"] > 0.03
    assert "worth more than" in r["cost_note"]


def test_a_narrow_band_warns_that_a_stop_cannot_execute():
    r = assess(dict(GOOD_SMALL, circuit_band=0.05), 100_000)
    assert any("stop-loss cannot execute" in w for w in r["exit"]["warnings"])


def test_position_advice_names_a_number():
    r = assess(GOOD_SMALL, 200_000)
    assert "Cap this at" in r["position_advice"]


def test_missing_data_never_reads_as_investable():
    # The bug this guards: an empty facts dict produced "passes all three gates"
    # while the warnings underneath said no size could be justified at all.
    r = assess({"symbol": "UNKNOWN"}, position_value=200_000)
    assert not r["investable"]
    assert "no turnover data" in r["headline"].lower()


def test_unverifiable_integrity_blocks_even_a_liquid_good_business():
    facts = {k: v for k, v in GOOD_SMALL.items()
             if k not in ("auditor_resigned", "audit_qualified",
                          "promoter_pledge_high", "negative_networth")}
    r = assess(facts, 100_000)
    assert not r["investable"]
    assert "could not be checked" in r["headline"]


def test_an_oversized_position_is_not_quietly_passed():
    r = assess(dict(GOOD_SMALL, medianTurnover=300_000), 3_000_000)
    assert not r["investable"]
    assert "oversized" in r["headline"] or "cannot be exited" in r["headline"]
