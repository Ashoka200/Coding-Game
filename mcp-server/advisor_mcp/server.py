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

from mcp.server import Server                      # noqa: E402
from mcp.server.stdio import stdio_server          # noqa: E402
from mcp.types import TextContent, Tool            # noqa: E402

from advisor_mcp.envelope import missing_fields, ok, unavailable  # noqa: E402

server = Server("advisor-360")

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

def tool_get_quote(symbol: str) -> dict:
    if not _db_ready():
        return unavailable("quote", "the advisor database has not been created yet; "
                                    "run `bash run_live.sh --backfill` first")
    f, as_of = _features(symbol)
    if f is None:
        return unavailable("quote", f"no price history stored for {symbol}")
    data = {
        "symbol": symbol, "close": round(f["close"], 2),
        "atr14": round(f["atr14"], 2), "atr_percent": round(f["atr_pct"] * 100, 2),
        "rsi14": round(f["rsi14"], 1),
        "sma200": round(f["sma200"], 2), "ema50": round(f["ema50"], 2),
        "high_52w": round(f["high_52w"], 2),
        "distance_from_52w_high_percent": round(f["dist_52w_high"] * 100, 2),
        "trend_stage": __import__("advisor.technical", fromlist=["x"]).stage(f),
    }
    return ok(data,
              provenance=[{"field": "prices", "source": "advisor database (yfinance EOD, "
                           "cross-checked against NSE bhavcopy)", "as_of": as_of}],
              caveats=["End-of-day close, not a live quote. Confirm live prices in your broker "
                       "terminal before acting."])


def tool_get_market_regime() -> dict:
    if not _db_ready():
        return unavailable("market regime", "the advisor database has not been created yet")
    from advisor.regime import compute_regime, last_state
    r = compute_regime(prev_state=last_state())
    if r is None:
        return unavailable("market regime",
                           "not enough price history stored to compute breadth")
    return ok({"state": r.state, "breadth_above_200sma": r.breadth_200,
               "breadth_above_50sma": r.breadth_50,
               "index_drawdown_from_1y_high": r.index_drawdown,
               "index_above_200sma": r.index_above_200sma,
               "signals": r.signals, "risk_on": r.risk_on()},
              provenance=[{"field": "regime", "source": "computed from the stored universe "
                           "(equal-weight index and breadth)", "as_of": "latest stored session"}])


def tool_get_fundamentals(symbol: str) -> dict:
    if not _db_ready():
        return unavailable("fundamentals", "the advisor database has not been created yet")
    from advisor import db
    from advisor.fundamentals import fundamental_score, latest_fundamentals
    values = latest_fundamentals(symbol)
    if not values:
        return unavailable("fundamentals", f"no fundamental values stored for {symbol}; "
                                           "run `advisor.cli fetch-fundamentals`")
    with db.connect() as conn:
        row = conn.execute("SELECT MAX(as_of_date), source FROM fundamentals WHERE symbol=?",
                           (symbol,)).fetchone()
    as_of, source = (row[0], row[1]) if row else (None, "unknown")
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
                       "Read them in the annual report before a long-term decision."])


def tool_get_news(symbol: str, days: int = 14) -> dict:
    from advisor.news import fetch_news, pressure
    try:
        items = fetch_news(symbol, days=days)
    except Exception as exc:                       # network refused, feed changed, etc.
        return unavailable("news", f"the news feed could not be reached: {exc}")
    if not items:
        return ok({"symbol": symbol, "items": [], "pressure": pressure([])},
                  provenance=[{"field": "news", "source": "Google News RSS (India)",
                               "as_of": "now"}],
                  caveats=[f"No items found for {symbol} in the last {days} days. "
                           "Absence of news is not evidence of absence of events."])
    return ok({"symbol": symbol, "items": [i.to_dict() for i in items],
               "pressure": pressure(items)},
              provenance=[{"field": "news", "source": "Google News RSS (India)",
                           "as_of": "now"}],
              caveats=["Headlines are third-party reporting, not verified fact. "
                       "Event labels and weights are this system's classification."])


def tool_get_verdict(symbol: str, include_news: bool = True) -> dict:
    if not _db_ready():
        return unavailable("verdict", "the advisor database has not been created yet")
    from advisor import db, technical
    from advisor.fundamentals import fundamental_score, latest_fundamentals
    from advisor.regime import compute_regime, last_state
    from advisor.verdict import decide

    f, as_of = _features(symbol)
    if f is None:
        return unavailable("verdict", f"no price history stored for {symbol}")
    values = latest_fundamentals(symbol)
    score = fundamental_score(values)[0] if values else None
    news_items, press = None, None
    if include_news:
        try:
            from advisor.news import fetch_news, pressure
            news_items = fetch_news(symbol)
            press = pressure(news_items)
        except Exception:
            news_items, press = None, None
    reading = compute_regime(prev_state=last_state())

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
               stage=technical.stage(f),
               regime_risk_on=reading.risk_on() if reading else True,
               holding=holding)

    return ok(v.to_dict(),
              provenance=[
                  {"field": "prices", "source": "advisor database (EOD)", "as_of": as_of},
                  {"field": "fundamentals", "source": "advisor database" if values else "none",
                   "as_of": "latest stored"},
                  {"field": "news", "source": "Google News RSS" if press else "not fetched",
                   "as_of": "now" if press else None},
              ],
              unknown=[{"field": u, "reason": "not available to the engine for this decision"}
                       for u in v.unknowns],
              caveats=["The action is the output of a fixed nine-stage sequence, shown in "
                       "`chain`. Report the chain rather than inventing a rationale.",
                       "Decision support only, not investment advice."])


