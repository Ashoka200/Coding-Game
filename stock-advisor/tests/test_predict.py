"""Prediction and sentiment: a forecast must be earned by evidence, and news
must never manufacture one where the history did not support it."""
import math
import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from advisor.predict import (  # noqa: E402
    MIN_SAMPLES, blend_with_sentiment, describe_state, forecast, wilson_interval,
)
from advisor.sentiment import Scored, aggregate, analyse  # noqa: E402


def series(n=1200, drift=0.0004, vol=0.012, seed=11):
    rng = random.Random(seed)
    close, p = [], 100.0
    for _ in range(n):
        p *= math.exp(rng.gauss(drift, vol))
        close.append(p)
    high = [c * 1.008 for c in close]
    low = [c * 0.992 for c in close]
    return close, high, low


# ---------- statistics ----------

def test_wilson_interval_is_wide_when_evidence_is_thin():
    narrow_lo, narrow_hi = wilson_interval(70, 100)
    wide_lo, wide_hi = wilson_interval(7, 10)          # same 70%, far less evidence
    assert (wide_hi - wide_lo) > (narrow_hi - narrow_lo) * 2
    assert 0 <= wide_lo <= wide_hi <= 1
    assert wilson_interval(0, 0) == (0.0, 1.0)


# ---------- state description ----------

def test_state_is_coarse_and_uses_only_past_data():
    close, high, low = series()
    st = describe_state(close, high, low, 500)
    assert set(st) == {"stage", "rsi_band", "momentum_band", "vol_band"}
    assert st["stage"] in (1, 2, 3, 4)
    assert st["rsi_band"] in ("high", "mid", "low")
    # a state computed at bar 500 must not change when later bars are appended
    extended = close + [close[-1] * 1.05] * 50
    assert describe_state(extended, high + [0] * 50, low + [0] * 50, 500) == st
    assert describe_state(close, high, low, 50) is None      # not enough history


# ---------- forecasts ----------

def test_forecast_refuses_without_enough_history():
    close, high, low = series(n=200)
    f = forecast("X", close, high, low)
    assert f.prob_up is None
    assert "insufficient history" in f.verdict


def test_forecast_refuses_when_too_few_days_match():
    close, high, low = series()
    f = forecast("X", close, high, low, min_samples=100_000)
    assert f.prob_up is None
    assert f.samples >= 0
    assert "too few comparable days" in f.verdict
    assert any("noise wearing a percentage sign" in c for c in f.caveats)


def test_forecast_reports_distribution_and_compares_to_base_rate():
    close, high, low = series(n=2000, seed=3)
    f = forecast("X", close, high, low, min_samples=20)
    if f.prob_up is None:                       # acceptable outcome; must be honest
        assert "no forecast" in f.verdict
        return
    assert 0 <= f.prob_up <= 1
    assert f.ci_low <= f.prob_up <= f.ci_high
    assert f.p25 <= f.median_return <= f.p75
    assert f.worst <= f.p25
    assert f.base_rate_prob_up is not None
    assert f.edge_vs_base == pytest.approx(f.prob_up - f.base_rate_prob_up, abs=1e-9)
    assert any("the median is not the risk" in c for c in f.caveats)
    assert any("not a prediction about this instance" in c for c in f.caveats)


def test_forecast_admits_when_it_has_no_edge_over_the_base_rate():
    close, high, low = series(n=2500, seed=7)
    f = forecast("X", close, high, low, min_samples=20)
    if f.prob_up is not None and f.ci_low <= f.base_rate_prob_up <= f.ci_high:
        assert "no edge" in f.verdict
        assert any("tells you nothing the calendar does not" in c for c in f.caveats)


# ---------- sentiment blending ----------

def test_sentiment_can_nudge_a_forecast_but_not_create_one():
    close, high, low = series(n=2000, seed=3)
    f = forecast("X", close, high, low, min_samples=20)
    if f.prob_up is not None:
        before = f.prob_up
        after = blend_with_sentiment(f, 1.0).prob_up
        assert after > before
        assert after - before <= 0.05 + 1e-9          # bounded, cannot dominate
        assert any("cannot override a weak historical record" in c for c in f.caveats)

    empty = forecast("X", *series(n=200))
    blended = blend_with_sentiment(empty, 1.0)
    assert blended.prob_up is None                     # news cannot invent a forecast
    assert any("nothing for it to adjust" in c for c in blended.caveats)


# ---------- sentiment aggregation ----------

def s(direction, materiality=0.8, age=1.0, confirmed=True, about=True, title="t"):
    return Scored(title=title, direction=direction, materiality=materiality,
                  event="results", confirmed=confirmed, about_company=about,
                  why="why", age_days=age)


def test_aggregate_weights_recency_materiality_and_confirmation():
    fresh = aggregate("X", [s(3, age=1)], "llm")
    stale = aggregate("X", [s(3, age=13)], "llm")
    assert fresh.score == stale.score              # direction is the same
    # but a rumour counts for less in the confidence
    rumour = aggregate("X", [s(3, confirmed=False)], "llm")
    assert rumour.confidence < fresh.confidence
    assert any("unconfirmed reporting" in c for c in rumour.caveats)


def test_disagreement_is_measured_and_flagged():
    split = aggregate("X", [s(3), s(-3), s(2), s(-2)], "llm")
    assert split.disagreement > 0.35
    assert any("disagrees with itself" in c for c in split.caveats)
    assert abs(split.score) < 0.35                 # opposing stories cancel

    aligned = aggregate("X", [s(3), s(2), s(3)], "llm")
    assert aligned.disagreement == 0
    assert aligned.score > 0.5


def test_items_not_about_the_company_are_ignored():
    read = aggregate("X", [s(3, about=False), s(3, about=False)], "llm")
    assert read.score is None
    assert "Absence of news is not evidence" in read.summary


def test_no_api_key_falls_back_to_keywords_and_says_so(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    read = analyse("X", [{"title": "X bags Rs 5,000 crore order from NHAI",
                          "age_days": 1.0}])
    assert read.method == "keywords"
    assert read.score is not None and read.score > 0
    assert any("not by reading" in c for c in read.caveats)
    assert any("misreads negation" in c for c in read.caveats)


def test_empty_headlines_produce_no_score():
    read = analyse("X", [])
    assert read.method == "none" and read.score is None
