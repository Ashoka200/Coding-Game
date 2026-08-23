"""Portfolio tracker: holdings, valuation, heat, concentration, stop alerts (mod 03/04)."""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from . import db

HOLDINGS_SCHEMA = """
CREATE TABLE IF NOT EXISTS holdings (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol    TEXT NOT NULL,
    book      TEXT NOT NULL,             -- 'investing' | 'trading'
    qty       INTEGER NOT NULL,
    avg_cost  REAL NOT NULL,
    stop      REAL,
    opened_at TEXT NOT NULL,
    closed_at TEXT,
    exit_price REAL
);
"""


def _ensure(conn) -> None:
    conn.executescript(HOLDINGS_SCHEMA)


def add_holding(symbol: str, book: str, qty: int, avg_cost: float,
                stop: float | None = None) -> int:
    assert book in ("investing", "trading")
    with db.connect() as conn:
        _ensure(conn)
        cur = conn.execute(
            "INSERT INTO holdings (symbol, book, qty, avg_cost, stop, opened_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (symbol, book, qty, avg_cost, stop,
             datetime.now(timezone.utc).isoformat(timespec="seconds")))
        return int(cur.lastrowid)


def close_holding(holding_id: int, exit_price: float) -> None:
    with db.connect() as conn:
        _ensure(conn)
        n = conn.execute(
            "UPDATE holdings SET closed_at=?, exit_price=? WHERE id=? AND closed_at IS NULL",
            (datetime.now(timezone.utc).isoformat(timespec="seconds"),
             exit_price, holding_id)).rowcount
        if n == 0:
            raise ValueError(f"no open holding {holding_id}")


def _latest_closes(conn, symbols: list[str]) -> dict[str, float]:
    if not symbols:
        return {}
    q = ("SELECT symbol, close FROM prices_eod WHERE source='yfinance' "
         f"AND symbol IN ({','.join('?' * len(symbols))}) "
         "AND (symbol, date) IN (SELECT symbol, MAX(date) FROM prices_eod "
         "WHERE source='yfinance' GROUP BY symbol)")
    return dict(conn.execute(q, symbols).fetchall())


def snapshot(cash: float = 0.0) -> dict:
    """Valuation, weights, open heat, sector concentration, stop breaches."""
    with db.connect() as conn:
        _ensure(conn)
        hold = pd.read_sql_query(
            "SELECT h.*, s.industry FROM holdings h LEFT JOIN stocks s USING (symbol) "
            "WHERE h.closed_at IS NULL", conn)
        closes = _latest_closes(conn, hold["symbol"].tolist())

    if hold.empty:
        return {"positions": hold, "total_value": cash, "alerts": [], "heat_pct": 0.0,
                "sector_weights": {}}

    hold["last"] = hold["symbol"].map(closes)
    hold["value"] = hold["qty"] * hold["last"]
    hold["pnl_pct"] = hold["last"] / hold["avg_cost"] - 1
    total = float(hold["value"].sum()) + cash
    hold["weight"] = hold["value"] / total

    alerts = []
    for _, r in hold.iterrows():
        if pd.isna(r["last"]):
            alerts.append(f"{r['symbol']}: no price data")
            continue
        if r["stop"] and r["last"] <= r["stop"]:
            alerts.append(f"{r['symbol']}: CLOSED BELOW STOP {r['stop']:.2f} (last {r['last']:.2f})")
        if r["weight"] > 0.15:
            alerts.append(f"{r['symbol']}: weight {r['weight']:.1%} > 15% trim rule")
        if r["book"] == "investing" and r["pnl_pct"] < -0.20:
            alerts.append(f"{r['symbol']}: -20% forced thesis review (module 04)")

    trading = hold[hold["book"] == "trading"]
    heat = float(((trading["last"] - trading["stop"]).clip(lower=0)
                  * trading["qty"]).sum() / total) if not trading.empty else 0.0
    if heat > 0.05:
        alerts.append(f"portfolio heat {heat:.1%} > 5% cap — no new trades")

    sector = hold.groupby("industry")["weight"].sum().sort_values(ascending=False)
    for ind, w in sector.items():
        if w > 0.25:
            alerts.append(f"sector {ind}: {w:.1%} > 25% cap")

    return {"positions": hold, "total_value": round(total, 2), "alerts": alerts,
            "heat_pct": round(heat, 4), "sector_weights": sector.round(4).to_dict()}
