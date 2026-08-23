# 11 — Machine Learning in Quant Finance (doing it the way that survives contact)

Added by owner's request. Doctrine: ML has a real place in this system — but the
naive version (feed prices to an LSTM, predict tomorrow) is the single most common
way quants burn years. Financial data is nearly all noise (signal-to-noise far below
any domain ML succeeded in), non-stationary (the game changes), and tiny (a few
thousand daily observations, not millions). This module encodes the practitioner
playbook (López de Prado school) for the ML that *does* work.

## Where ML earns its keep here (in deployment order)

1. **Cross-sectional ranking (first, highest value):** gradient-boosted trees
   (LightGBM/XGBoost) over the module-06 factor features to rank stocks by expected
   relative 1–3 month performance. Not "will it go up" — "which of these 500 will do
   better than the median." Cross-sectional prediction is materially easier than
   time-series direction, and it slots directly into the existing screener.
2. **Meta-labeling (second, best risk-adjusted payoff):** keep the module-05 setups
   as the primary signal; train a classifier to predict *which of the system's own
   signals succeed*, using regime features, volatility, liquidity, breadth. The model
   sizes/filters trades rather than generating them — errors are bounded by the
   rule-based system underneath.
3. **Regime classification (third):** learned regime states (HMM or trees on the
   module-10 indicators) as a cross-check on the hand-built state machine.
4. **NLP feature extraction:** Claude already does this (news taxonomy, filings tone);
   its structured outputs become features for models 1–3.

**Not sanctioned:** end-to-end price-level prediction (LSTM/transformer on raw
prices), reinforcement-learning traders, and any model whose edge cannot be
explained in one sentence of financial logic. If the edge has no economic rationale,
it is overfit noise wearing a lab coat.

## The validation gauntlet (every model passes all of it or ships nowhere)

- **Purged walk-forward CV with embargo:** ordinary k-fold leaks future into past via
  overlapping labels; purge overlapping samples, embargo adjacent periods.
- **Point-in-time features only** (the Phase-1 fundamentals store exists for this);
  universe = survivorship-free (delisted names included — the `stocks` table keeps them).
- **Costs in the label:** returns net of STT + slippage estimates; a model that only
  works gross of costs is a donation schedule to the exchange.
- **Baseline test:** must beat the plain module-06 factor composite out-of-sample by
  a margin that survives multiple-testing correction (deflated Sharpe). Complexity
  that ties the baseline loses to the baseline.
- **Feature count discipline:** tens of features, not thousands; SHAP importances
  must make financial sense; any feature whose sign flips across folds is dropped.
- **Paper period:** 2 quarters of live paper predictions logged in the journal before
  the model influences a single rupee of sizing.

## Ongoing operation

- Retrain on a fixed calendar (quarterly), never on drawdown-triggered panic retunes.
- Monitor live-vs-backtest performance decay; a model 2σ below its OOS expectation
  for 2 quarters is retired to paper status automatically.
- Every model version is journaled like a decision: hypothesis, training window,
  OOS results, live results — so model selection itself gets a calibration loop.
