# 360° Advisor MCP server

Gives an LLM **verified** market data instead of remembered or invented figures.

## The contract this server enforces

Every response carries the same envelope:

```json
{
  "data":       { ... },
  "provenance": [{"field": "close", "source": "NSE bhavcopy", "as_of": "2026-08-22"}],
  "unknown":    [{"field": "roe", "reason": "no fundamental source answered"}],
  "caveats":    ["End-of-day data, not live."],
  "rules":      ["Do not estimate any field listed in `unknown` — report it as unavailable.", ...]
}
```

Three properties matter:

1. **Nothing is fabricated.** A figure the sources did not supply appears in
   `unknown` with a reason. It is never filled in with a plausible number.
2. **Everything is attributed.** Each figure names its source and as-of date,
   so the model can cite rather than assert.
3. **The model is told the rules, in-band.** `rules` travels with the data, so a
   model that never read this file still gets the constraint.

The rules also travel at the protocol level: the server's `instructions` field
carries them, so a client receives the contract before the first tool call.

## Tools

| Tool | Returns |
|---|---|
| `get_quote` | last close, previous close, ATR, RSI-14, 50/200-day averages, 52-week high |
| `get_market_regime` | expansion / caution / stress / crisis, with breadth and drawdown |
| `get_fundamentals` | ratios and statement-derived figures, per-field provenance |
| `get_news` | classified headlines with event type, weight and recency |
| `get_verdict` | the nine-stage decision with its full reasoning chain |
| `get_portfolio` | open positions, exit prices, portfolio heat |
| `build_portfolio_plan` | a complete proposed plan for an amount (proposal only) |
| `get_universe` | tradeable symbols the local database knows |
| `get_valuation` | DCF, the growth the price already assumes, relative multiples |
| `get_ownership` | promoter/FII/DII movement, and who is selling to whom |
| `get_credit` | Altman-Z, Beneish-M, Piotroski-F, maturity wall, covenant headroom |
| `analyse_special_situation` | buyback, open offer, rights, merger, delisting, demerger arithmetic |
| `get_portfolio_risk` | VaR, expected shortfall, crisis stress, correlation |
| `get_deep_dive` | full published statements — P&L, balance sheet, cash flow, ratios, shareholding |

No tool places an order. Order preparation stays in the CLI, behind explicit
human approval.

## Hybrid: it works with or without a local database

`ADVISOR_MODE` controls where figures come from (default `auto`):

| Mode | Behaviour |
|---|---|
| `auto` | Local database first; falls back to the deployed console API when it is absent or silent |
| `local` | Local only — fails cleanly rather than reaching out |
| `remote` | Console API only — no local setup needed |

Provenance always names which one answered, and remote mode carries its own
caveats, because it is genuinely thinner: no stored history, so no backtests, no
portfolio heat, no point-in-time fundamentals, and market breadth is unavailable
(the regime falls back to an index-only reading, which is stated in the response).

Local-only tools — `get_portfolio`, `build_portfolio_plan`, `get_universe` — say
so explicitly instead of degrading into something less accurate.

## Running it

```bash
pip install -r mcp-server/requirements.txt   # needs mcp>=2.0
# the tools read the advisor's local database, so populate it first:
cd stock-advisor && bash run_live.sh --backfill
```

One command configures **both** Claude Code and Claude Desktop with correct
absolute paths for this machine:

```bash
python mcp-server/setup_mcp.py            # print the config and where it goes
python mcp-server/setup_mcp.py --write    # merge into both, backing up originals
```

`--write` preserves any other MCP servers and unrelated settings already in
those files. Restart both clients afterwards.

Then ask in plain language: *"What does the advisor say about SUNPHARMA?"* — the
model calls `get_verdict`, and answers from the returned figures with citations,
because the envelope leaves it nothing to invent.
