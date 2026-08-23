# What the professionals use — and what this system implements

Research summary (Aug 2026) mapping the institutional and Indian pro toolchain to
this codebase. The pattern across every desk: **data terminal → analytics/risk
platform → execution/alerts**, with risk as a platform, not a feature.

## Wall Street / institutional

| Platform | What it does for a desk | Our analog |
|---|---|---|
| **Bloomberg Terminal** (~325k seats) | Data + news + analytics + chat; risk modeling, performance attribution, multi-portfolio views | Data layer (dual-source EOD, point-in-time fundamentals) + digest + AI news layer (module 10) |
| **FactSet** | Deep fundamentals, multi-asset portfolio analytics, Excel workflow | `fundamentals.py` scoring + `factors.py` composite ranks |
| **BlackRock Aladdin** ($20tn+ administered) | The lesson that matters: risk is the *platform* — every position seen through VaR, stress, factor exposures daily | `risk.py`: shrinkage covariance, VaR/CVaR, crisis stress replay, correlation diagnostics — run on YOUR book daily |
| Quant desks (kdb+/tick stores, walk-forward validation culture) | Never trust one backtest; validate across regimes | `walkforward.py` + costed worst-case-fill backtester |

## Indian pro/retail stack

| Tool | Loved for | Our analog |
|---|---|---|
| **Screener.in** | 10y fundamentals, custom query screens | fundamental scorer + screener presets |
| **Trendlyne** | DVM composite (Durability/Value/Momentum), institutional-holding trends | `factors.py` sector-neutral V/Q/M/low-vol composite (same idea, ours is transparent and backtestable) |
| **Sensibull / Quantsapp** | Options: payoff graphs, max pain, IV analytics | `fno.py` Greeks/IVP + defined-risk selector |
| **TradingView** | Charting + broker integration | Streamlit dashboard (charts); execution stays manual by design |
| **Zerodha Streak** | Rule-based algo without code | Our setups ARE the rules — plus journal + calibration they don't have |
| StockEdge / Tickertape | Mobile screeners, portfolio analysis | digest + Telegram push (`notify.py`) |

## The three lessons taken, one deliberately rejected

1. **Aladdin's lesson (taken):** risk analytics run on the whole portfolio every
   day, not on trades at entry. → `advisor.cli risk` is now a first-class daily
   command: VaR in rupees, expected shortfall, crisis-scenario losses, and a
   diversification-illusion check.
2. **Quant-desk lesson (taken):** a strategy is only believed after it survives
   walk-forward validation across regimes. → `advisor.cli walkforward`.
3. **Terminal lesson (taken):** information that doesn't reach you in time is
   worthless — push, don't pull. → Telegram delivery of the nightly digest.
4. **Rejected:** black-box scores and signal-selling (much of the retail AI-tools
   market). Every number this system produces traces to a formula in this repo
   that you can read, test, and challenge. That transparency is the actual edge
   a personal system has over a subscription.

Sources: [Daloopa — hedge fund analytics platforms](https://daloopa.com/blog/analyst-best-practices/best-investment-analytics-and-performance-software-for-hedge-funds) ·
[Hebbia — investment research software 2026](https://www.hebbia.com/resources/investment-research-software) ·
[Bloomberg Terminal explained](https://www.comstock-interactivedata.com/bloomberg-terminal-explained/) ·
[Bloomberg vs FactSet comparison](https://pro.stockalarm.io/blog/best-financial-terminals-comparison) ·
[Wall Street Fintech on Aladdin](https://wallstreetfintech.substack.com/p/jody-kochansky-building-the-operating) ·
[Univest — best stock analysis apps India 2026](https://univest.in/blogs/best-stock-analysis-app-india-2026-top-7-picks-for-research-screeners-amp-advisory) ·
[KnowYourBrokerage — Indian tools directory](https://knowyourbrokerage.in/tools) ·
[Winvesta — fundamental screeners India](https://www.winvesta.in/blog/investors/fundamental-analysis-tools-and-screeners-2026-guide)
