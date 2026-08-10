# Extended Roadmap — Phases 8–10 (added by owner's request)

These were originally excluded as "cost without edge at this stage." Owner has opted
in, so they are added here *properly* — each with its real prerequisites, costs, and
the engineering shape that gives it a chance of working. Sequencing rule: none of
these begin until Phases 1–5 of the core BUILD-PLAN are live and the paper-trading
scoreboard has at least one full quarter of data (the ML phase literally consumes
that data; the others depend on infrastructure Phases 1–5 create).

## Phase 8 — Machine learning layer

Spec lives in `knowledge/11-ml-quant-research.md`. Summary: cross-sectional ranking
(LightGBM over factor features) → meta-labeling of the system's own signals → learned
regime classification. Purged walk-forward validation, costs-in-label, deflated-Sharpe
baseline test, 2-quarter paper gate. **Explicitly out:** end-to-end price prediction
and RL traders — not "later," but never, unless the evidence standard in module 11 is
met by some future approach.

- Deliverables: `advisor.ml` package (feature store, purged CV harness, model
  registry), monthly rank file consumed by the screener, model scorecard page.
- Extra deps: lightgbm, scikit-learn, shap.

## Phase 9 — Intraday module

Honest cost sheet first: intraday is a different sport — colocation-adjacent players,
STT drag on churn, and decisions at a cadence humans shouldn't emotionally follow.
The defensible retail version is **narrow**:

1. **Execution quality (the real win):** for signals the daily system already
   generated, an intraday executor works the order — VWAP/TWAP slicing, opening-range
   avoidance, limit-ladder entries near planned levels. This measurably saves basis
   points on every trade regardless of any alpha. Built first.
2. **Event-window monitor:** live alerting when a holding gaps/circuits or a regime
   alert fires mid-session (act-by-playbook, not new signals).
3. **Intraday strategies (optional, last, paper-first):** at most 1–2 well-studied
   setups (e.g. opening range breakout on index futures) run at tiny size as an
   experiment with its own journal — treated as R&D, funded like a hobby, capped at
   1% of capital.

- Prerequisites: broker API with websocket feed (Upstox/Angel One), tick storage
  (DuckDB/Parquet), latency-tolerant design (retail = seconds, and that's fine for
  execution use).

## Phase 10 — Multi-user platform

**Legal gate before code:** advising others for consideration — or even structuring
free recommendations to the public — triggers SEBI Investment Adviser (2013) /
Research Analyst (2014) registration: exams (NISM XA/XB or XV), net-worth and
record-keeping requirements, audits. Two lawful shapes:

- **Household mode (near-term, low-risk):** multiple portfolios (self, spouse,
  parents/HUF) under one roof — separate IPS per person, separate journals, shared
  data layer. This is most of the real value of "multi-user" with none of the
  regulatory burden, and it is the version this phase builds by default.
- **Product mode (only with registration):** auth, per-user data isolation,
  suitability assessment (mandated), disclosure documents, grievance process, audit
  logs. Engineering is the easy half; compliance is the product. Not started without
  an RIA/RA registration decision made deliberately, with professional advice.

- Deliverables (household mode): user/portfolio tables keyed into journal + holdings,
  per-IPS constraint engine, per-user digests.

## Additional knowledge modules (continuous, not a phase)

The knowledge layer stays open: candidates queued — special situations (demergers,
buybacks, delisting arbitrage), IPO analysis doctrine, commodity/currency context,
fixed-income & G-Sec allocation, REIT/InvIT analysis. Rule from `knowledge/README.md`
still applies: a module is added only when it changes a decision the system makes,
and every addition ships with the engine change that uses it.
