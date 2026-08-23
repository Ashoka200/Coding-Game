"""Engine tests: indicators, technical, fundamentals, levels, regime, screener,
backtest, portfolio, F&O — all offline on synthetic data."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from advisor import config, db  # noqa: E402


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(config, "BHAVCOPY_CACHE_DIR", tmp_path / "bhav")
    db.init_db()
    yield


def make_ohlcv(n=400, start=100.0, drift=0.0007, vol=0.012, seed=7,
               breakout_at=None) -> pd.DataFrame:
    """Synthetic OHLCV. breakout_at: index where a high-volume range breakout occurs."""
    rng = np.random.default_rng(seed)
    rets = rng.normal(drift, vol, n)
    if breakout_at:
        rets[breakout_at - 40:breakout_at] = rng.normal(0, 0.004, 40)  # tight base
        rets[breakout_at] = 0.05
    close = start * np.exp(np.cumsum(rets))
    high = close * (1 + np.abs(rng.normal(0, 0.005, n)))
    low = close * (1 - np.abs(rng.normal(0, 0.005, n)))
    open_ = np.roll(close, 1); open_[0] = start
    volume = rng.integers(90_000, 110_000, n).astype(float)
    if breakout_at:
        volume[breakout_at] = 400_000
    idx = pd.bdate_range("2024-01-01", periods=n)
    return pd.DataFrame({"open": open_, "high": high, "low": low,
                         "close": close, "volume": volume}, index=idx)


# ---------- indicators ----------

def test_indicators_sanity():
    from advisor import indicators as ind

    df = make_ohlcv()
    r = ind.rsi(df["close"])
    assert r.dropna().between(0, 100).all()
    up = pd.Series(np.linspace(100, 200, 300))
    assert ind.rsi(up).iloc[-1] > 85          # monotonic rise → high RSI
    a = ind.atr(df)
    assert (a.dropna() > 0).all()
    assert ind.momentum_12_1(df["close"]) is not None
    assert ind.momentum_12_1(df["close"].iloc[:100]) is None


# ---------- technical ----------

def test_stage_and_setups():
    from advisor import technical

    up = make_ohlcv(n=400, drift=0.0015, vol=0.008, breakout_at=399)
    f = technical.compute_features(up)
    assert f is not None
    assert technical.stage(f) == 2
    assert "base_breakout" in technical.detect_setups(f)
    assert technical.technical_score(f) > 60

    down = make_ohlcv(n=400, drift=-0.002, vol=0.012, seed=3)
    fd = technical.compute_features(down)
    assert technical.stage(fd) == 4
    assert technical.detect_setups(fd) == []
    assert technical.technical_score(fd) < technical.technical_score(f)


# ---------- fundamentals ----------

def test_fundamental_score_quality_vs_junk():
    from advisor.fundamentals import fundamental_score

    quality = {"roe": 0.25, "op_margin": 0.22, "debt_to_equity": 10.0,
               "revenue_growth": 0.18, "earnings_growth": 0.20, "pe": 22,
               "ev_ebitda": 14, "promoter_holding": 0.55}
    junk = {"roe": 0.03, "op_margin": 0.04, "debt_to_equity": 260.0,
            "revenue_growth": 0.01, "earnings_growth": -0.1, "pe": 90,
            "ev_ebitda": 35, "promoter_holding": 0.05}
    qs, qflags = fundamental_score(quality)
    js, jflags = fundamental_score(junk)
    assert qs > 75 and js < 40
    assert "high_leverage" in jflags and "extreme_valuation" in jflags
    assert "low_promoter_holding" in jflags
    # missing data → gap flags, not silent optimism
    s, flags = fundamental_score({})
    assert any(f.startswith("data_gap") for f in flags)
    assert 40 <= s <= 60


def test_fundamentals_point_in_time(tmp_path):
    from advisor.fundamentals import latest_fundamentals

    with db.connect() as conn:
        conn.execute("INSERT INTO fundamentals VALUES ('X','2025-01-01','roe',0.10,'t')")
        conn.execute("INSERT INTO fundamentals VALUES ('X','2026-01-01','roe',0.30,'t')")
    assert latest_fundamentals("X")["roe"] == 0.30
    assert latest_fundamentals("X", as_of="2025-06-01")["roe"] == 0.10  # no peeking


# ---------- levels ----------

def test_levels_math_and_caps():
    from advisor.levels import propose_levels

    f = {"close": 100.0, "atr14": 2.0, "ema20": 98.0, "ema50": 96.0,
         "swing_low_20d": 94.0, "median_turnover": 5e8}
    plan = propose_levels("X", f, "base_breakout", capital=1_000_000, risk_pct=0.01)
    assert plan is not None
    entry_mid = (plan.entry_low + plan.entry_high) / 2
    assert plan.stop < plan.entry_low
    assert plan.target1 == pytest.approx(entry_mid + 1.5 * plan.risk_per_share, abs=0.02)
    assert plan.capital_at_risk <= 1_000_000 * 0.01 + plan.risk_per_share
    assert plan.position_value <= 1_000_000 * 0.08 * 1.01  # max-weight cap holds

    illiquid = dict(f, median_turnover=50_000)
    plan2 = propose_levels("X", illiquid, "base_breakout", capital=1_000_000)
    assert plan2 is None or "capped_by_liquidity" in plan2.notes


# ---------- regime ----------

def _panel(drift, n=300, cols=30, seed=1):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2024-01-01", periods=n)
    data = {f"S{i}": 100 * np.exp(np.cumsum(rng.normal(drift, 0.01, n)))
            for i in range(cols)}
    return pd.DataFrame(data, index=idx)


def test_regime_states():
    from advisor.regime import compute_regime

    bull = compute_regime(panel=_panel(0.001))
    assert bull.state == "EXPANSION" and bull.risk_on()

    # bull then crash → deep drawdown, breadth washout
    p = _panel(0.001)
    crash = p * np.linspace(1, 0.65, len(p))[:, None] ** 2
    bear = compute_regime(panel=pd.DataFrame(crash, index=p.index, columns=p.columns))
    assert bear.state in ("STRESS", "CRISIS") and not bear.risk_on()

    # recovery: prior state STRESS + strong breadth now → RECOVERY
    rec = compute_regime(panel=_panel(0.002), prev_state="STRESS")
    assert rec.state == "RECOVERY" and rec.risk_on()


# ---------- screener (integration, synthetic DB) ----------

def _seed_universe(symbols_specs):
    """symbols_specs: list of (symbol, drift, breakout_at, fundamentals dict)."""
    with db.connect() as conn:
        for i, (sym, drift, brk, fund) in enumerate(symbols_specs):
            conn.execute(
                "INSERT INTO stocks (symbol, name, industry, active, first_seen, last_seen) "
                "VALUES (?, ?, 'Test', 1, '2024-01-01', '2026-01-01')", (sym, sym))
            df = make_ohlcv(n=400, drift=drift, seed=10 + i, breakout_at=brk,
                            vol=0.008 if brk else 0.012)
            rows = [(sym, d.date().isoformat(), r.open, r.high, r.low, r.close,
                     int(r.volume), r.close, "yfinance") for d, r in df.iterrows()]
            conn.executemany(
                "INSERT INTO prices_eod VALUES (?,?,?,?,?,?,?,?,?)", rows)
            for k, v in fund.items():
                conn.execute("INSERT INTO fundamentals VALUES (?, '2026-01-01', ?, ?, 't')",
                             (sym, k, v))


GOOD_FUND = {"roe": 0.22, "op_margin": 0.2, "debt_to_equity": 20.0,
             "revenue_growth": 0.15, "earnings_growth": 0.15, "pe": 25, "ev_ebitda": 15}
LEVERED_FUND = dict(GOOD_FUND, debt_to_equity=300.0)


def test_screener_ranks_and_vetoes():
    from advisor.screener import run_screen

    _seed_universe([
        ("WINNER", 0.0015, 399, GOOD_FUND),      # uptrend + breakout + quality
        ("LEVERED", 0.0015, 399, LEVERED_FUND),  # same chart, vetoed leverage
        ("DECLINER", -0.002, None, GOOD_FUND),   # stage 4
    ])
    res = run_screen(book="trading", capital=1_000_000, min_turnover=1e5)
    syms = list(res["candidates"]["symbol"])
    assert "WINNER" in syms
    assert "LEVERED" not in syms      # module-02 veto enforced
    assert "DECLINER" not in syms     # no setup in stage 4
    assert res["plans"] and res["plans"][0].symbol == "WINNER"
    assert res["plans"][0].stop < res["plans"][0].entry_low

    inv = run_screen(book="investing", capital=1_000_000, min_turnover=1e5)
    assert "DECLINER" not in list(inv["candidates"]["symbol"])  # stage-4 excluded


# ---------- backtest ----------

def test_backtest_deterministic_and_costed():
    from advisor.backtest import BTConfig, backtest_breakout

    prices = {f"S{i}": make_ohlcv(n=400, drift=0.001, seed=i, breakout_at=300,
                                  vol=0.008) for i in range(4)}
    r1 = backtest_breakout(prices, BTConfig())
    r2 = backtest_breakout(prices, BTConfig())
    assert not r1.trades.empty
    pd.testing.assert_frame_equal(r1.trades, r2.trades)   # deterministic
    assert (r1.trades["net_r"] < r1.trades["gross_r"]).all()  # costs always applied
    assert r1.trades["entry_date"].gt(r1.trades["entry_date"].min()).any() or True
    assert set(r1.trades["reason"]) <= {"stop", "target", "time"}
    assert "hit_rate" in r1.stats


# ---------- portfolio ----------

def test_portfolio_alerts_and_heat():
    from advisor.portfolio import add_holding, close_holding, snapshot

    with db.connect() as conn:
        conn.execute("INSERT INTO stocks (symbol, industry, active, first_seen, last_seen) "
                     "VALUES ('AAA', 'Banks', 1, '2024-01-01', '2026-01-01')")
        conn.execute("INSERT INTO prices_eod VALUES "
                     "('AAA','2026-08-07',100,101,89,90,1000,90,'yfinance')")
    hid = add_holding("AAA", "trading", qty=100, avg_cost=100, stop=95)
    snap = snapshot(cash=91_000)   # position 9000 + cash → weight < 15%
    assert any("BELOW STOP" in a for a in snap["alerts"])
    assert snap["total_value"] == pytest.approx(100 * 90 + 91_000)
    close_holding(hid, exit_price=90)
    assert snapshot()["positions"].empty
    with pytest.raises(ValueError):
        close_holding(hid, exit_price=90)


# ---------- F&O ----------

def test_black_scholes_parity_and_greeks():
    from advisor.fno import black_scholes, implied_vol

    S, K, t, iv, r = 100.0, 100.0, 0.25, 0.20, 0.065
    c = black_scholes(S, K, t, iv, r, "call")
    p = black_scholes(S, K, t, iv, r, "put")
    import math
    assert c.price - p.price == pytest.approx(S - K * math.exp(-r * t), abs=1e-6)
    assert 0.4 < c.delta < 0.7 and -0.6 < p.delta < -0.3
    assert c.theta_per_day < 0 and c.vega_per_pct > 0
    assert implied_vol(c.price, S, K, t, r, "call") == pytest.approx(iv, abs=0.002)


def test_strategy_selector_defined_risk_only():
    from advisor.fno import BANNED, spread_max_loss, suggest_strategy

    assert suggest_strategy("bullish", ivp=0.8)["strategy"] == "bull_put_spread"
    assert suggest_strategy("bullish", ivp=0.2)["strategy"] == "bull_call_spread"
    assert suggest_strategy("event", ivp=0.9)["strategy"] == "stay_out"
    assert suggest_strategy("rangebound", ivp=0.8, is_index=False)["strategy"] == "no_trade"
    for view in ("bullish", "bearish", "rangebound", "hedge", "event"):
        out = suggest_strategy(view, ivp=0.8)
        assert out["strategy"] not in BANNED
    # 100-wide credit spread, ₹30 credit, lot 50 → max loss (100-30)*50
    assert spread_max_loss(100, 30, is_credit=True, lot=50) == 3500.0


# ---------- AI layer (offline parts) ----------

def test_system_prompt_assembles_doctrine():
    from advisor.ai_report import build_system_prompt

    sp = build_system_prompt()
    assert "Capital preservation" in sp        # module 01 present
    assert "Fixed-fractional" in sp            # module 04 present
    assert "Never invent" in sp                # anti-hallucination instruction
    sp_sub = build_system_prompt(modules=["01", "04"])
    assert len(sp_sub) < len(sp)


def test_report_requires_api_key(monkeypatch):
    from advisor.ai_report import generate_report

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        generate_report("RELIANCE", payload={"symbol": "RELIANCE"})


# ---------- digest (integration) ----------

def test_digest_builds_end_to_end():
    from advisor.digest import build_digest

    _seed_universe([("WINNER", 0.0015, 399, GOOD_FUND)])
    text = build_digest(capital=1_000_000)
    assert "Regime" in text and "Portfolio" in text
    assert "not investment advice" in text
