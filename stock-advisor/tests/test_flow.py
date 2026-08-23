"""Tests for the amount → plan → approve → orders flow."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from advisor import config, db  # noqa: E402
from tests.test_engines import make_ohlcv  # noqa: E402


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(config, "BHAVCOPY_CACHE_DIR", tmp_path / "bhav")
    db.init_db()
    monkeypatch.chdir(tmp_path)
    yield


GOOD_FUND = {"roe": 0.22, "op_margin": 0.2, "debt_to_equity": 20.0,
             "revenue_growth": 0.15, "earnings_growth": 0.15, "pe": 25,
             "ev_ebitda": 15}


def _seed(specs):
    """specs: [(symbol, drift, fundamentals|None)] — ETFs pass None."""
    with db.connect() as conn:
        for i, (sym, drift, fund) in enumerate(specs):
            conn.execute(
                "INSERT INTO stocks (symbol, industry, active, first_seen, last_seen) "
                "VALUES (?, 'Test', 1, '2024-01-01', '2026-01-01')", (sym,))
            df = make_ohlcv(n=400, drift=drift, seed=30 + i, vol=0.009)
            conn.executemany(
                "INSERT INTO prices_eod VALUES (?,?,?,?,?,?,?,?,?)",
                [(sym, d.date().isoformat(), r.open, r.high, r.low, r.close,
                  int(r.volume), r.close, "yfinance") for d, r in df.iterrows()])
            for k, v in (fund or {}).items():
                conn.execute("INSERT INTO fundamentals VALUES (?, '2026-01-01', ?, ?, 't')",
                             (sym, k, v))


BULL = [("NIFTYBEES", 0.0009, None), ("JUNIORBEES", 0.0010, None),
        ("ALPHA", 0.0015, GOOD_FUND), ("BETA", 0.0014, GOOD_FUND),
        ("GAMMA", 0.0013, GOOD_FUND)]


def test_plan_allocates_and_reports_downside():
    from advisor.planner import build_plan

    _seed(BULL)
    plan = build_plan(1_000_000, "balanced")

    assert plan.plan_id is not None
    assert plan.invested <= plan.amount
    assert plan.cash_left >= 0
    core = [l for l in plan.lines if l.role == "core"]
    sat = [l for l in plan.lines if l.role == "satellite"]
    assert {l.symbol for l in core} == {"NIFTYBEES", "JUNIORBEES"}
    assert sat, "expected stock picks in a bull regime"
    # every stock pick carries a stop below its price, and quantified risk
    for l in sat:
        assert l.stop is not None and l.stop < l.price
        assert l.risk_amount == pytest.approx(l.qty * (l.price - l.stop), rel=1e-6)
    # core ≈ 60% of amount, no single stock over the profile cap
    assert 0.5 < sum(l.value for l in core) / plan.amount < 0.65
    assert all(l.value <= plan.amount * 0.08 * 1.01 for l in sat)
    assert plan.bad_month_estimate > plan.total_risk   # index risk counted too
    # the index is the core sleeve — never also sold back as a "stock pick"
    assert not ({l.symbol for l in sat} & {"NIFTYBEES", "JUNIORBEES"})
    from advisor.planner import render_plan
    assert "not investment advice" in render_plan(plan)


def test_profiles_change_the_mix():
    from advisor.planner import build_plan

    _seed(BULL)
    careful = build_plan(1_000_000, "careful")
    ambitious = build_plan(1_000_000, "ambitious")
    c_core = sum(l.value for l in careful.lines if l.role == "core")
    a_core = sum(l.value for l in ambitious.lines if l.role == "core")
    assert c_core > a_core                       # careful holds more index
    assert careful.bad_month_estimate < ambitious.bad_month_estimate


def test_risk_off_regime_holds_the_stock_sleeve_in_cash():
    from advisor.planner import build_plan

    # every name in a downtrend → regime is not risk-on
    _seed([("NIFTYBEES", -0.0025, None), ("JUNIORBEES", -0.0025, None),
           ("ALPHA", -0.003, GOOD_FUND), ("BETA", -0.003, GOOD_FUND)])
    plan = build_plan(1_000_000, "balanced")
    assert plan.regime in ("CAUTION", "STRESS", "CRISIS")
    assert not [l for l in plan.lines if l.role == "satellite"]
    assert plan.cash_left > plan.amount * 0.3
    assert any("cash" in n for n in plan.notes)


def test_minimum_amount_and_bad_profile_rejected():
    from advisor.planner import build_plan

    with pytest.raises(ValueError, match="minimum amount"):
        build_plan(5_000)
    with pytest.raises(ValueError, match="profile"):
        build_plan(500_000, "yolo")


def test_orders_require_approval_then_build():
    from advisor import broker
    from advisor.planner import approve_plan, build_plan, get_plan

    _seed(BULL)
    plan = build_plan(1_000_000, "balanced")

    # unapproved → refused, everywhere
    with pytest.raises(ValueError, match="approve it first"):
        broker.basket_summary(plan.plan_id)
    with pytest.raises(ValueError, match="approve it first"):
        broker.to_csv(plan.plan_id)

    approve_plan(plan.plan_id)
    assert get_plan(plan.plan_id)[0] == "approved"
    assert approve_plan(plan.plan_id)              # idempotent

    summary = broker.basket_summary(plan.plan_id)
    assert summary["n_orders"] == len(plan.lines)
    for o in summary["orders"]:
        assert o["transaction_type"] == "BUY"
        assert o["product"] == "CNC"               # delivery, not intraday
        assert o["quantity"] > 0
        assert o["price"] > 0                      # limit above last, fills
    line = {l.symbol: l for l in plan.lines}
    for o in summary["orders"]:
        assert o["price"] > line[o["tradingsymbol"]].price

    csv_path = broker.to_csv(plan.plan_id)
    body = Path(csv_path).read_text()
    assert "Symbol" in body and "NIFTYBEES" in body and "BUY" in body


def test_basket_form_needs_api_key_and_embeds_orders(monkeypatch):
    from advisor import broker
    from advisor.planner import approve_plan, build_plan

    _seed(BULL)
    plan = build_plan(1_000_000, "balanced")
    approve_plan(plan.plan_id)

    monkeypatch.delenv("KITE_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="KITE_API_KEY"):
        broker.basket_form_html(plan.plan_id)

    path = broker.basket_form_html(plan.plan_id, api_key="testkey123")
    doc = Path(path).read_text()
    assert broker.KITE_BASKET_URL in doc
    assert 'name="api_key" value="testkey123"' in doc
    assert "NIFTYBEES" in doc
    assert "confirm them there" in doc or "own PIN" in doc


def test_live_placement_is_gated():
    from advisor import broker
    from advisor.planner import approve_plan, build_plan

    _seed(BULL)
    plan = build_plan(1_000_000, "balanced")
    approve_plan(plan.plan_id)
    with pytest.raises(RuntimeError, match="i_understand"):
        broker.place_via_kite_connect(plan.plan_id)


def test_mark_placed_opens_holdings_with_stops():
    from advisor import broker
    from advisor.planner import approve_plan, build_plan, get_plan
    from advisor.portfolio import snapshot

    _seed(BULL)
    plan = build_plan(1_000_000, "balanced")
    approve_plan(plan.plan_id)
    broker.mark_placed(plan.plan_id)

    assert get_plan(plan.plan_id)[0] == "placed"
    pos = snapshot()["positions"]
    assert len(pos) == len(plan.lines)
    sat_syms = {l.symbol for l in plan.lines if l.role == "satellite"}
    for _, r in pos.iterrows():
        if r["symbol"] in sat_syms:
            assert r["stop"] is not None and r["stop"] > 0
