"""Offline tests: schema, journal loop, universe parsing, bhavcopy parsing.

Live-network paths (NSE/yfinance fetch) are exercised by the nightly job on the
user's machine; here they are covered via fixtures.
"""
import io
import sys
import zipfile
from datetime import date
from pathlib import Path

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


def test_schema_tables_exist():
    with db.connect() as conn:
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"stocks", "prices_eod", "fundamentals", "journal_decisions",
            "journal_outcomes", "refresh_log"} <= tables


def test_journal_full_loop_and_r_multiple():
    from advisor import journal

    did = journal.log_decision(
        symbol="TESTCO", book="trading", action="buy", conviction=75,
        thesis="base breakout with volume", entry_low=100, entry_high=102,
        stop=95, target1=110, size_pct=2.0, engine_scores={"tech": 80},
    )
    r = journal.close_decision(did, exit_price=110, outcome="target")
    # entry mid = 101, risk = 6 → R = 9/6 = 1.5
    assert r == pytest.approx(1.5)

    with db.connect() as conn:
        status = conn.execute(
            "SELECT status FROM journal_decisions WHERE id=?", (did,)).fetchone()[0]
    assert status == "closed"

    report = journal.calibration_report()
    assert len(report) == 1
    assert report.iloc[0]["hit_rate"] == 1.0


def test_journal_rejects_bad_inputs():
    from advisor import journal

    with pytest.raises(AssertionError):
        journal.log_decision("X", "gambling", "buy", 50, "no")
    with pytest.raises(ValueError):
        journal.close_decision(9999, exit_price=1.0, outcome="stop")


def test_universe_upsert_and_survivorship(monkeypatch):
    from advisor import universe

    def fake_fetch():
        return pd.DataFrame({
            "company_name": ["Alpha Ltd", "Beta Ltd"],
            "industry": ["IT", "Banks"],
            "symbol": ["ALPHA", "BETA"],
            "isin_code": ["INE1", "INE2"],
        })

    monkeypatch.setattr(universe, "fetch_nifty500", fake_fetch)
    n, dropped = universe.update_universe()
    assert (n, dropped) == (2, 0)

    # BETA drops out of the index → marked inactive, never deleted.
    def fake_fetch2():
        return fake_fetch().iloc[[0]]

    monkeypatch.setattr(universe, "fetch_nifty500", fake_fetch2)
    n, dropped = universe.update_universe()
    assert (n, dropped) == (1, 1)
    with db.connect() as conn:
        total = conn.execute("SELECT COUNT(*) FROM stocks").fetchone()[0]
        active = conn.execute("SELECT COUNT(*) FROM stocks WHERE active=1").fetchone()[0]
    assert (total, active) == (2, 1)
    assert universe.active_symbols() == ["ALPHA"]


def test_bhavcopy_parse_and_crosscheck(monkeypatch):
    from advisor.ingest import bhavcopy

    sample = pd.DataFrame({
        "TckrSymb": ["ALPHA", "BETA", "BOND1"],
        "SctySrs": ["EQ", "EQ", "GB"],
        "OpnPric": [100.0, 50.0, 99.0],
        "HghPric": [105.0, 52.0, 99.0],
        "LwPric": [99.0, 49.0, 99.0],
        "ClsPric": [104.0, 51.0, 99.0],
        "TtlTradgVol": [10000, 5000, 10],
    })
    csv_bytes = sample.to_csv(index=False).encode()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("BhavCopy_test.csv", csv_bytes)

    class FakeResp:
        status_code = 200
        content = buf.getvalue()
        def raise_for_status(self): pass

    monkeypatch.setattr(bhavcopy.requests, "get", lambda *a, **k: FakeResp())
    monkeypatch.setattr(bhavcopy.time, "sleep", lambda s: None)

    d = date(2026, 8, 7)
    rows = bhavcopy.ingest_bhavcopy(d)
    assert rows == 2  # GB series excluded

    # Insert a diverging yfinance close for ALPHA → cross_check flags it.
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO prices_eod (symbol, date, open, high, low, close, volume, adj_close, source) "
            "VALUES ('ALPHA', ?, 100, 105, 99, 110.0, 10000, 110.0, 'yfinance')",
            (d.isoformat(),),
        )
        conn.execute(
            "INSERT INTO prices_eod (symbol, date, open, high, low, close, volume, adj_close, source) "
            "VALUES ('BETA', ?, 50, 52, 49, 51.0, 5000, 51.0, 'yfinance')",
            (d.isoformat(),),
        )
    bad = bhavcopy.cross_check(d)
    assert list(bad["symbol"]) == ["ALPHA"]

    # Cache hit path: second ingest reads from disk (requests not needed).
    monkeypatch.setattr(bhavcopy.requests, "get",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no net")))
    assert bhavcopy.ingest_bhavcopy(d) == 2


def test_load_prices_roundtrip():
    from advisor.ingest.prices import load_prices

    with db.connect() as conn:
        for i, day in enumerate(["2026-08-04", "2026-08-05", "2026-08-06"]):
            conn.execute(
                "INSERT INTO prices_eod (symbol, date, open, high, low, close, volume, adj_close, source) "
                "VALUES ('ALPHA', ?, 100, 101, 99, ?, 1000, ?, 'yfinance')",
                (day, 100 + i, 100 + i),
            )
    df = load_prices("ALPHA", start="2026-08-05")
    assert len(df) == 2
    assert df["close"].tolist() == [101, 102]
