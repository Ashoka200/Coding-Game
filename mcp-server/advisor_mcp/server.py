"""MCP server exposing the 360° Advisor's engines as verified-data tools.

Design rule: this process reads the advisor's own database and engines. It
never asks a model to supply a figure, and never fills a gap with a plausible
number — see envelope.py.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# The advisor package lives beside this server in the repository.
_REPO = Path(__file__).resolve().parents[2]
_SRC = _REPO / "stock-advisor" / "src"
if _SRC.exists() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from mcp.server import MCPServer                  # noqa: E402

from advisor_mcp import remote                                     # noqa: E402
from advisor_mcp.envelope import RULES, missing_fields, ok, unavailable  # noqa: E402

# `instructions` reaches the client at the protocol level, so the never-guess
# contract arrives before the first tool call rather than only alongside data.
INSTRUCTIONS = (
    "Verified market data for Indian equities (NSE/BSE). Use these tools instead of "
    "any remembered price, ratio or date.\n\n"
    "Every response has the same shape: `data` (what is known), `provenance` "
    "(source and as-of date per field), `unknown` (fields no source supplied, with "
    "reasons), `caveats`, and `rules`.\n\nRules that always apply:\n"
    + "\n".join(f"- {r}" for r in RULES)
)

mcp_server = MCPServer("advisor-360", instructions=INSTRUCTIONS, version="1.0.0")

# Hybrid resolution. Local first — it has stored history, point-in-time
# fundamentals and your portfolio. The deployed console API is the fallback so
# the tools work on a machine with no database. Which one answered is always
# reported; it is never silently mixed.
MODE = os.environ.get("ADVISOR_MODE", "auto").lower()   # auto | local | remote


def _local_allowed() -> bool:
    return MODE in ("auto", "local") and _db_ready()


def _remote_allowed() -> bool:
    return MODE in ("auto", "remote")

FUND_WANTED = {
    "pe": "valuation cannot be judged without it",
    "roe": "profitability cannot be judged without it",
    "debt_to_equity": "balance-sheet risk cannot be judged without it",
    "op_margin": "pricing power cannot be judged without it",
    "revenue_growth": "growth cannot be judged without it",
}


def _db_ready() -> bool:
    from advisor import config
    return config.DB_PATH.exists()


def _price_date(conn, symbol: str) -> str | None:
    row = conn.execute(
        "SELECT MAX(date) FROM prices_eod WHERE symbol=? AND source='yfinance'",
        (symbol,)).fetchone()
    return row[0] if row and row[0] else None


def _stage(features: dict) -> int:
    """Trend stage, tolerant of the thinner remote feature set."""
    from advisor import technical
    try:
        return technical.stage(features)
    except (KeyError, TypeError):
        close, sma200 = features.get("close"), features.get("sma200")
        rising = (features.get("sma200_slope") or 0) > 0
        if close is None or sma200 is None:
            return 1
        if close > sma200 and rising:
            return 2
        if close < sma200 and not rising:
            return 4
        return 1 if rising else 3


def _features(symbol: str):
    """Latest technical snapshot straight from the database, or None."""
    from advisor import db, technical
    from advisor.screener import _load_symbol_df
    with db.connect() as conn:
        df = _load_symbol_df(conn, symbol)
        as_of = _price_date(conn, symbol)
    if df.empty:
        return None, None
    return technical.compute_features(df), as_of


# --------------------------------------------------------------------------- tools

def _resolve_features(symbol: str):
    """(features, source_label, as_of, caveats) from whichever source answers."""
    errors = []
    if _local_allowed():
        try:
            f, as_of = _features(symbol)
            if f is not None:
                return f, ("advisor database (yfinance EOD, cross-checked against "
                           "NSE bhavcopy)"), as_of, []
            errors.append("local: no price history stored")
        except Exception as exc:
            errors.append(f"local: {exc}")
    elif MODE == "local":
        errors.append("local: database not created")
    if _remote_allowed():
        try:
            f, src = remote.quote_features(symbol)
            return f, src, "latest published session", list(remote.REMOTE_CAVEATS)
        except remote.RemoteUnavailable as exc:
            errors.append(f"remote: {exc}")
    raise LookupError("; ".join(errors) or "no source enabled")


def tool_get_quote(symbol: str) -> dict:
    try:
        f, source, as_of, caveats = _resolve_features(symbol)
    except LookupError as exc:
        return unavailable("quote", str(exc))
    def r(key, places=2, scale=1.0):
        v = f.get(key)
        return None if v is None else round(v * scale, places)

    data = {
        "symbol": symbol, "close": r("close"),
        "atr14": r("atr14"), "atr_percent": r("atr_pct", 2, 100),
        "rsi14": r("rsi14", 1),
        "sma200": r("sma200"), "ema50": r("ema50"),
        "high_52w": r("high_52w"),
        "distance_from_52w_high_percent": r("dist_52w_high", 2, 100),
        "trend_stage": _stage(f),
    }
    return ok({k: v for k, v in data.items() if v is not None},
              provenance=[{"field": "prices", "source": source, "as_of": as_of}],
              unknown=[{"field": k, "reason": "the source did not supply it"}
                       for k, v in data.items() if v is None],
              caveats=["End-of-day close, not a live quote. Confirm live prices in your broker "
                       "terminal before acting."] + caveats)


def tool_get_market_regime() -> dict:
    errors = []
    if _local_allowed():
        try:
            from advisor.regime import compute_regime, last_state
            r = compute_regime(prev_state=last_state())
            if r is not None:
                return ok({"state": r.state, "breadth_above_200sma": r.breadth_200,
                           "breadth_above_50sma": r.breadth_50,
                           "index_drawdown_from_1y_high": r.index_drawdown,
                           "index_above_200sma": r.index_above_200sma,
                           "signals": r.signals, "risk_on": r.risk_on()},
                          provenance=[{"field": "regime",
                                       "source": "computed from the stored universe "
                                                 "(equal-weight index and breadth)",
                                       "as_of": "latest stored session"}])
            errors.append("local: not enough stored history for breadth")
        except Exception as exc:
            errors.append(f"local: {exc}")
    if _remote_allowed():
        try:
            data, src = remote.market_regime()
            return ok(data, provenance=[{"field": "regime", "source": src,
                                         "as_of": "latest published session"}],
                      unknown=[{"field": "breadth_above_200sma",
                                "reason": "breadth needs the full stored universe; "
                                          "not computable in remote mode"},
                               {"field": "breadth_above_50sma",
                                "reason": "breadth needs the full stored universe"}],
                      caveats=remote.REMOTE_CAVEATS + [
                          "State is derived from the index alone, so it is coarser than the "
                          "local reading, which also weighs how many stocks participate."])
        except remote.RemoteUnavailable as exc:
            errors.append(f"remote: {exc}")
    return unavailable("market regime", "; ".join(errors) or "no source enabled")


def _resolve_fundamentals(symbol: str):
    """(values, source, as_of, extra_caveats). Raises LookupError if none answer."""
    errors = []
    if _local_allowed():
        try:
            from advisor import db
            from advisor.fundamentals import latest_fundamentals
            values = latest_fundamentals(symbol)
            if values:
                with db.connect() as conn:
                    row = conn.execute("SELECT MAX(as_of_date), source FROM fundamentals "
                                       "WHERE symbol=?", (symbol,)).fetchone()
                as_of, src = (row[0], row[1]) if row else (None, "advisor database")
                return values, f"advisor database ({src})", as_of, []
            errors.append("local: nothing stored; run `advisor.cli fetch-fundamentals`")
        except Exception as exc:
            errors.append(f"local: {exc}")
    if _remote_allowed():
        try:
            values, src, diags = remote.fundamentals(symbol)
            extra = ([f"Upstream attempts: {'; '.join(diags[:4])}"] if diags else [])
            return values, src, "latest published fetch", remote.REMOTE_CAVEATS + extra
        except remote.RemoteUnavailable as exc:
            errors.append(f"remote: {exc}")
    raise LookupError("; ".join(errors) or "no source enabled")


def tool_get_fundamentals(symbol: str) -> dict:
    from advisor.fundamentals import fundamental_score
    try:
        values, source, as_of, extra_caveats = _resolve_fundamentals(symbol)
    except LookupError as exc:
        return unavailable("fundamentals", str(exc))
    score, flags = fundamental_score(values)
    gaps = [f.split(":", 1)[1] for f in flags if f.startswith("data_gap:")]
    return ok({"symbol": symbol, "values": values, "score": score,
               "score_basis": "quality 40 / growth 25 / valuation 25 / governance 10",
               "flags": [f for f in flags if not f.startswith("data_gap:")]},
              provenance=[{"field": "fundamentals", "source": source, "as_of": as_of}],
              unknown=([{"field": g, "reason": "the source did not supply it; it scores "
                         "neutral and must not be estimated"} for g in gaps] +
                       missing_fields(values, FUND_WANTED)),
              caveats=["Promoter pledging and contingent liabilities are not in any free feed. "
                       "Read them in the annual report before a long-term decision."]
                      + extra_caveats)


def _resolve_news(symbol: str, days: int):
    """(items_as_dicts, pressure, source). Raises LookupError if none answer."""
    errors = []
    try:
        from advisor.news import fetch_news, pressure
        items = fetch_news(symbol, days=days)
        return [i.to_dict() for i in items], pressure(items), "Google News RSS (India)"
    except Exception as exc:
        errors.append(f"direct feed: {exc}")
    if _remote_allowed():
        try:
            items, press, src = remote.news(symbol, days)
            return items, press, src
        except remote.RemoteUnavailable as exc:
            errors.append(f"remote: {exc}")
    raise LookupError("; ".join(errors))


def tool_get_news(symbol: str, days: int = 14) -> dict:
    from advisor.news import pressure
    try:
        raw_items, press, news_source = _resolve_news(symbol, days)
    except LookupError as exc:
        return unavailable("news", f"the news feed could not be reached: {exc}")
    items = raw_items
    if not items:
        return ok({"symbol": symbol, "items": [], "pressure": pressure([])},
                  provenance=[{"field": "news", "source": news_source, "as_of": "now"}],
                  caveats=[f"No items found for {symbol} in the last {days} days. "
                           "Absence of news is not evidence of absence of events."])
    return ok({"symbol": symbol, "items": items, "pressure": press},
              provenance=[{"field": "news", "source": news_source, "as_of": "now"}],
              caveats=["Headlines are third-party reporting, not verified fact. "
                       "Event labels and weights are this system's classification."])


def tool_get_verdict(symbol: str, include_news: bool = True) -> dict:
    from advisor.fundamentals import fundamental_score
    from advisor.verdict import decide

    try:
        f, price_source, as_of, price_caveats = _resolve_features(symbol)
    except LookupError as exc:
        return unavailable("verdict", f"no price data for {symbol}: {exc}")

    try:
        values, fund_source, fund_as_of, fund_caveats = _resolve_fundamentals(symbol)
        score = fundamental_score(values)[0]
    except LookupError as exc:
        values, fund_source, fund_as_of, fund_caveats = None, f"unavailable ({exc})", None, []
        score = None

    news_items, press, news_source = None, None, "not fetched"
    if include_news:
        try:
            news_items, press, news_source = _resolve_news(symbol, 14)
        except LookupError as exc:
            news_source = f"unavailable ({exc})"

    reading = None
    if _local_allowed():
        try:
            from advisor.regime import compute_regime, last_state
            reading = compute_regime(prev_state=last_state())
        except Exception:
            reading = None
    risk_on = reading.risk_on() if reading is not None else None
    if risk_on is None and _remote_allowed():
        try:
            risk_on = remote.market_regime()[0]["risk_on"]
        except remote.RemoteUnavailable:
            risk_on = True          # neutral default; stated in caveats below

    holding = None
    try:
        from advisor.portfolio import snapshot
        snap = snapshot()
        pos = snap["positions"]
        if not pos.empty:
            match = pos[pos["symbol"] == symbol]
            if not match.empty:
                r0 = match.iloc[0]
                holding = {"qty": int(r0["qty"]), "stop": r0["stop"],
                           "weight": float(r0["weight"]) if r0["weight"] == r0["weight"] else None}
    except Exception:
        holding = None

    v = decide(symbol=symbol, features=f,
               fundamentals={"pe": values.get("pe"), "roe": values.get("roe"),
                             "roce": values.get("roce"),
                             "debt_to_equity": (values.get("debt_to_equity") / 100
                                                if values.get("debt_to_equity", 0) and
                                                values["debt_to_equity"] > 5
                                                else values.get("debt_to_equity")),
                             "interest_cover": values.get("interest_cover")} if values else None,
               fundamental_score=score,
               news_items=news_items, news_pressure=press,
               stage=_stage(f),
               regime_risk_on=bool(risk_on),
               holding=holding)

    return ok(v.to_dict(),
              provenance=[
                  {"field": "prices", "source": price_source, "as_of": as_of},
                  {"field": "fundamentals", "source": fund_source, "as_of": fund_as_of},
                  {"field": "news", "source": news_source,
                   "as_of": "now" if press else None},
              ],
              unknown=[{"field": u, "reason": "not available to the engine for this decision"}
                       for u in v.unknowns],
              caveats=["The action is the output of a fixed nine-stage sequence, shown in "
                       "`chain`. Report the chain rather than inventing a rationale.",
                       "Decision support only, not investment advice."]
                      + price_caveats + fund_caveats
                      + ([] if reading is not None else
                         ["Market breadth was not available, so the regime gate used the "
                          "index alone."]))


def tool_get_deep_dive(symbol: str) -> dict:
    """Full financial statements — served by the console API, which scrapes them."""
    if not _remote_allowed():
        return unavailable("deep dive", "remote mode is disabled (ADVISOR_MODE=local) and "
                                        "statement scraping lives in the console API")
    try:
        payload, src = remote.deep_dive(symbol)
    except remote.RemoteUnavailable as exc:
        return unavailable("deep dive", str(exc))
    return ok(payload, provenance=[{"field": "financial statements", "source": src,
                                    "as_of": "latest filed period"}],
              caveats=["Statements are as published. Contingent liabilities, litigation, "
                       "customer concentration and related-party transactions are in the "
                       "notes to accounts, not here — read them before a long-term decision."])


def tool_get_portfolio() -> dict:
    if not _db_ready():
        return unavailable("portfolio",
                           "portfolio tracking is local-only — it needs the advisor database "
                           "on this machine. Run `bash run_live.sh --backfill`, then record "
                           "holdings with `advisor.cli portfolio add`.")
    from advisor.portfolio import snapshot
    snap = snapshot()
    pos = snap["positions"]
    if pos.empty:
        return ok({"positions": [], "total_value": snap["total_value"], "alerts": []},
                  caveats=["No open positions recorded."])
    cols = ["symbol", "book", "qty", "avg_cost", "last", "value", "pnl_pct", "weight", "stop"]
    return ok({"positions": json.loads(pos[cols].to_json(orient="records")),
               "total_value": snap["total_value"], "heat_percent": snap["heat_pct"] * 100,
               "sector_weights": snap["sector_weights"], "alerts": snap["alerts"]},
              provenance=[{"field": "positions", "source": "advisor database (holdings you "
                           "recorded)", "as_of": "latest stored prices"}])


def tool_build_portfolio_plan(amount: float, profile: str = "balanced") -> dict:
    if not _db_ready():
        return unavailable("plan",
                           "plan building is local-only — it screens the stored universe. "
                           "Run `bash run_live.sh --backfill` first, or build a plan in the "
                           "web console's 'Invest an amount' tab.")
    from advisor.planner import build_plan
    try:
        plan = build_plan(amount, profile)
    except ValueError as exc:
        return unavailable("plan", str(exc))
    return ok(plan.to_dict(),
              provenance=[{"field": "prices", "source": "advisor database (EOD)",
                           "as_of": "latest stored session"}],
              caveats=["This is a PROPOSAL. Nothing is ordered. Approving and placing orders "
                       "happens in the CLI, with the user's own broker confirmation.",
                       "The bad-month estimate deliberately does not credit stop-losses, "
                       "because prices gap through them."])


def tool_get_universe() -> dict:
    if not _db_ready():
        return unavailable("universe",
                           "the tracked universe is local-only. Run `bash run_live.sh` to "
                           "populate it.")
    from advisor.universe import active_symbols
    syms = active_symbols()
    return ok({"symbols": syms, "count": len(syms)},
              provenance=[{"field": "universe", "source": "NSE index constituents stored locally",
                           "as_of": "last universe sync"}],
              caveats=["Delisted and removed names are retained in the database but excluded "
                       "here; backtests still see them."])


# --------------------------------------------------------------- MCP interface
# Thin wrappers: schemas are inferred from the signatures, descriptions from the
# docstrings. The engine functions above stay plain and testable.


def _safe(fn, label, *args, **kwargs) -> dict:
    """Never let an exception become a guess."""
    try:
        return fn(*args, **kwargs)
    except Exception as exc:
        return unavailable(label, f"the engine raised: {type(exc).__name__}: {exc}")


@mcp_server.tool()
def get_quote(symbol: str) -> dict:
    """Verified end-of-day price and technical state for one NSE symbol.
    Use this instead of any remembered price."""
    return _safe(tool_get_quote, "quote", symbol.upper())


@mcp_server.tool()
def get_market_regime() -> dict:
    """Current market state (expansion/caution/stress/crisis) with breadth and
    drawdown, and whether new risk-taking is allowed."""
    return _safe(tool_get_market_regime, "market regime")


@mcp_server.tool()
def get_fundamentals(symbol: str) -> dict:
    """Fundamental values and the quality/growth/valuation score for one symbol.
    Fields no source supplied are returned in `unknown` and must not be estimated."""
    return _safe(tool_get_fundamentals, "fundamentals", symbol.upper())


@mcp_server.tool()
def get_news(symbol: str, days: int = 14) -> dict:
    """Recent headlines for one symbol, classified by event type and weighted for
    direction and recency."""
    return _safe(tool_get_news, "news", symbol.upper(), days)


@mcp_server.tool()
def get_verdict(symbol: str, include_news: bool = True) -> dict:
    """The advisor's action for one symbol (sell/trim/hold/watch/avoid/accumulate/buy)
    with conviction, horizon and the full nine-stage reasoning chain. Report the chain
    rather than inventing a rationale."""
    return _safe(tool_get_verdict, "verdict", symbol.upper(), include_news)


@mcp_server.tool()
def get_deep_dive(symbol: str) -> dict:
    """Full published financial statements for one company — profit and loss, balance
    sheet, cash flow, ratios and shareholding as year-by-year series."""
    return _safe(tool_get_deep_dive, "deep dive", symbol.upper())


@mcp_server.tool()
def get_portfolio() -> dict:
    """Open positions with exit prices, weights, portfolio heat and alerts.
    Local database only."""
    return _safe(tool_get_portfolio, "portfolio")


@mcp_server.tool()
def build_portfolio_plan(amount: float, profile: str = "balanced") -> dict:
    """Propose a complete portfolio for an amount (profile: careful, balanced or
    ambitious). A PROPOSAL ONLY — this never places an order."""
    return _safe(tool_build_portfolio_plan, "plan", float(amount), profile.lower())


@mcp_server.tool()
def get_universe() -> dict:
    """Symbols the local database currently tracks."""
    return _safe(tool_get_universe, "universe")


def main() -> None:
    mcp_server.run(transport="stdio")


if __name__ == "__main__":
    main()
