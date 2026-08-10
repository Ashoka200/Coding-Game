# 360° Stock Investor Advisory — Build Plan (Indian Markets)

An AI-assisted decision-support system for personal portfolio management on NSE/BSE:
stock scouting, fundamental + technical + chart analysis, entry/exit price suggestions,
position sizing, and portfolio tracking — for long-term investing, swing trading, and
(later, optionally) futures & options.

---

## 0. Honest framing (read this first)

- **No system predicts prices.** What we can build is a system that *ranks opportunities,
  quantifies risk, and enforces discipline*. The edge comes from consistency and risk
  management, not from a magic signal.
- **Entry/exit levels are risk-management constructs**, not predictions: entries near
  support/value zones, stops sized by volatility (ATR), targets by reward:risk ratio.
- **F&O is deliberately last.** SEBI's own study found ~90% of retail F&O traders lose
  money. The system should master cash-market analysis and paper-trade F&O strategies
  before any real derivatives exposure.
- **Regulatory note:** for personal use this is fine. Giving buy/sell recommendations to
  *others* (even friends, via a shared app) falls under SEBI Investment Adviser /
  Research Analyst regulations. Keep it personal.
- **Everything gets backtested and paper-traded before real money.**

---

## 1. System architecture

```
┌────────────────────────────────────────────────────────────┐
│                     Data Layer (daily jobs)                │
│  EOD prices · Fundamentals · Corporate actions · Indices   │
│  F&O bhavcopy · News/filings · FII/DII flows               │
└───────────────┬────────────────────────────────────────────┘
                │  SQLite/Postgres + Parquet cache
┌───────────────▼────────────────────────────────────────────┐
│                    Analysis Engines                        │
│  1. Fundamental scorer   2. Technical/trend engine         │
│  3. Chart pattern detector  4. Relative strength vs Nifty  │
│  5. Risk & position sizing  6. (later) Options analytics   │
└───────────────┬────────────────────────────────────────────┘
                │  structured scores & levels (JSON)
┌───────────────▼────────────────────────────────────────────┐
│              AI Synthesis Layer (Claude API)               │
│  Merges all engine outputs into a 360° narrative report    │
│  with a conviction score, entry zone, stop, targets, size  │
└───────────────┬────────────────────────────────────────────┘
                │
┌───────────────▼────────────────────────────────────────────┐
│        Interface: Streamlit dashboard + daily digest       │
│  Watchlist · Screener results · Portfolio · Alerts         │
└────────────────────────────────────────────────────────────┘
```

Key principle: **the math lives in deterministic Python engines; the LLM only
synthesizes and explains.** Never ask an LLM to compute an RSI or a fair value — it
will hallucinate. Feed it computed numbers, let it write the 360° view.

## 2. Data sources (India-specific)

| Data | Free option | Paid/robust option |
|---|---|---|
| EOD prices NSE/BSE | NSE bhavcopy (official daily CSV), `yfinance` (`RELIANCE.NS`) | Broker APIs (Zerodha Kite Connect ₹2k/mo, Upstox free, Angel One SmartAPI free) |
| Intraday/live | Broker API websocket (free with account) | TrueData, Global Datafeeds |
| Fundamentals | NSE/BSE filings, screener.in exports, Tijori | Financial data vendors (CMIE, Ace Equity) |
| Corporate actions | NSE corporate actions feed | broker APIs |
| F&O chain, OI | NSE option-chain endpoint, F&O bhavcopy | broker APIs |
| FII/DII flows | NSE/BSE daily reports | — |
| News/announcements | NSE announcements RSS, Google News | paid news APIs |

Recommendation: **start with NSE bhavcopy + yfinance + screener.in exports** (all free),
and open a broker API (Upstox/Angel One are free) when you want live quotes and later
order placement. NSE endpoints need polite scraping (headers, throttling) and break
occasionally — build the ingestion layer with retries and a local cache so analysis
never depends on a live fetch.

## 3. Analysis engines

### 3.1 Fundamental scorer (long-term leg)
- Ratios: ROE/ROCE (>15% filter), debt/equity, interest coverage, OPM trend,
  sales & profit CAGR (3y/5y), cash-flow vs profit divergence (earnings quality),
  promoter holding & pledging trend.
- Valuation: P/E and EV/EBITDA **vs own history and sector median** (not absolute),
  PEG, earnings yield vs 10y G-Sec.
- Composite: Piotroski F-Score + a custom 0–100 quality/valuation/growth score.
- Red-flag detector: pledging spikes, auditor changes, receivables ballooning,
  frequent equity dilution.

