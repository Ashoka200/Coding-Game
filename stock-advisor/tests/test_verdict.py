"""Tests for the nine-stage decision engine and the news classifier."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from advisor.verdict import decide  # noqa: E402


FEAT = {"close": 100.0, "atr14": 2.0, "swing_low_20d": 94.0, "rsi14": 60.0,
        "dist_52w_high": -0.03, "sma200": 90.0, "ema50": 95.0}
GOOD_FUND = {"pe": 20, "roe": 0.22, "roce": 0.24, "debt_to_equity": 0.3, "interest_cover": 12}
JUNK_FUND = {"pe": 90, "roe": 0.02, "roce": 0.03, "debt_to_equity": 1.2, "interest_cover": 2}


def test_quality_uptrend_is_a_long_term_buy():
    v = decide("X", FEAT, GOOD_FUND, 78, news_pressure={"tone": "mixed", "net": 0,
                                                        "material_count": 0},
               stage=2, regime_risk_on=True)
    assert v.action == "BUY"
    assert v.horizon.startswith("Long term")
    assert v.conviction > 60
    assert v.levels["stop"] < v.levels["reference_price"] < v.levels["target1"]


def test_breached_exit_price_forces_a_sell_even_on_good_news():
    v = decide("X", dict(FEAT, close=80.0), GOOD_FUND, 80,
               news_pressure={"tone": "positive", "net": 3, "material_count": 2},
               stage=2, regime_risk_on=True, holding={"qty": 10, "stop": 85.0})
    assert v.action == "SELL"
    assert v.conviction >= 85
    assert any("exit price" in s.finding for s in v.chain)


def test_grave_news_vetoes_everything():
    grave = [{"weight": -3, "event_label": "Fraud or investigation",
              "title": "Regulator opens probe into X", "age_days": 1}]
    held = decide("X", FEAT, GOOD_FUND, 80, news_items=grave,
                  news_pressure={"tone": "negative", "net": -3, "material_count": 1},
                  stage=2, regime_risk_on=True, holding={"qty": 5})
    assert held.action == "SELL"
    fresh = decide("X", FEAT, GOOD_FUND, 80, news_items=grave,
                   news_pressure={"tone": "negative", "net": -3, "material_count": 1},
                   stage=2, regime_risk_on=True)
    assert fresh.action == "AVOID"
    assert v_stage(fresh, "Veto")


def test_ruinous_leverage_vetoes():
    v = decide("X", FEAT, {"pe": 8, "debt_to_equity": 4.0, "interest_cover": 1.1}, 42,
               stage=2, regime_risk_on=True)
    assert v.action == "AVOID"
    assert any("balance sheet" in s.finding for s in v.chain)


def test_missing_evidence_caps_confidence_and_forbids_long_term():
    v = decide("X", FEAT, None, None, stage=2, regime_risk_on=True)
    assert v.conviction <= 60                    # no fundamentals, no news
    assert v.horizon.startswith("Short term")    # never a long-term call without financials
    assert "fundamentals" in v.unknowns and "news" in v.unknowns


def test_downtrend_junk_flags_the_short_case_but_not_a_naked_short():
    v = decide("X", dict(FEAT, close=70.0, rsi14=30.0), JUNK_FUND, 32,
               news_pressure={"tone": "negative", "net": -2, "material_count": 1},
               stage=4, regime_risk_on=False)
    assert v.action == "AVOID"
    assert v.short_case is True
    assert any("never a naked short" in s.finding for s in v.chain)


def test_concentration_forces_a_trim():
    v = decide("X", FEAT, GOOD_FUND, 80, stage=2, regime_risk_on=True,
               holding={"qty": 100, "weight": 0.22})
    assert v.action == "TRIM"


def test_chain_is_ordered_and_complete():
    v = decide("X", FEAT, GOOD_FUND, 75,
               news_pressure={"tone": "mixed", "net": 0, "material_count": 0},
               stage=2, regime_risk_on=True)
    stages = [s.stage for s in v.chain]
    assert stages[0] == "Evidence"
    for expected in ("Business", "Valuation", "News", "Trend", "Horizon"):
        assert expected in stages
    assert stages.index("Business") < stages.index("Valuation") < stages.index("Horizon")


def v_stage(verdict, name):
    return any(s.stage == name for s in verdict.chain)


# ---------- news classifier ----------

def test_news_classification_and_pressure():
    from advisor.news import NewsItem, classify, pressure

    assert classify("SEBI opens probe into accounting fraud at X")[0] == "fraud"
    assert classify("X bags ₹5,000 crore order from NHAI")[0] == "order"
    assert classify("Brokerage upgrades X, raises target price")[0] == "upgrade"
    assert classify("X profit falls 30% on weak demand")[0] == "profitfall"
    assert classify("X to consider dividend on Friday")[0] == "payout"
    assert classify("X opens new showroom in Pune")[0] == "general"

    fresh_bad = NewsItem("t", "l", "s", None, 1.0, "fraud", "Fraud", -3)
    old_bad = NewsItem("t", "l", "s", None, 13.0, "fraud", "Fraud", -3)
    assert pressure([fresh_bad])["net"] < pressure([old_bad])["net"]   # recency matters
    assert pressure([fresh_bad])["tone"] == "negative"
    assert pressure([])["tone"] == "mixed"
    assert pressure([fresh_bad])["material_count"] == 1


# ---------- book-aware conflict resolution ----------

CHEAP_SOUND = {"pe": 12, "roe": 0.19, "roce": 0.21, "debt_to_equity": 0.3,
               "interest_cover": 9}
DOWNTREND = dict(FEAT, close=80.0, rsi14=38.0, dist_52w_high=-0.28)


def test_fno_book_refuses_a_contested_trade():
    v = decide("X", DOWNTREND, CHEAP_SOUND, 72, stage=4, regime_risk_on=True,
               book="fno")
    assert v.action == "WATCH"
    assert v.conflict is not None
    assert v.conviction <= 40
    assert "expiring instrument" in v.horizon
    assert any(s.stage == "Resolution" for s in v.chain)


def test_investing_book_lets_fundamentals_decide_and_the_trend_time():
    v = decide("X", DOWNTREND, CHEAP_SOUND, 72, stage=4, regime_risk_on=True,
               book="investing")
    assert v.action == "WATCH"                     # wait for the turn, do not avoid
    assert v.conflict is not None
    assert any("business decides" in s.finding for s in v.chain)
    assert v.horizon.startswith("Long term")       # still a long-term case


def test_expensive_uptrend_is_flagged_as_momentum_not_value():
    dear = {"pe": 85, "roe": 0.14, "debt_to_equity": 0.4}
    v = decide("X", FEAT, dear, 58, stage=2, regime_risk_on=True, book="investing")
    assert v.conflict is not None and "momentum, not value" in v.conflict


def test_no_conflict_when_models_agree():
    v = decide("X", FEAT, CHEAP_SOUND, 75, stage=2, regime_risk_on=True,
               book="fno")
    assert v.conflict is None
    assert v.action in ("BUY", "ACCUMULATE")


def test_valuation_lens_outranks_a_bare_multiple():
    val = {"margin_of_safety": 0.35, "fair_value_base": 150.0, "implied_growth": 0.06}
    v = decide("X", FEAT, {"pe": 70}, 70, stage=2, regime_risk_on=True,
               valuation=val)
    finding = next(s.finding for s in v.chain if s.stage == "Valuation")
    assert "margin of safety" in finding and "+35%" in finding
    assert "already assumes" in finding             # reverse DCF surfaced


# ---------- ownership gate ----------

def test_promoter_selling_lowers_conviction_through_the_ownership_gate():
    own_bad = {"smart_money_score": 28, "flow": "distribution",
               "flags": ["promoter_selling:high", "distribution_to_retail"]}
    own_good = {"smart_money_score": 72, "flow": "accumulation", "flags": []}
    bad = decide("X", FEAT, CHEAP_SOUND, 70, stage=2, regime_risk_on=True,
                 ownership=own_bad)
    good = decide("X", FEAT, CHEAP_SOUND, 70, stage=2, regime_risk_on=True,
                  ownership=own_good)
    assert bad.conviction < good.conviction - 20
    assert any(s.stage == "Ownership" for s in bad.chain)
    assert any("promoters have been selling" in s.finding for s in bad.chain)


def test_missing_ownership_is_recorded_as_a_gap():
    v = decide("X", FEAT, CHEAP_SOUND, 70, stage=2, regime_risk_on=True)
    assert "ownership" in v.unknowns


def test_pledge_flag_is_penalised():
    pledged = decide("X", FEAT, CHEAP_SOUND, 70, stage=2, regime_risk_on=True,
                     ownership={"smart_money_score": 45, "flow": "stable",
                                "flags": ["pledge_high"]})
    clean = decide("X", FEAT, CHEAP_SOUND, 70, stage=2, regime_risk_on=True,
                   ownership={"smart_money_score": 45, "flow": "stable", "flags": []})
    assert pledged.conviction < clean.conviction
