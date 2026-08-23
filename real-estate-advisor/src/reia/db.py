"""SQLite schema: events (the public-record timeline), corridors, scores, parcels."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    fetched_at  TEXT NOT NULL,
    source      TEXT NOT NULL,
    region      TEXT,
    url         TEXT,
    title       TEXT NOT NULL,
    body        TEXT,
    categories  TEXT,            -- comma-separated (rule-based classifier)
    corridors   TEXT,            -- comma-separated corridor slugs matched
    ai_json     TEXT,            -- optional Claude enrichment (severity, stage hint)
    UNIQUE (source, title)       -- dedupe re-fetches
);

CREATE TABLE IF NOT EXISTS corridors (
    slug      TEXT PRIMARY KEY,
    name      TEXT NOT NULL,
    state     TEXT,
    keywords  TEXT NOT NULL,     -- comma-separated match terms
    -- analyst-maintained inputs for the scoring template (knowledge 01):
    jobs_anchor        REAL DEFAULT 0,   -- 0-1: committed jobs within 15km
    connectivity_delta REAL DEFAULT 0,   -- 0-1: funded travel-time improvement
    policy_persistence REAL DEFAULT 0,   -- 0-1: survives govt change?
    supply_constraint  REAL DEFAULT 0,   -- 0-1: geographic/regulatory scarcity
    stage              TEXT DEFAULT 'A', -- A|B|C|D (entry-timing, knowledge 01)
    notes     TEXT
);

CREATE TABLE IF NOT EXISTS corridor_scores (
    slug     TEXT NOT NULL,
    scored_at TEXT NOT NULL,
    score    REAL NOT NULL,
    event_momentum REAL,         -- events/90d vs prior 90d
    breakdown TEXT,              -- json of components
    PRIMARY KEY (slug, scored_at)
);

CREATE TABLE IF NOT EXISTS parcels (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    label      TEXT NOT NULL,    -- human name, e.g. 'Thullur 2.5ac'
    corridor   TEXT,             -- corridor slug
    state      TEXT,
    survey_no  TEXT,
    extent_acres REAL,
    asking_price REAL,
    guidance_value REAL,         -- registration dept value for the same extent
    checklist_json TEXT,         -- answers to legal checklist
    verdict    TEXT,             -- CLEAR_PENDING_LAWYER | RESOLVE_FIRST | VETO
    report     TEXT
);
"""


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    config.ensure_dirs()
    conn = sqlite3.connect(db_path or config.DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db(db_path: Path | None = None) -> None:
    with connect(db_path) as conn:
        conn.executescript(SCHEMA)
        for c in config.SEED_CORRIDORS:
            conn.execute(
                "INSERT OR IGNORE INTO corridors (slug, name, state, keywords) "
                "VALUES (?, ?, ?, ?)",
                (c["slug"], c["name"], c["state"], ",".join(c["keywords"])))
