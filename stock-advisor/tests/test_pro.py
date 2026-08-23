"""Tests for the pro-stack modules: factors, risk, walk-forward, notify."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from advisor import config, db  # noqa: E402
from tests.test_engines import make_ohlcv  # noqa: E402  (reuse synthetic OHLCV)


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(config, "BHAVCOPY_CACHE_DIR", tmp_path / "bhav")
    db.init_db()
    yield


def _seed(symbols_specs):
    with db.connect() as conn:
        for i, (sym, sector, drift, fund) in enumerate(symbols_specs):
            conn.execute(
                "INSERT INTO stocks (symbol, industry, active, first_seen, last_seen) "
                "VALUES (?, ?, 1, '2024-01-01', '2026-01-01')", (sym, sector))
            df = make_ohlcv(n=400, drift=drift, seed=20 + i)
            conn.executemany(
                "INSERT INTO prices_eod VALUES (?,?,?,?,?,?,?,?,?)",
                [(sym, d.date().isoformat(), r.open, r.high, r.low, r.close,
                  int(r.volume), r.close, "yfinance") for d, r in df.iterrows()])
            for k, v in fund.items():
                conn.execute(
                    "INSERT INTO fundamentals VALUES (?, '2026-01-01', ?, ?, 't')",
                    (sym, k, v))


# ---------- factors ----------

def test_factor_ranks_sector_neutral_and_composites():
    from advisor.factors import hysteresis_action, rank_factors

    _seed([
        ("CHEAPQ", "IT", 0.0012, {"pe": 12, "pb": 2, "roe": 0.25, "op_margin": 0.2,
                                   "debt_to_equity": 10}),
        ("RICHJ", "IT", 0.0002, {"pe": 80, "pb": 12, "roe": 0.04, "op_margin": 0.03,
                                  "debt_to_equity": 200}),
        ("BANKA", "Banks", 0.0008, {"pe": 15, "pb": 1.5, "roe": 0.15,
                                     "op_margin": 0.25, "debt_to_equity": 90}),
    ])
    table = rank_factors()
    assert set(table.index) == {"CHEAPQ", "RICHJ", "BANKA"}
    # cheap+quality+momentum beats rich junk on every composite
    assert table.loc["CHEAPQ", "investing_score"] > table.loc["RICHJ", "investing_score"]
    assert table.loc["CHEAPQ", "trading_score"] > table.loc["RICHJ", "trading_score"]
    assert table["investing_pct"].between(0, 1).all()

    # hysteresis: held names survive mid-rank; exit only below 40th pct
    assert hysteresis_action(0.55, held=True) == "HOLD"
    assert hysteresis_action(0.35, held=True) == "EXIT"
    assert hysteresis_action(0.85, held=False) == "CANDIDATE"
    assert hysteresis_action(0.55, held=False) == "IGNORE"


def test_factor_missing_data_scores_neutral():
    from advisor.factors import rank_factors

    _seed([("NODATA", "IT", 0.0008, {}),
           ("FULL", "IT", 0.0008, {"pe": 20, "pb": 3, "roe": 0.18,
                                    "op_margin": 0.15, "debt_to_equity": 30})])
    t = rank_factors()
    assert "NODATA" in t.index          # missing fundamentals ≠ dropped
    assert t.loc["NODATA", "value"] == 0  # neutral, not penalized or rewarded


# ---------- risk ----------

def _rand_returns(cols=6, n=500, seed=5, corr=0.3):
    rng = np.random.default_rng(seed)
    common = rng.normal(0, 0.01, n)
    data = {f"S{i}": corr * common + (1 - corr) * rng.normal(0.0003, 0.012, n)
            for i in range(cols)}
    return pd.DataFrame(data, index=pd.bdate_range("2024-01-01", periods=n))


def test_shrink_cov_properties():
    from advisor.risk import shrink_cov

    rts = _rand_returns()
    S = shrink_cov(rts)
    vals = np.linalg.eigvalsh(S.values)
    assert (vals > -1e-12).all()                       # PSD
    raw = rts.cov()
    # diagonal (variances) preserved by constant-correlation target
    assert np.allclose(np.diag(S.values), np.diag(raw.values), rtol=1e-6)
    # off-diagonals pulled toward the average — dispersion shrinks
    off = ~np.eye(len(S), dtype=bool)
    assert S.values[off].std() < raw.values[off].std()


def test_var_cvar_and_stress():
    from advisor.risk import portfolio_var, stress_test, correlation_diagnostics

    rts = _rand_returns()
    w = {c: 1 / 6 for c in rts.columns}
    v = portfolio_var(w, rts)
    assert 0 < v["var_parametric"] < 0.5
    assert 0 < v["var_historical"] < 0.5
    assert v["cvar_historical"] >= v["var_historical"]   # ES beyond VaR, always

    st = stress_test(w, rts)
    assert st["covid_2020_crash"] <= -0.30 * 1.0 + 1e-9  # no diversification credit
    assert "worst_realized_month_in_data" in st

    diag = correlation_diagnostics(_rand_returns(corr=0.9))
    assert diag["diversification_illusion"] is True


def test_inverse_vol_weights_sum_and_order():
    from advisor.risk import inverse_vol_weights

    rng = np.random.default_rng(1)
    rts = pd.DataFrame({"CALM": rng.normal(0, 0.005, 300),
                        "WILD": rng.normal(0, 0.03, 300)})
    w = inverse_vol_weights(rts)
    assert abs(sum(w.values()) - 1) < 1e-6
    assert w["CALM"] > w["WILD"]


# ---------- walk-forward ----------

def test_walk_forward_folds_and_verdict():
    from advisor.walkforward import walk_forward

    prices = {f"S{i}": make_ohlcv(n=900, drift=0.001, seed=i, vol=0.009,
                                  breakout_at=500) for i in range(3)}
    res = walk_forward(prices, n_folds=3)
    assert len(res["folds"]) == 3
    assert res["verdict"].split(":")[0] in ("ROBUST", "MIXED", "FAILED")
    # folds are sequential, non-overlapping
    starts = [f["start"] for f in res["folds"]]
    assert starts == sorted(starts)

    tiny = {"X": make_ohlcv(n=300)}
    assert walk_forward(tiny)["folds"] == []


# ---------- notify ----------

def test_notify_requires_env_and_chunks(monkeypatch):
    from advisor import notify

    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    with pytest.raises(RuntimeError, match="TELEGRAM_BOT_TOKEN"):
        notify.send_telegram("hi")

    sent = []

    class FakeResp:
        def raise_for_status(self): pass

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "c")
    monkeypatch.setattr(notify.requests, "post",
                        lambda url, json, timeout: sent.append(json) or FakeResp())
    n = notify.send_telegram("x" * 9000)   # 9000 chars → 3 chunks of ≤4000
    assert n == 3 and len(sent) == 3
    assert all(len(m["text"]) <= 4000 for m in sent)
