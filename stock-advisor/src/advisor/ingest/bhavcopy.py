"""Official NSE bhavcopy ingestion — the cross-validation source for yfinance data.

Doctrine (module 04/BUILD-PLAN): never trust a single data source. Bhavcopy is the
exchange's official record; yfinance is convenient but third-party. Daily job pulls
bhavcopy, stores it under source='bhavcopy', and `cross_check` reports divergences.
"""
from __future__ import annotations

import io
import time
import zipfile
from datetime import date

import pandas as pd
import requests

from .. import config, db


def fetch_bhavcopy(for_date: date) -> pd.DataFrame | None:
    """Download and parse the new-format CM bhavcopy for a date (None if absent —
    holidays/weekends return 404). Cached on disk."""
    ymd = for_date.strftime("%Y%m%d")
    cache = config.BHAVCOPY_CACHE_DIR / f"{ymd}.csv"
    config.ensure_dirs()
    if cache.exists():
        return pd.read_csv(cache)

    url = config.BHAVCOPY_URL.format(date=ymd)
    resp = requests.get(url, headers=config.NSE_HEADERS, timeout=config.REQUEST_TIMEOUT)
    time.sleep(config.THROTTLE_SECONDS)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        name = zf.namelist()[0]
        df = pd.read_csv(zf.open(name))
    df.to_csv(cache, index=False)
    return df


def ingest_bhavcopy(for_date: date | None = None) -> int:
    """Store one day's bhavcopy EQ-series rows. Returns rows written (0 = holiday)."""
    for_date = for_date or date.today()
    df = fetch_bhavcopy(for_date)
    if df is None:
        return 0
    # New-format columns: TckrSymb, SctySrs, OpnPric, HghPric, LwPric, ClsPric, TtlTradgVol
    eq = df[df["SctySrs"] == "EQ"]
    iso = for_date.isoformat()
    rows = [
        (r["TckrSymb"], iso, r["OpnPric"], r["HghPric"], r["LwPric"],
         r["ClsPric"], int(r["TtlTradgVol"]), None, "bhavcopy")
        for _, r in eq.iterrows()
    ]
    with db.connect() as conn:
        conn.executemany(
            """
            INSERT INTO prices_eod
                (symbol, date, open, high, low, close, volume, adj_close, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol, date, source) DO UPDATE SET
                open=excluded.open, high=excluded.high, low=excluded.low,
                close=excluded.close, volume=excluded.volume
            """,
            rows,
        )
        db.log_refresh(conn, "bhavcopy", True, f"{len(rows)} rows for {iso}")
    return len(rows)


def cross_check(for_date: date, tolerance: float = 0.005) -> pd.DataFrame:
    """Compare yfinance vs bhavcopy closes for a date; return divergent symbols."""
    iso = for_date.isoformat()
    with db.connect() as conn:
        df = pd.read_sql_query(
            """
            SELECT a.symbol, a.close AS yf_close, b.close AS bhav_close
            FROM prices_eod a JOIN prices_eod b
              ON a.symbol=b.symbol AND a.date=b.date
            WHERE a.date=? AND a.source='yfinance' AND b.source='bhavcopy'
            """,
            conn, params=[iso],
        )
    if df.empty:
        return df
    df["diff_pct"] = (df["yf_close"] - df["bhav_close"]).abs() / df["bhav_close"]
    return df[df["diff_pct"] > tolerance].sort_values("diff_pct", ascending=False)
