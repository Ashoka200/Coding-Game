"""Decision journal — the system's accumulating experience.

Every suggestion is logged BEFORE outcomes are known (pre-commitment, module 08).
Outcomes close the loop; `calibration_report` turns history into evidence that
tunes future conviction weights.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pandas as pd

from . import db


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def log_decision(symbol: str, book: str, action: str, conviction: int,
                 thesis: str, entry_low: float | None = None,
                 entry_high: float | None = None, stop: float | None = None,
                 target1: float | None = None, target2: float | None = None,
                 size_pct: float | None = None, engine_scores: dict | None = None) -> int:
    assert book in ("investing", "trading")
    assert action in ("buy", "sell", "trim", "avoid", "watch")
    with db.connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO journal_decisions
                (created_at, symbol, book, action, conviction, entry_low, entry_high,
                 stop, target1, target2, size_pct, thesis, engine_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (_now(), symbol, book, action, conviction, entry_low, entry_high,
             stop, target1, target2, size_pct, thesis,
             json.dumps(engine_scores or {})),
        )
        return int(cur.lastrowid)


def close_decision(decision_id: int, exit_price: float, outcome: str,
                   notes: str = "") -> float | None:
    """Record the outcome; returns realized R multiple where computable."""
    with db.connect() as conn:
        row = conn.execute(
            "SELECT entry_low, entry_high, stop FROM journal_decisions WHERE id=?",
            (decision_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"no decision {decision_id}")
        entry_low, entry_high, stop = row
        r_multiple = None
        if entry_low is not None and stop is not None:
            entry = (entry_low + (entry_high or entry_low)) / 2
            risk = entry - stop
            if risk > 0:
                r_multiple = (exit_price - entry) / risk
        conn.execute(
            """
            INSERT INTO journal_outcomes (decision_id, closed_at, exit_price,
                                          r_multiple, outcome, notes)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (decision_id, _now(), exit_price, r_multiple, outcome, notes),
        )
        conn.execute(
            "UPDATE journal_decisions SET status='closed' WHERE id=?", (decision_id,)
        )
    return r_multiple


def calibration_report() -> pd.DataFrame:
    """Hit rate and average R by conviction band — the evidence loop.

    If 80-conviction calls don't beat 50-conviction calls over time, the scoring
    weights are miscalibrated and must be revisited (quarterly review, module 01).
    """
    with db.connect() as conn:
        df = pd.read_sql_query(
            """
            SELECT d.conviction, d.book, o.r_multiple
            FROM journal_decisions d JOIN journal_outcomes o ON o.decision_id = d.id
            WHERE o.r_multiple IS NOT NULL
            """,
            conn,
        )
    if df.empty:
        return df
    df["band"] = pd.cut(df["conviction"], bins=[0, 40, 60, 80, 100],
                        labels=["<=40", "41-60", "61-80", "81-100"])
    return df.groupby(["book", "band"], observed=True)["r_multiple"].agg(
        n="count", hit_rate=lambda s: (s > 0).mean(), avg_r="mean"
    ).reset_index()
