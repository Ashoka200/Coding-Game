# 06 — Quantitative Factors (the systematic edge library)

The five factor premia with decades of academic and practitioner evidence, adapted to
India. These drive the screener's ranking mathematics.

## The factor library

1. **Value:** cheap beats expensive on average, with long droughts. Metrics: earnings
   yield (E/P), EV/EBITDA, P/B (financials), FCF yield. Composite z-score across
   metrics within sector (raw cross-sector value comparisons just buy the worst sectors).
2. **Momentum:** 12-month-minus-1-month return (12-1) — winners persist ~3–12 months.
   The strongest documented anomaly, including in India (well-supported in NSE data).
   Crash risk: momentum reverses violently at bear-market turns — the regime filter
   (module 05) and volatility scaling are the standard mitigants.
3. **Quality:** high ROE/ROCE, stable margins, low accruals, low leverage. Pays most
   in downturns; the natural pairing with value ("quality at a reasonable price"
   beats deep value in India, where cheap often means governance-broken).
4. **Low volatility:** low-beta/low-vol stocks earn better risk-adjusted returns than
   theory predicts. Used for the core book's defensive sleeve, not for alpha ranking.
5. **Size:** small beats large on average but with brutal liquidity and drawdown
   costs — treated as a risk to manage (liquidity caps, module 04), not an edge to chase.

## How the screener uses factors

- Each stock gets sector-neutral z-scores per factor, winsorized at ±3.
- **Investing book ranking:** 0.4×Quality + 0.35×Value + 0.25×Momentum
  (momentum included even for investors — it prevents buying value traps early).
- **Trading book ranking:** 0.6×Momentum + 0.25×Quality + 0.15×Value.
- Factor scores are recomputed monthly; ranks are stable by construction (turnover
  control: a holding is sold only when it drops below the 40th percentile, not the
  moment it leaves the top decile — hysteresis cuts churn and tax).

## Factor regimes and honest limits

- Every factor has multi-year droughts (value 2017–2020 globally). The system reports
  rolling factor performance in India but does **not** aggressively time factors —
  factor timing has a poor track record; diversification across factors is the
  defensible choice. Mild tilt allowed: reduce momentum weight when index is below
  200SMA (documented momentum-crash regime).
- Backtest discipline for any new factor idea (the quant researcher's oath):
  point-in-time data (no survivorship — include delisted stocks), realistic costs
  (India: STT + impact, assume ≥ 0.3–0.5% round trip in mid-caps), out-of-sample
  validation, and a pre-registered hypothesis. A backtest tuned until it works is a
  curve-fit, and the system labels any result from < 10 years of data as provisional.

## Market-regime dashboard (context layer, not a timing system)

Computed daily, shown with every report: index vs 200SMA, % universe above 200SMA
(breadth), advance-decline trend, India VIX level/percentile, FII/DII net flows
(20-day), yield-curve and credit-spread direction. Regime affects *pacing and sizing*
(module 03/04), never binary in/out calls.
