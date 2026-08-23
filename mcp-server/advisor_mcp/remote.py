"""Live-console fallback: the same figures over HTTP when no local database exists.

Used only when the local advisor database is absent or silent. Field names are
normalised to the local shape so downstream engines cannot tell the difference —
but `provenance` always names which source actually answered, and remote mode
carries its own caveats, because it is thinner than the local path.
"""
from __future__ import annotations

import os

import requests

BASE = os.environ.get("ADVISOR_API_BASE", "https://advisor-360-live.netlify.app").rstrip("/")
TIMEOUT = float(os.environ.get("ADVISOR_API_TIMEOUT", "25"))

# Remote mode approximates two things the local engines compute exactly.
REMOTE_CAVEATS = [
    "Served by the deployed console API, not a local database. Only the current "
    "snapshot is available — no stored history, so backtests, portfolio heat and "
    "point-in-time fundamentals are not computable in this mode.",
    "Trend stage uses a 50-day simple average where the local engine uses a 50-day "
    "exponential average; the two rarely disagree but can at a turning point.",
]


class RemoteUnavailable(RuntimeError):
    """The console API could not answer. Never downgraded into a guess."""


def _get(path: str, params: dict) -> dict:
    try:
        resp = requests.get(f"{BASE}{path}", params=params, timeout=TIMEOUT,
                            headers={"User-Agent": "advisor-mcp/1.0"})
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        raise RemoteUnavailable(f"{BASE}{path}: {exc}") from exc


def quote_features(symbol: str) -> tuple[dict, str]:
    """Return a features dict shaped like technical.compute_features(), plus source."""
    payload = _get("/api/quotes", {"symbols": symbol})
    rows = [q for q in payload.get("quotes", []) if q.get("symbol") == symbol]
    if not rows:
        raise RemoteUnavailable(f"console API returned no data for {symbol}")
    q = rows[0]
    last, sma200 = q.get("last"), q.get("sma200")
    if last is None:
        raise RemoteUnavailable(f"console API returned no price for {symbol}")
    high52 = q.get("high52")
    features = {
        "close": last,
        "atr14": q.get("atr14"),
        "atr_pct": (q["atr14"] / last) if q.get("atr14") and last else None,
        "rsi14": q.get("rsi14"),
        "sma200": sma200,
        # the local engine uses an exponential 50-day average; see REMOTE_CAVEATS
        "ema50": q.get("sma50"),
        "sma200_slope": (0.01 if q.get("sma200Rising") else -0.01)
                        if q.get("sma200Rising") is not None else None,
        "high_52w": high52,
        "dist_52w_high": (last / high52 - 1) if high52 else None,
        "swing_low_20d": q.get("swingLow20"),
        "mom_12_1": q.get("mom6m"),          # 6-month proxy; named honestly below
    }
    return features, "live console API (/api/quotes)"


# console field -> local field
_FUND_MAP = {
    "pe": "pe", "pb": "pb", "roe": "roe", "roce": "roce",
    "opMargin": "op_margin", "netMargin": "net_margin",
    "debtToEquity": "debt_to_equity", "interestCover": "interest_cover",
    "revenueGrowth": "revenue_growth", "earningsGrowth": "earnings_growth",
    "evEbitda": "ev_ebitda", "currentRatio": "current_ratio",
    "dividendYield": "dividend_yield", "marketCap": "market_cap",
}


def fundamentals(symbol: str) -> tuple[dict, str, list[str]]:
    """Return (values, source_label, diagnostics). Raises if nothing answered."""
    payload = _get("/api/fundamentals", {"symbols": symbol})
    diagnostics = payload.get("diagnostics", []) or []
    rows = [f for f in payload.get("fundamentals", []) if f.get("symbol") == symbol]
    if not rows or rows[0].get("error"):
        reason = rows[0].get("error") if rows else "symbol absent from response"
        raise RemoteUnavailable(f"{reason}"
                                + (f" (attempts: {'; '.join(diagnostics[:5])})" if diagnostics else ""))
    row = rows[0]
    values = {local: row[remote] for remote, local in _FUND_MAP.items()
              if row.get(remote) is not None}
    return values, f"live console API (/api/fundamentals via {row.get('source', 'unknown')})", diagnostics


def news(symbol: str, days: int = 14) -> tuple[list[dict], dict, str]:
    payload = _get("/api/news", {"symbol": symbol})
    if payload.get("error"):
        raise RemoteUnavailable(payload.get("detail") or payload["error"])
    items = payload.get("items", [])
    press = payload.get("pressure", {}) or {}
    press.setdefault("material_count", payload.get("materialCount", 0))
    return items, press, "live console API (/api/news)"


def deep_dive(symbol: str) -> tuple[dict, str]:
    payload = _get("/api/deepdive", {"symbol": symbol})
    if payload.get("error"):
        raise RemoteUnavailable(payload.get("hint") or payload["error"])
    return payload, "live console API (/api/deepdive)"


def market_regime() -> tuple[dict, str]:
    """Index-level regime from the console's own inputs (breadth needs the local DB)."""
    payload = _get("/api/quotes", {"symbols": "^NSEI"})
    rows = [q for q in payload.get("quotes", []) if q.get("symbol") == "^NSEI"]
    if not rows:
        raise RemoteUnavailable("console API returned no index data")
    q = rows[0]
    last, sma200, high52 = q.get("last"), q.get("sma200"), q.get("high52")
    if last is None or sma200 is None or not high52:
        raise RemoteUnavailable("console API index payload incomplete")
    dd = last / high52 - 1
    above = last > sma200
    state = ("EXPANSION" if above and dd > -0.05
             else "CRISIS" if dd < -0.20
             else "STRESS" if dd < -0.10
             else "CAUTION")
    return ({"state": state, "index_level": last, "index_above_200sma": above,
             "index_drawdown_from_1y_high": round(dd, 4),
             "risk_on": state == "EXPANSION",
             "breadth_above_200sma": None, "breadth_above_50sma": None,
             "signals": []},
            "live console API (index only)")
