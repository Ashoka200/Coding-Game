"""Valuation engine: the maths must be right, and missing inputs must produce
gaps rather than plausible-looking numbers."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from advisor.valuation import (  # noqa: E402
    TERMINAL_GROWTH, cost_of_equity, dcf, implied_growth, relative_value,
    sum_of_parts, value_company, wacc,
)


def test_cost_of_capital_reflects_risk():
    assert cost_of_equity(1.0) == pytest.approx(0.125)
    assert cost_of_equity(1.5) > cost_of_equity(0.8)        # riskier costs more
    # debt is cheaper after tax, so leverage lowers WACC
    all_equity = wacc(equity_value=1000, debt=0, beta=1.0)
    levered = wacc(equity_value=1000, debt=1000, beta=1.0)
    assert levered < all_equity
    assert wacc(equity_value=0, debt=500, beta=1.0) == cost_of_equity(1.0)  # no structure known


def test_dcf_behaves_like_a_dcf():
    base, detail = dcf(fcff=100, growth=0.10, discount=0.12, shares=100)
    assert base > 0
    # a higher discount rate must lower the value
    higher, _ = dcf(fcff=100, growth=0.10, discount=0.15, shares=100)
    assert higher < base
    # more growth must raise it
    faster, _ = dcf(fcff=100, growth=0.15, discount=0.12, shares=100)
    assert faster > base
    # net debt is subtracted from equity holders
    indebted, _ = dcf(fcff=100, growth=0.10, discount=0.12, shares=100, net_debt=500)
    assert indebted == pytest.approx(base - 5.0)
    # the terminal share is reported so an over-reliant model can be flagged
    assert 0 < detail["terminal_share"] < 1
    assert detail["pv_explicit"] + detail["pv_terminal"] == pytest.approx(
        detail["enterprise_value"])


def test_growth_fade_is_conservative():
    faded, _ = dcf(100, 0.25, 0.12, 100, fade=True)
    flat, _ = dcf(100, 0.25, 0.12, 100, fade=False)
    assert faded < flat          # holding 25% flat for a decade flatters the business


def test_dcf_rejects_impossible_assumptions():
    with pytest.raises(ValueError):
        dcf(100, 0.10, TERMINAL_GROWTH - 0.01, 100)   # discount below terminal growth
    with pytest.raises(ValueError):
        dcf(100, 0.10, 0.12, 0)                        # no shares


def test_reverse_dcf_recovers_the_growth_that_made_the_price():
    price, _ = dcf(fcff=100, growth=0.12, discount=0.13, shares=100)
    recovered = implied_growth(price, fcff=100, discount=0.13, shares=100)
    assert recovered == pytest.approx(0.12, abs=0.005)


def test_reverse_dcf_admits_when_no_sane_growth_explains_the_price():
    # a wildly high price cannot be explained inside a sane growth band
    assert implied_growth(1e9, fcff=100, discount=0.13, shares=100) is None
    assert implied_growth(0, fcff=100, discount=0.13, shares=100) is None
    assert implied_growth(100, fcff=0, discount=0.13, shares=100) is None


def test_relative_and_sum_of_parts():
    lens = relative_value(eps=50, book_value=200, sector_pe=20, sector_pb=3)
    assert lens.value_per_share == pytest.approx((50 * 20 + 200 * 3) / 2)
    assert relative_value(None, None, 20, 3).value_per_share is None   # no inputs, no number

    sotp = sum_of_parts(
        [{"name": "retail", "metric_value": 1000, "multiple": 20, "basis": "EBITDA"},
         {"name": "telecom", "metric_value": 800, "multiple": 12, "basis": "EBITDA"},
         {"name": "new energy", "metric_value": None, "multiple": None}],
        net_debt=5000, shares=1000)
    assert sotp.value_per_share == pytest.approx((1000 * 20 + 800 * 12 - 5000) / 1000)
    assert any("new energy" in c for c in sotp.caveats)   # the skipped part is named


def test_missing_inputs_produce_gaps_not_guesses():
    v = value_company("NODATA", price=100, inputs={})
    assert v.fair_value_base is None
    assert v.verdict is None
    fields = {u["field"] for u in v.unknowns}
    assert "fcff" in fields and "shares" in fields
    assert any("gap, not a view" in c for c in v.caveats)


def test_full_valuation_produces_a_range_and_a_margin_of_safety():
    v = value_company("TESTCO", price=100, inputs={
        "fcff": 1000, "shares": 100, "net_debt": 2000, "beta": 1.0,
        "growth": 0.12, "eps": 12, "book_value": 60,
        "sector_pe": 18, "sector_pb": 2.5, "total_debt": 3000,
    })
    assert v.fair_value_low < v.fair_value_base < v.fair_value_high
    assert v.margin_of_safety is not None
    assert v.verdict in ("materially cheap", "cheap", "around fair",
                         "expensive", "priced for perfection")
    assert v.implied_growth is not None
    assert any("already assuming" in c for c in v.caveats)
    names = {l.name for l in v.lenses}
    assert {"dcf", "relative"} <= names


def test_terminal_heavy_valuations_are_flagged():
    # low starting growth, long horizon: terminal value dominates
    v = value_company("SLOW", price=50, inputs={
        "fcff": 100, "shares": 100, "growth": 0.02, "beta": 1.0})
    dcf_lens = next(l for l in v.lenses if l.name == "dcf")
    if dcf_lens.detail["terminal_share"] > 0.60:
        assert any("terminal assumption" in c for c in dcf_lens.caveats)
