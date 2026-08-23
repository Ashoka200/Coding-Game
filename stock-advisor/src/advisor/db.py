"""SQLite schema and connection helpers.

Design notes:
- `stocks` keeps first_seen/last_seen and is never deleted from → the universe is
  survivorship-free by construction (delisted names stay, flagged inactive).
- `fundamentals` is a point-in-time store: every value carries as_of_date (when it
  became known), so backtests can query "what was known then", not restated data.
- `journal_*` is the decision journal — the system's accumulating experience.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS stocks (
    symbol      TEXT PRIMARY KEY,       -- NSE symbol, e.g. RELIANCE
    name        TEXT,
    isin        TEXT,
    industry    TEXT,
    index_name  TEXT,                   -- e.g. NIFTY 500
    active      INTEGER DEFAULT 1,      -- 0 once it drops out of the universe
    first_seen  TEXT NOT NULL,          -- ISO date
    last_seen   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS prices_eod (
    symbol   TEXT NOT NULL,
    date     TEXT NOT NULL,             -- ISO date
    open     REAL, high REAL, low REAL, close REAL,
    volume   INTEGER,
    adj_close REAL,                     -- split/dividend adjusted (yfinance)
    source   TEXT NOT NULL,             -- 'yfinance' | 'bhavcopy'
    PRIMARY KEY (symbol, date, source)
);
CREATE INDEX IF NOT EXISTS idx_prices_symbol ON prices_eod (symbol, date);

CREATE TABLE IF NOT EXISTS fundamentals (
    symbol     TEXT NOT NULL,
    as_of_date TEXT NOT NULL,           -- date this value became known (point-in-time)
    field      TEXT NOT NULL,           -- e.g. 'roe', 'debt_to_equity', 'market_cap'
    value      REAL,
    source     TEXT NOT NULL,
    PRIMARY KEY (symbol, as_of_date, field, source)
);

CREATE TABLE IF NOT EXISTS corporate_actions (
    symbol   TEXT NOT NULL,
    ex_date  TEXT NOT NULL,
    kind     TEXT NOT NULL,             -- 'dividend' | 'split' | 'bonus' | ...
    detail   TEXT,
    PRIMARY KEY (symbol, ex_date, kind)
);

CREATE TABLE IF NOT EXISTS refresh_log (
    job      TEXT NOT NULL,             -- 'universe' | 'prices' | 'bhavcopy' | ...
    run_at   TEXT NOT NULL,             -- ISO timestamp
    ok       INTEGER NOT NULL,
    detail   TEXT
);

-- Decision journal: every suggestion, logged before outcomes are known.
CREATE TABLE IF NOT EXISTS journal_decisions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at  TEXT NOT NULL,
    symbol      TEXT NOT NULL,
    book        TEXT NOT NULL,          -- 'investing' | 'trading'
    action      TEXT NOT NULL,          -- 'buy' | 'sell' | 'trim' | 'avoid' | 'watch'
    conviction  INTEGER,                -- 0-100 at decision time
    entry_low   REAL, entry_high REAL,
    stop        REAL,
    target1     REAL, target2 REAL,
    size_pct    REAL,                   -- suggested % of equity
    thesis      TEXT,                   -- one-paragraph rationale
    engine_json TEXT,                   -- full engine scores snapshot (audit trail)
    status      TEXT NOT NULL DEFAULT 'open'  -- 'open' | 'closed' | 'expired'
);

CREATE TABLE IF NOT EXISTS journal_outcomes (
    decision_id INTEGER PRIMARY KEY REFERENCES journal_decisions(id),
    closed_at   TEXT NOT NULL,
    exit_price  REAL,
    r_multiple  REAL,                   -- realized (exit-entry)/(entry-stop)
    outcome     TEXT,                   -- 'target' | 'stop' | 'time' | 'manual'
    notes       TEXT
);
"""


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    config.ensure_dirs()
    conn = sqlite3.connect(db_path or config.DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(db_path: Path | None = None) -> None:
    with connect(db_path) as conn:
        conn.executescript(SCHEMA)


def log_refresh(conn: sqlite3.Connection, job: str, ok: bool, detail: str = "") -> None:
    from datetime import datetime, timezone

    conn.execute(
        "INSERT INTO refresh_log (job, run_at, ok, detail) VALUES (?, ?, ?, ?)",
        (job, datetime.now(timezone.utc).isoformat(timespec="seconds"), int(ok), detail),
    )
