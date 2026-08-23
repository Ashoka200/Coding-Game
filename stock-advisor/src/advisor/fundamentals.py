"""Fundamental scorer (module 02) + yfinance snapshot fetcher.

Scoring works off whatever point-in-time fields exist in the `fundamentals` table;
missing fields score their category neutral and are reported as data gaps (never
silently treated as good). Governance data (pledging etc.) is not in free APIs —
scored neutral with an explicit gap flag until a better source is wired.
"""
from __future__ import annotations

from datetime import date

from . import db

# yfinance .info keys → our canonical field names
YF_FIELDS = {
    "returnOnEquity": "roe",
    "debtToEquity": "debt_to_equity",       # yf reports in % (e.g. 45.0)
    "profitMargins": "net_margin",
    "operatingMargins": "op_margin",
    "revenueGrowth": "revenue_growth",
    "earningsGrowth": "earnings_growth",
    "trailingPE": "pe",
    "priceToBook": "pb",
    "enterpriseToEbitda": "ev_ebitda",
    "marketCap": "market_cap",
    "freeCashflow": "fcf",
    "totalCash": "total_cash",
    "totalDebt": "total_debt",
    "heldPercentInsiders": "promoter_holding",
}


def fetch_fundamentals_yf(symbols: list[str]) -> int:
    """Snapshot fundamentals from yfinance into the point-in-time store."""
    import yfinance as yf
    from . import config

    today = date.today().isoformat()
    written = 0
    with db.connect() as conn:
        for sym in symbols:
            try:
                info = yf.Ticker(sym + config.YF_SUFFIX).info or {}
            except Exception:
                continue
            rows = [
                (sym, today, ours, float(info[theirs]), "yfinance")
                for theirs, ours in YF_FIELDS.items()
                if isinstance(info.get(theirs), (int, float))
            ]
            conn.executemany(
                "INSERT OR REPLACE INTO fundamentals (symbol, as_of_date, field, value, source) "
                "VALUES (?, ?, ?, ?, ?)", rows)
            written += len(rows)
        db.log_refresh(conn, "fundamentals", True, f"{written} values")
    return written


def latest_fundamentals(symbol: str, as_of: str | None = None) -> dict:
    """Latest known value per field at/before as_of (point-in-time semantics)."""
    q = """
        SELECT field, value FROM fundamentals
        WHERE symbol=? {cutoff}
          AND as_of_date = (SELECT MAX(as_of_date) FROM fundamentals f2
                            WHERE f2.symbol=fundamentals.symbol
                              AND f2.field=fundamentals.field {cutoff2})
    """.format(cutoff="AND as_of_date<=?" if as_of else "",
               cutoff2="AND f2.as_of_date<=?" if as_of else "")
    params = [symbol] + ([as_of, as_of] if as_of else [])
    with db.connect() as conn:
        return dict(conn.execute(q, params).fetchall())


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def fundamental_score(f: dict) -> tuple[float, list[str]]:
    """Module-02 composite: Quality 40 + Growth 25 + Valuation 25 + Governance 10.

    Returns (score 0-100, flags). Missing categories score 50% of their weight and
    add a data-gap flag.
    """
    flags: list[str] = []

    # Quality (40): ROE, margins, leverage
    q = 0.0
    if "roe" in f:
        q += _clamp(f["roe"] / 0.20, 0, 1) * 20            # 20% ROE → full marks
    else:
        q += 10; flags.append("data_gap:roe")
    if "op_margin" in f:
        q += _clamp(f["op_margin"] / 0.20, 0, 1) * 10
    else:
        q += 5; flags.append("data_gap:op_margin")
    if "debt_to_equity" in f:
        de = f["debt_to_equity"] / 100 if f["debt_to_equity"] > 5 else f["debt_to_equity"]
        q += _clamp(1 - de / 2, 0, 1) * 10                  # D/E 0 → 10, ≥2 → 0
        if de > 2:
            flags.append("high_leverage")
    else:
        q += 5; flags.append("data_gap:leverage")

    # Growth (25)
    g = 0.0
    if "revenue_growth" in f:
        g += _clamp(f["revenue_growth"] / 0.15, 0, 1) * 12.5
    else:
        g += 6.25; flags.append("data_gap:revenue_growth")
    if "earnings_growth" in f:
        g += _clamp(f["earnings_growth"] / 0.15, 0, 1) * 12.5
    else:
        g += 6.25; flags.append("data_gap:earnings_growth")

    # Valuation (25): PE and EV/EBITDA bands (sector-relative comes with factors.py)
    v = 0.0
    if "pe" in f and f["pe"] > 0:
        v += _clamp((60 - f["pe"]) / 45, 0, 1) * 15         # PE≤15 full, ≥60 zero
        if f["pe"] > 80:
            flags.append("extreme_valuation")
    else:
        v += 7.5; flags.append("data_gap:pe")
    if "ev_ebitda" in f and f["ev_ebitda"] > 0:
        v += _clamp((30 - f["ev_ebitda"]) / 22, 0, 1) * 10
    else:
        v += 5; flags.append("data_gap:ev_ebitda")

    # Governance (10): only promoter holding available free; pledging unavailable.
    gov = 5.0
    flags.append("data_gap:pledging")
    if "promoter_holding" in f:
        if f["promoter_holding"] >= 0.40:
            gov += 3
        elif f["promoter_holding"] < 0.10:
            flags.append("low_promoter_holding")
    score = round(q + g + v + gov, 1)
    return score, flags
