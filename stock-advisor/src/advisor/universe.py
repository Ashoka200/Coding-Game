"""Universe management: fetch NSE index constituents, keep survivorship history."""
from __future__ import annotations

import io
from datetime import date

import pandas as pd
import requests

from . import config, db


def fetch_nifty500() -> pd.DataFrame:
    """Download the current Nifty 500 constituent list (public NSE CSV)."""
    resp = requests.get(
        config.NIFTY500_URL, headers=config.NSE_HEADERS, timeout=config.REQUEST_TIMEOUT
    )
    resp.raise_for_status()
    df = pd.read_csv(io.StringIO(resp.text))
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
    # Expected columns: company_name, industry, symbol, series, isin_code
    return df


def update_universe() -> tuple[int, int]:
    """Upsert current constituents; mark dropped names inactive (never delete).

    Returns (n_current, n_marked_inactive).
    """
    df = fetch_nifty500()
    today = date.today().isoformat()
    current_symbols = set(df["symbol"].str.strip())

    with db.connect() as conn:
        for _, row in df.iterrows():
            conn.execute(
                """
                INSERT INTO stocks (symbol, name, isin, industry, index_name,
                                    active, first_seen, last_seen)
                VALUES (?, ?, ?, ?, 'NIFTY 500', 1, ?, ?)
                ON CONFLICT(symbol) DO UPDATE SET
                    name=excluded.name, isin=excluded.isin,
                    industry=excluded.industry, active=1, last_seen=excluded.last_seen
                """,
                (
                    row["symbol"].strip(),
                    row.get("company_name", ""),
                    row.get("isin_code", ""),
                    row.get("industry", ""),
                    today,
                    today,
                ),
            )
        cur = conn.execute("SELECT symbol FROM stocks WHERE active=1")
        known_active = {r[0] for r in cur.fetchall()}
        dropped = known_active - current_symbols
        for sym in dropped:
            conn.execute("UPDATE stocks SET active=0 WHERE symbol=?", (sym,))
        db.log_refresh(conn, "universe", True, f"{len(current_symbols)} current, {len(dropped)} dropped")
    return len(current_symbols), len(dropped)


def active_symbols() -> list[str]:
    with db.connect() as conn:
        cur = conn.execute("SELECT symbol FROM stocks WHERE active=1 ORDER BY symbol")
        return [r[0] for r in cur.fetchall()]
