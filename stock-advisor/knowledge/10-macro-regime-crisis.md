# 10 — Macro Regime & Crisis Intelligence (the "super-intelligent mode")

Job: auto-recognize recessions, panics, pandemics and geopolitical shocks *as they
develop*, switch the whole system into the matching playbook — defend the existing
book, then hunt the opportunities every crisis creates.

Honest doctrine first: nobody — human or machine — reliably predicts crises in
advance. What a veteran does, and what this module encodes, is **recognize regime
change early from measurable stress, act by pre-committed playbook instead of
emotion, and buy systematically when others are forced sellers.** Recognition +
playbooks beat prediction.

## 10.1 Regime detection engine (computed daily, no LLM involved)

Signals, each scored, combined into a regime state machine:

**Market-internal stress (fastest):**
- Index drawdown depth AND speed (−10% in ≤10 sessions = shock signature vs slow grind)
- India VIX level and percentile (>25 elevated, >35 panic); term structure inversion
- Breadth collapse: % of NSE 500 above 200SMA (<25% = washout), advance-decline
- Correlation spike: average pairwise correlation of holdings >0.7 (indiscriminate selling)
- FII flows: 20-day cumulative net vs history

**Macro-economic (slower, confirms):**
- Yield curve (10y−1y G-Sec, and US 10y−2y), credit spreads (AAA vs G-Sec, CP rates)
- USDINR velocity (rapid depreciation = external stress), Brent (India's fiscal Achilles heel)
- PMI (mfg + services) below 50, GST collections growth, IIP trend, bank credit growth
- US: initial claims trend, ISM, Fed policy direction (global risk appetite driver)

**Regime states:** `EXPANSION → CAUTION → STRESS → CRISIS → RECOVERY`, with dwell
rules (no state flapping; 2 confirming signals to escalate, sustained absence to
de-escalate). Each state changes system behavior mechanically (below).

## 10.2 News & world-event intelligence layer (LLM's real job here)

Daily pipeline: ingest headlines/feeds (global wires, RBI/SEBI/GoI releases, earnings
warnings) → Claude classifies each into an event taxonomy with a structured impact
assessment:

- Taxonomy: monetary policy / fiscal / geopolitical-conflict / pandemic-health /
  financial-contagion / commodity shock / regulatory / trade-tariff / domestic-political
- For each material event: transmission channel to Indian equities (rates? oil? exports?
  flows? specific sectors?), affected holdings/watchlist names, historical analog
  ("this rhymes with 2013 taper / 2018 IL&FS / 2020 COVID"), estimated
  severity × persistence, and a confidence level.
- Output: a daily **World → Portfolio impact brief**, and immediate alerts when an
  event pattern-matches crisis precursors.
- Anti-noise doctrine: news *raises hypotheses*; only the indicator engine *confirms
  regimes*. The system never goes risk-off on headlines alone — headlines without
  market-stress confirmation are logged, not acted on. (Most scary headlines mean
  nothing; every real crisis also shows up in prices and credit within days.)

## 10.3 Lessons library — what each crisis teaches (drives the playbooks)

- **2008 GFC:** credit spreads led equities; leverage kills; correlations →1 so only
  cash/G-Secs hedged; quality fell 40% too — and repaid buyers 3–5× over 5 years.
  Lesson: survival first, then buy quality indiscriminately sold.
- **2013 taper tantrum:** India-specific vulnerability = twin deficits + INR; exporters
  (IT/pharma) were the hiding place. Lesson: in external-account crises, rotate to
  USD earners, avoid leveraged financials/infra.
- **2016 demonetization:** liquidity shock to cash-economy sectors (NBFC, realty,
  consumer discretionary) — sharp but temporary; formalization winners emerged.
  Lesson: classify shocks temporary vs structural before selling.
- **2018 IL&FS / NBFC crisis:** contagion via funding channels; CP/CD spreads were the
  tell. Lesson: monitor funding-market plumbing, not just equity prices; avoid
  borrow-short-lend-long models in tightening cycles.
- **2020 COVID:** fastest crash ever (−38% in 5 weeks) and fastest recovery (policy
  flood). Selling after the crash was the costliest move; staged buying through the
  panic and holding through volatility won. Digital/pharma re-rated; travel took years.
  Lesson: crash speed ≠ recession depth when policy responds; pre-committed staged
  deployment beats waiting for "clarity" (clarity arrives at +40%).
- **2022 inflation/rate shock:** long-duration growth stocks de-rated most; value/
  commodities defended. Lesson: in rate shocks, valuation duration is the risk axis.
- **Recurring meta-lessons:** every crisis bottoms on forced selling + policy response,
  not on good news; breadth washouts (<15–20% above 200SMA) mark generational entry
  zones; the sectors that led the prior bull rarely lead the next.

## 10.4 Playbooks (pre-committed, state-triggered)

**CAUTION** (e.g. curve flattening, breadth divergence, VIX rising):
- New-position sizing −25%; raise quality bar; no new leverage-sensitive names;
  refresh the pre-mortem on every holding; build the crisis shopping list *now*.

**STRESS** (drawdown >10% with confirming macro signals):
- Trading sleeve → mostly cash (regime filter already forces this); no new swing longs.
- Investing book: sell the pre-identified weakest holdings (governance flags, leverage,
  thesis already wobbly) — not the whole book; consider index-put/collar hedge
  (module 07) sized to IPS drawdown tolerance.
- Activate staged-deployment schedule for reserves: e.g. deploy 20% of cash at −15%
  index, 30% at −25%, 30% at −35%, hold 20% for beyond (levels pre-committed in writing).

**CRISIS** (panic signatures: VIX >35, breadth <20%, correlation ~1):
- No panic selling of quality — the sell decision was CAUTION/STRESS's job; too late now.
- Execute the deployment schedule mechanically into the **crisis shopping list**:
  highest-quality names (module 02 score >75, low leverage, governance clean) at
  bear-case valuations; prefer survivors with balance-sheet strength to buy competitors.
- Harvest tax losses into equivalent exposures; roll hedges down; journal everything.

**RECOVERY** (breadth thrust: >55% above 50SMA from washout, credit spreads narrowing,
policy easing):
- Breadth thrusts off washouts are the highest-conviction long signal this system has;
  redeploy remaining reserves, rebuild trading sleeve, tilt toward new leadership
  (watch what makes 52w highs first off the low — next cycle's leaders).

**Pandemic/geo-shock addendum:** classify sector impact by transmission (mobility?
supply chains? energy? defense?), separate temporary-hit-strong-balance-sheet names
(buy list) from structurally-impaired ones (avoid regardless of cheapness).

## 10.5 Outputs to the user

- Daily: regime state + dashboard, world-impact brief (only material items).
- On state change: full alert — what triggered it, playbook now active, exact actions
  proposed for *this* portfolio (with the pre-committed levels).
- Always framed: "here is what history says, here is the plan we committed to when
  calm — the system's job in a crisis is to be the calmest thing you own."
