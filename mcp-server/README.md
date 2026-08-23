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

No tool places an order. Order preparation stays in the CLI, behind explicit
human approval.

## Running it

```bash
pip install -r mcp-server/requirements.txt
# the tools read the advisor's local database, so populate it first:
cd stock-advisor && bash run_live.sh --backfill
```

**Claude Code** — add to `~/.claude/settings.json` (or the project's `.mcp.json`):

```json
{ "mcpServers": {
    "advisor": { "command": "python", "args": ["-m", "advisor_mcp.server"],
                 "cwd": "/absolute/path/to/Coding-Game/mcp-server",
                 "env": { "PYTHONPATH": "/absolute/path/to/Coding-Game/stock-advisor/src" } } } }
```

**Claude Desktop** — the same block in `claude_desktop_config.json`.

Then ask in plain language: *"What does the advisor say about SUNPHARMA?"* — the
model calls `get_verdict`, and answers from the returned figures with citations,
because the envelope leaves it nothing to invent.