### 3.2 Technical / trend engine (timing leg)
- Trend: 20/50/200 EMA structure, higher-highs/higher-lows, ADX.
- Momentum: RSI, MACD, 52-week-high proximity, volume confirmation.
- Volatility: ATR (feeds stops and position sizing), Bollinger width.
- Levels: swing-based support/resistance, anchored VWAP, gap zones.
- Relative strength vs Nifty 50 / sector index — only buy leaders.

### 3.3 Chart pattern detector
- Start rule-based (breakouts from N-day ranges, flat bases, cup-with-handle
  approximations, volume dry-up) — these are testable. Skip ML pattern recognition
  initially; it's low signal-to-noise and hard to validate.

### 3.4 Scout / screener
- Universe: NSE 500 (liquidity floor: min avg daily turnover).
- Preset scans: "quality compounders at fair value" (investing),
  "momentum leaders in uptrend" (swing), "52w-high breakouts with volume",
  "oversold quality" (mean reversion).

### 3.5 Entry / exit / sizing (the numbers you asked for)
For each candidate the system outputs:
- **Entry zone**: e.g. breakout level, or pullback-to-20EMA/support zone — a range, not a point.
- **Stop-loss**: structure-based (below swing low) validated against 1.5–2× ATR.
- **Targets**: T1 at 1.5R, T2 at 2.5–3R, plus trailing rule (e.g. 20EMA exit for trends).
- **Position size**: fixed-fractional risk — `shares = (capital × risk%) / (entry − stop)`,
  with risk% = 0.5–1% per trade for trading, and max 5–8% capital per position and
  25–30% per sector for the investing book.
- **Conviction score** 0–100 combining fundamental, technical and RS scores, weighted
  differently per mode (investing: 70/20/10; swing: 20/60/20).

### 3.6 AI synthesis layer
- Claude API call per shortlisted stock: receives all engine JSON + recent
  announcements, returns the 360° report — bull case, bear case, what would
  invalidate the thesis, and a plain-English rationale for the levels.
- The call's system prompt is assembled from the **knowledge layer**
  (`knowledge/` — CFA-curriculum and quant-PM doctrine modules 01–09), so the AI
  analyzes with a fixed institutional methodology rather than ad-hoc reasoning.
  The knowledge modules are also the specification the Python engines implement.
- Also a daily portfolio review: "what changed, what needs action."

### 3.7 F&O module (Phase 5 only)
- Options chain analytics: IV vs historical IV percentile, OI buildup, PCR, max pain.
- Strategy suggester restricted to *defined-risk* structures (spreads, covered calls
  against holdings) — never naked short options.
- Futures only as a hedging overlay on the portfolio, not standalone speculation.

## 4. Tech stack

- **Python** end-to-end: `pandas`, `numpy`, `pandas-ta` (indicators), `yfinance`/`nsepython`.
- **Backtesting**: `vectorbt` (fast screens) or `backtrader` (event-driven realism).
- **Storage**: SQLite to start (upgrade to Postgres if needed) + Parquet for price history.
- **Dashboard**: Streamlit (fastest path to a usable UI) with Plotly candlestick charts.
- **Scheduler**: cron — 6:30 PM IST job after bhavcopy publishes; digest by 8 PM.
- **LLM**: Claude API (`claude-sonnet-5` for nightly batch reports, `claude-fable-5`/Opus
  for deep-dive single-stock analysis).

## 5. Phased roadmap

| Phase | Scope | Outcome |
|---|---|---|
| **1. Data foundation** (wk 1–2) | Ingest EOD prices + fundamentals for NSE 500 into SQLite; nightly refresh job | Clean queryable dataset |
| **2. Engines + screener** (wk 3–5) | Fundamental scorer, technical engine, RS ranking, preset scans | Daily ranked shortlists |
| **3. Levels + AI reports** (wk 6–7) | Entry/stop/target/size calculator; Claude 360° report; Streamlit dashboard | The actual advisory output |
| **4. Backtest + portfolio** (wk 8–10) | Backtest the scan+level rules on 5–10y data; portfolio tracker; alerts (price/stop/result dates) | Evidence the rules work; live tracking |
| **5. Paper trading** (2–3 mo) | Log every system suggestion vs outcome; tune weights | Trust, calibrated |
| **6. F&O module** (only after 5) | Options analytics, defined-risk strategies, hedging | Derivatives support |
| **7. Optional: execution** | Broker API order placement with manual confirm | One-click acting on signals |

## 6. What I'd explicitly avoid

- ML price prediction models (LSTM etc.) — endless effort, negligible real edge at EOD retail scale.
- Intraday trading automation as an early goal — infrastructure-heavy, edge-poor.
- Trusting any single data source — cross-validate prices between bhavcopy and broker API.
- Letting the LLM generate numbers — it explains; the engines compute.
- Skipping backtesting/paper trading — the phases are ordered this way on purpose.