def tool_get_portfolio() -> dict:
    if not _db_ready():
        return unavailable("portfolio", "the advisor database has not been created yet")
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
        return unavailable("plan", "the advisor database has not been created yet")
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
        return unavailable("universe", "the advisor database has not been created yet")
    from advisor.universe import active_symbols
    syms = active_symbols()
    return ok({"symbols": syms, "count": len(syms)},
              provenance=[{"field": "universe", "source": "NSE index constituents stored locally",
                           "as_of": "last universe sync"}],
              caveats=["Delisted and removed names are retained in the database but excluded "
                       "here; backtests still see them."])


TOOLS = [
    Tool(name="get_quote",
         description="Verified end-of-day price and technical state for one NSE symbol. "
                     "Use this instead of any remembered price.",
         inputSchema={"type": "object", "properties": {
             "symbol": {"type": "string", "description": "NSE symbol, e.g. RELIANCE"}},
             "required": ["symbol"]}),
    Tool(name="get_market_regime",
         description="Current market state (expansion/caution/stress/crisis) with breadth "
                     "and drawdown, computed from the stored universe.",
         inputSchema={"type": "object", "properties": {}}),
    Tool(name="get_fundamentals",
         description="Stored fundamental values and the quality/growth/valuation score for one "
                     "symbol. Fields the source did not supply are returned in `unknown` and "
                     "must not be estimated.",
         inputSchema={"type": "object", "properties": {
             "symbol": {"type": "string"}}, "required": ["symbol"]}),
    Tool(name="get_news",
         description="Recent headlines for one symbol, classified by event type and weighted "
                     "for direction and recency.",
         inputSchema={"type": "object", "properties": {
             "symbol": {"type": "string"},
             "days": {"type": "integer", "description": "lookback window, default 14"}},
             "required": ["symbol"]}),
    Tool(name="get_verdict",
         description="The advisor's action for one symbol (sell/trim/hold/watch/avoid/"
                     "accumulate/buy) with conviction, horizon and the full nine-stage "
                     "reasoning chain. Report the chain rather than inventing a rationale.",
         inputSchema={"type": "object", "properties": {
             "symbol": {"type": "string"},
             "include_news": {"type": "boolean", "description": "default true"}},
             "required": ["symbol"]}),
    Tool(name="get_portfolio",
         description="Open positions with exit prices, weights, portfolio heat and alerts.",
         inputSchema={"type": "object", "properties": {}}),
    Tool(name="build_portfolio_plan",
         description="Propose a complete portfolio for an amount. A PROPOSAL ONLY — this "
                     "never places an order.",
         inputSchema={"type": "object", "properties": {
             "amount": {"type": "number", "description": "rupees to invest"},
             "profile": {"type": "string", "enum": ["careful", "balanced", "ambitious"]}},
             "required": ["amount"]}),
    Tool(name="get_universe",
         description="Symbols the local database currently tracks.",
         inputSchema={"type": "object", "properties": {}}),
]

HANDLERS = {
    "get_quote": lambda a: tool_get_quote(a["symbol"].upper()),
    "get_market_regime": lambda a: tool_get_market_regime(),
    "get_fundamentals": lambda a: tool_get_fundamentals(a["symbol"].upper()),
    "get_news": lambda a: tool_get_news(a["symbol"].upper(), int(a.get("days", 14))),
    "get_verdict": lambda a: tool_get_verdict(a["symbol"].upper(),
                                              bool(a.get("include_news", True))),
    "get_portfolio": lambda a: tool_get_portfolio(),
    "build_portfolio_plan": lambda a: tool_build_portfolio_plan(
        float(a["amount"]), str(a.get("profile", "balanced")).lower()),
    "get_universe": lambda a: tool_get_universe(),
}


@server.list_tools()
async def list_tools() -> list[Tool]:
    return TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    handler = HANDLERS.get(name)
    if handler is None:
        payload = unavailable(name, "unknown tool")
    else:
        try:
            payload = handler(arguments or {})
        except Exception as exc:                   # never fail into a guess
            payload = unavailable(name, f"the engine raised: {type(exc).__name__}: {exc}")
    return [TextContent(type="text", text=json.dumps(payload, indent=2, default=str))]


async def main() -> None:
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
