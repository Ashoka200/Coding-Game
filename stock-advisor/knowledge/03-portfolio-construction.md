# 03 — Portfolio Construction (CFA L3 + quant practice)

## Structure: core–satellite

- **Core (50–70% of equity book):** index funds / 15–25 quality compounders held for
  years. Low turnover; the compounding engine.
- **Satellite (20–40%):** active high-conviction picks from the screener.
- **Trading sleeve (≤10–15%):** swing trades under module 05 rules; its max drawdown
  is capped so it can never sink the ship.

## Diversification — the only free lunch, used correctly

- 15–25 stocks captures most idiosyncratic-risk reduction; beyond ~30 is closet
  indexing with extra cost.
- Diversify by **risk driver**, not by count: an IT + a bank + an FMCG name diversify;
  five NBFCs do not. Track pairwise correlation of holdings (rolling 1y, weekly returns).
- Limits: single position ≤ 8% at cost / 15% at market (trim rule beyond), sector ≤ 25%,
  single risk theme (e.g. "rural consumption", "US rate cycle") ≤ 35%.

## Modern Portfolio Theory — used with adult supervision

- Mean-variance optimization is hypersensitive to expected-return inputs (garbage in,
  optimal garbage out). The system does **not** run naive Markowitz on historical means.
- Usable descendants:
  - **Risk-based weighting:** inverse-volatility or equal-risk-contribution across
    satellite picks — needs only the covariance matrix (estimable), not returns.
  - **Black-Litterman intuition:** start from market/index weights as equilibrium,
    tilt only where the system has an explicit, scored view; tilt size proportional
    to conviction × confidence.
- Covariance estimated with Ledoit-Wolf shrinkage on 1–2y weekly returns.

## Rebalancing (CFA L3 corridor method)

- Bands, not calendar: rebalance an asset class when it drifts ±20% relative (e.g. 60%
  equity target → act at 48%/72%). Check monthly, act rarely.
- Within equity: trim positions crossing max-weight; recycle into highest-scoring
  underweights. In India, harvest LTCG thoughtfully (see module 09 for tax).
- Rebalancing is the mechanism that enforces buy-low/sell-high without forecasting.

## Performance measurement (what "am I doing well" means)

- Benchmark: Nifty 500 TRI (total return — never price index; dividends matter).
- Metrics computed quarterly: XIRR vs benchmark, Sharpe, Sortino, max drawdown,
  hit rate and slugging ratio (avg win/avg loss), and **Brinson-style attribution**:
  how much came from allocation vs selection vs the trading sleeve.
- Rolling 3y underperformance of the satellite book vs core triggers a strategy
  review — the honest exit from overactive management.

## Cash as a position

- Trading sleeve holds cash when no setups qualify — no forced trades.
- Investing book stays near fully invested (timing the market costs more than it
  saves), but incoming capital is staged in on a schedule or on drawdowns, not lump
  summed at euphoric breadth readings (module 06 regime signals inform pacing only).
