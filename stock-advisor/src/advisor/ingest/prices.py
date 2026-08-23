"""EOD price ingestion via yfinance (adjusted history, 10y backfill + daily update)."""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from .. import config, db


def _yf_download(symbols: list[str], start: str) -> pd.DataFrame:
    import yfinance as yf

    tickers = [s + config.YF_SUFFIX for s in symbols]
    data = yf.download(
        tickers,
        start=start,
        auto_adjust=False,
        actions=False,
        group_by="ticker",
        threads=True,
        progress=False,
    )
    return data


def update_prices(symbols: list[str] | None = None, backfill: bool = False,
                  batch_size: int = 50) -> int:
    """Fetch EOD prices for symbols and upsert. Returns number of rows written.

    backfill=True pulls PRICE_HISTORY_YEARS of history; otherwise last 30 days
    (idempotent upsert makes overlap harmless).
    """
    from ..universe import active_symbols

    symbols = symbols or active_symbols()
    days = 365 * config.PRICE_HISTORY_YEARS if backfill else 30
    start = (date.today() - timedelta(days=days)).isoformat()
    written = 0

    with db.connect() as conn:
        for i in range(0, len(symbols), batch_size):
            batch = symbols[i : i + batch_size]
            data = _yf_download(batch, start)
            if data.empty:
                continue
            for sym in batch:
                ticker = sym + config.YF_SUFFIX
                try:
                    frame = data[ticker] if len(batch) > 1 else data
                except KeyError:
                    continue
                frame = frame.dropna(subset=["Close"])
                rows = [
                    (
                        sym,
                        idx.date().isoformat(),
                        float(r["Open"]), float(r["High"]),
                        float(r["Low"]), float(r["Close"]),
                        int(r["Volume"]) if pd.notna(r["Volume"]) else None,
                        float(r["Adj Close"]) if "Adj Close" in r and pd.notna(r["Adj Close"]) else None,
                        "yfinance",
                    )
                    for idx, r in frame.iterrows()
                ]
                conn.executemany(
                    """
                    INSERT INTO prices_eod
                        (symbol, date, open, high, low, close, volume, adj_close, source)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(symbol, date, source) DO UPDATE SET
                        open=excluded.open, high=excluded.high, low=excluded.low,
                        close=excluded.close, volume=excluded.volume,
                        adj_close=excluded.adj_close
                    """,
                    rows,
                )
                written += len(rows)
            conn.commit()
        db.log_refresh(conn, "prices", True, f"{written} rows, {len(symbols)} symbols")
    return written


def load_prices(symbol: str, start: str | None = None) -> pd.DataFrame:
    """Read a symbol's price history from the DB as a DataFrame indexed by date."""
    with db.connect() as conn:
        q = "SELECT date, open, high, low, close, volume, adj_close FROM prices_eod " \
            "WHERE symbol=? AND source='yfinance'"
        params: list = [symbol]
        if start:
            q += " AND date >= ?"
            params.append(start)
        q += " ORDER BY date"
        df = pd.read_sql_query(q, conn, params=params, parse_dates=["date"])
    return df.set_index("date")
