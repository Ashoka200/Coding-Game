# 05 — Technical Analysis & Trend (practitioner doctrine, testable subset only)

Technicals answer *when* and *at what risk*, never *what quality*. Everything here is
mechanically computable and was chosen because it survives backtesting; folklore
patterns that can't be coded objectively are excluded.

## Trend identification (the primary filter)

- **Stage analysis (Weinstein):** Stage 1 base → Stage 2 advance → Stage 3 top →
  Stage 4 decline. Longs only in Stage 2: price > 200SMA, 200SMA rising, sequence of
  higher highs/lows. Stage 4 names are untouchable for longs at any "cheapness."
- Trend strength: ADX > 20 for trend-following entries; 20/50/200 EMA alignment
  (each above the next) defines an established uptrend.
- **Relative strength vs Nifty 500** (Levy/IBD-style RS percentile): buy candidates
  from the top quartile; RS breaking down before price is an early warning.

## Setups the system recognizes (each fully specified for the engine)

1. **Base breakout:** ≥ 6-week consolidation with contracting range and declining
   volume, breakout on ≥ 1.5× 50-day avg volume. Entry: breakout close or next-day
   follow-through; stop below base low or 2×ATR, whichever is nearer.
2. **Pullback in trend:** Stage 2 stock retraces to rising 20/50EMA zone on shrinking
   volume, resumes with a reversal bar. Stop below the pullback swing low.
3. **52-week-high momentum:** new high with RS ≥ 80th percentile and volume
   confirmation (anchoring makes fresh highs under-bought — a documented anomaly).
4. **Mean-reversion (quality only):** fundamentally scored ≥ 70 stock, RSI(2) < 10
   above a rising 200SMA — short-holding-period bounce; strictly the trading sleeve,
   strict time stop (5 sessions).

## Confirmation & context filters

- Volume must confirm: breakouts without volume expansion fail disproportionately.
- **Market regime filter:** new trading longs only when Nifty 500 > its 200SMA and
  breadth (% of universe above 200SMA) > 40%. In risk-off regimes the sleeve sits in
  cash — most breakouts fail in downtrends; the regime filter is worth more than any
  entry pattern.
- Earnings dates: no new swing entries within 5 sessions before results (gap risk
  can't be stopped).

## Levels (how entry/stop/target numbers are produced)

- Support/resistance from swing-point clustering (fractal highs/lows, ≥ 2 touches),
  prior base tops (polarity flip), and anchored VWAP from major pivots/IPO.
- Round numbers and 52w extremes acknowledged as behavioral magnets.
- Targets: measured move (base depth projected), prior structural levels, and R
  multiples; report the *nearest* of these honestly rather than the most exciting.

## What is deliberately excluded

- Elliott waves, Gann, harmonic patterns, Fibonacci as a primary signal — either
  unfalsifiable or no robust evidence; excluded to keep every rule testable.
- Indicator soups: two momentum oscillators saying the same thing is one signal.
- Intraday signals: this system trades daily/weekly timeframes only.

## Candlestick/price-action vocabulary (context, never standalone)

Reversal bars (hammer/engulfing at a tested level), inside-bar contractions, and wide
range breakout bars are used as *entry triggers within a qualified setup* — a hammer
in a Stage 4 downtrend is noise and the system says so.
