"""The feedback loop. The property under test throughout: a parameter must
declare whether it was measured or assumed, and an assumption must never be
presented as evidence."""
import json

from advisor.learning import (
    ASSUMED_IC, ASSUMED_LENS_CORRELATION, forward_return,
    lens_correlation_from_records, live_parameters,
    requirements_with_measured, rolling_ic, skill_from_records,
)


def call(conviction, entry, exit_price, action="buy", when="2026-01-01",
         lenses=None):
    return {
        "created_at": when, "action": action, "conviction": conviction,
        "entry_low": entry, "entry_high": entry, "exit_price": exit_price,
        "engine_json": json.dumps({"lenses": lenses or {}}),
    }


# --------------------------------------------------------------- outcome maths
def test_forward_return_is_measured_from_the_prices_recorded():
    assert abs(forward_return(call(70, 100, 120)) - 0.20) < 1e-12


def test_a_sell_call_that_was_right_counts_as_a_win():
    # The stock fell after a sell call: the call was correct, so the sign flips.
    assert forward_return(call(80, 100, 80, action="sell")) > 0
    assert forward_return(call(80, 100, 120, action="sell")) < 0


def test_an_entry_range_is_averaged():
    r = dict(call(70, 100, 110)); r["entry_high"] = 120
    assert abs(forward_return(r) - (110 / 110 - 1)) < 1e-12


def test_a_call_with_no_exit_yields_nothing():
    r = call(70, 100, None)
    assert forward_return(r) is None


# --------------------------------------------------------------- skill
def test_skill_is_assumed_and_labelled_when_the_record_is_thin():
    p = skill_from_records([call(70, 100, 110)] * 5)
    assert p.source == "assumed" and p.value == ASSUMED_IC
    assert not p.trustworthy
    assert "until the record can speak" in p.note


def test_skill_is_measured_once_there_are_enough_closed_calls():
    # Conviction genuinely predicted the outcome.
    recs = [call(40 + i, 100, 100 * (1 + (i - 25) / 200)) for i in range(50)]
    p = skill_from_records(recs)
    assert p.source == "measured" and p.n == 50
    assert p.value > 0.9 and p.trustworthy


def test_a_system_with_no_skill_measures_as_having_none():
    import random
    rng = random.Random(3)
    recs = [call(rng.randint(30, 90), 100, 100 * (1 + rng.gauss(0, 0.05)))
            for _ in range(60)]
    p = skill_from_records(recs)
    assert p.source == "measured"
    assert not p.trustworthy, "noise must not be reported as skill"


# --------------------------------------------------------------- correlation
def test_lens_correlation_is_measured_from_stored_scores():
    recs = []
    for i in range(20):
        x = i / 20
        recs.append(call(60, 100, 105, lenses={
            "Buffett": x, "Agrawal": x, "Damani": 1 - x}))
    p = lens_correlation_from_records(recs)
    assert p.source == "measured" and p.trustworthy
    assert "most redundant" in p.note


def test_lens_correlation_falls_back_and_says_why_it_matters():
    p = lens_correlation_from_records([call(60, 100, 105)])
    assert p.source == "assumed" and p.value == ASSUMED_LENS_CORRELATION
    assert "decides" in p.note, \
        "the fallback must say this guess drives the reachability verdict"


def test_malformed_engine_json_is_skipped_not_fatal():
    bad = dict(call(60, 100, 105)); bad["engine_json"] = "{not json"
    p = lens_correlation_from_records([bad])
    assert p.source == "assumed"


# --------------------------------------------------------------- decay
def test_rolling_ic_needs_a_real_record_before_it_speaks():
    assert rolling_ic([call(60, 100, 105)] * 20) == []


def test_rolling_ic_produces_one_value_per_bucket():
    recs = [call(40 + (i % 50), 100, 100 * (1 + ((i % 50) - 25) / 200),
                 when=f"2026-{1 + i // 30:02d}-{1 + i % 28:02d}")
            for i in range(120)]
    series = rolling_ic(recs, buckets=6)
    assert len(series) == 6


# --------------------------------------------------------------- the surface
def test_live_parameters_declares_how_much_is_guesswork():
    p = live_parameters([])
    assert p["measured_count"] == 0
    assert "published default" in p["summary"]
    assert p["warning"] and "provisional" in p["warning"]


def test_the_warning_clears_once_skill_is_established():
    recs = [call(40 + i, 100, 100 * (1 + (i - 25) / 200)) for i in range(60)]
    p = live_parameters(recs)
    assert p["parameters"]["information_coefficient"]["source"] == "measured"
    assert p["warning"] is None


def test_transfer_coefficient_stays_honest_about_being_unmeasurable_yet():
    p = live_parameters([])["parameters"]["transfer_coefficient"]
    assert p["source"] == "assumed"
    assert "live fills" in p["note"]


def test_requirements_carry_their_provenance():
    r = requirements_with_measured(0.50, [])
    assert r["confidence"].startswith("resting on assumed")
    prov = r["parameter_provenance"]
    assert prov["information_coefficient"]["source"] == "assumed"
    assert r["required_sharpe"] > 0


def test_requirements_switch_to_measured_when_the_record_supports_it():
    recs = [call(40 + i, 100, 100 * (1 + (i - 25) / 200)) for i in range(60)]
    r = requirements_with_measured(0.50, recs)
    assert r["confidence"] == "resting on measured skill"
    assert r["parameter_provenance"]["information_coefficient"]["source"] == "measured"


def test_a_measured_skill_changes_the_breadth_the_target_demands():
    assumed = requirements_with_measured(0.50, [])
    # A system with genuinely high skill needs far fewer independent decisions.
    recs = [call(40 + i, 100, 100 * (1 + (i - 25) / 200)) for i in range(60)]
    measured = requirements_with_measured(0.50, recs)
    assert (measured["independent_decisions_per_year"]
            < assumed["independent_decisions_per_year"])


def test_reading_an_absent_journal_returns_nothing_rather_than_failing():
    from advisor.learning import read_journal
    assert isinstance(read_journal(), list)
