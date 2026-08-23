# 04 — Risk Management (the module that vetoes everything else)

## Position sizing — the most important formula in the system

**Fixed-fractional risk:** `shares = (equity × risk_per_trade) / (entry − stop)`

- Trading sleeve: risk 0.5–1.0% of total equity per trade. Never more.
- Investing book: position size from conviction tiers (3% starter / 5% standard /
  8% max at cost), built in tranches, not all at once.
- **Kelly criterion** is computed for reference (`f* = W − (1−W)/R`, W = hit rate,
  R = avg win/loss) but the system always sizes at ≤ quarter-Kelly — full Kelly
  assumes known probabilities and tolerates 50%+ drawdowns; nobody's estimates
  deserve full Kelly.

## Portfolio heat & drawdown control

- **Open heat** = sum of (position size × distance to stop) across the trading sleeve;
  capped at 5% of equity. New trades blocked when at cap.
- **Drawdown governor:** at −10% sleeve drawdown, risk per trade halves; at −15%,
  trading pauses for review. This converts an equity curve into a survivable one.
- Max portfolio drawdown tolerance from the IPS (e.g. 25%) maps back to equity
  allocation — if a 40% equity crash would breach it, equity weight is too high.

## Value at Risk — used for awareness, not worship

- Parametric and historical 1-month 95% VaR computed on the whole portfolio; reported
  in ₹ ("normal bad month ≈ ₹X"). Expected Shortfall (CVaR) alongside, since VaR says
  nothing about the tail beyond it.
- Stress tests > VaR: replay the portfolio through 2008, 2013 taper, 2020 COVID crash,
  and a sector-specific shock (e.g. financials −30%). Report worst outcome and which
  positions drive it.

## Correlation & concentration risk

- Rolling correlation matrix of holdings; flag when average pairwise correlation of
  the book > 0.6 (diversification illusion — one trade wearing 20 tickers).
- Correlations converge to 1 in crashes: stress tests assume it; sizing never counts
  on diversification that disappears when needed.

## Liquidity risk (acute in Indian small/mid-caps)

- Position size also capped at ≤ 5× the stock's median daily traded value ÷ 20
  (i.e. exit within ~a week at ≤20% of volume without moving price).
- Circuit-limit names and ASM/GSM-listed stocks: reduced size or excluded.

## Stops & exits

- Stop = thesis invalidation, placed at structure (below swing low / base low),
  sanity-checked against 1.5–2× ATR(14) so normal noise doesn't trigger it. If the
  structural stop implies too-large risk, the position is smaller — never the stop wider.
- Investing book "stops" are fundamental: thesis-break events (governance flag,
  2 consecutive quarters contradicting thesis, pledging spike) trigger forced review
  with a default-to-exit bias; price alone doesn't exit the investing book, but a
  −20% position loss forces the review.
- Profit-taking: trading — scale out at 1.5R, trail remainder (20EMA or 2.5×ATR
  chandelier). Investing — trim on max-weight breach or valuation reaching bull case.

## The meta-rule

Any conflict between this module and any signal, score, or narrative resolves in
favor of this module. Risk management is not a input to the decision; it is the
boundary of the decision space.
