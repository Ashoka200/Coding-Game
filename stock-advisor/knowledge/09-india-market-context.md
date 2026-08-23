# 09 — India Market Context (the local knowledge layer)

Global doctrine, local execution. Everything above is adapted to NSE/BSE reality here.

## Market structure

- Sessions: 09:15–15:30 IST; T+1 settlement. Bhavcopy (official EOD) publishes evening.
- **Circuit limits:** 5/10/20% price bands on non-F&O stocks — stops can be
  ungappable; module 04's liquidity caps exist partly for this. Index-level circuit
  breakers halt the whole market (10/15/20%).
- **ASM/GSM surveillance frameworks:** stocks under Additional/Graded Surveillance
  have trading restrictions and 100% margin — the universe filter excludes GSM and
  deep ASM stages automatically.
- SME-board listings: separate liquidity/lot rules, manipulation-prone — excluded
  from the universe entirely.

## Regulatory (SEBI) facts the system must respect

- Personal use of this system is unregulated. Providing recommendations to others —
  even free, even a shared dashboard — falls under SEBI (Investment Advisers)
  Regulations 2013 / (Research Analysts) Regulations 2014. The system is single-user.
- Insider trading law (PIT Regulations): any analysis must use only public info;
  UPSI-adjacent "channel checks" culture is a legal minefield — public data only.
- F&O: lot sizes set by exchange (~₹15L+ notional per lot after 2024 SEBI reforms);
  weekly expiries now limited per exchange. Physical delivery on stock F&O expiry —
  never carry stock options to expiry ITM without intending delivery.

## Taxation (as of FY 2025–26 — re-verify each budget; changes frequently)

- Equity delivery: LTCG (>12m) 12.5% above ₹1.25L/yr exemption; STCG (≤12m) 20%.
- Tax-loss harvesting: legal and encouraged near March; the portfolio module surfaces
  candidates (book losses against realized gains; re-entry has no wash-sale rule in
  India — but re-buy timing is a market decision, not automatic).
- F&O and intraday: business income at slab rates, separate books; F&O turnover can
  trigger tax-audit thresholds. Delivery investing and F&O have *different tax
  characters* — factored into after-tax return comparisons.
- STT/costs: STT on delivery both sides (0.1%), higher effective drag on churn —
  another reason the factor engine (06) has turnover hysteresis. All backtests use
  after-cost, after-realistic-slippage returns.

## Flows & ownership context

- FII/DII daily net flows: 20-day trend is a regime input (module 06 dashboard).
  Persistent FII selling absorbed by DII/retail flows is the post-2020 structural
  pattern — flows are context, not signals.
- Promoter holding changes, pledge disclosures, bulk/block deals, and buyback/open
  offer events come from exchange disclosures — the governance engine (02) consumes
  these directly.

## India-specific analytical adjustments

- Governance risk premium: India's small/mid-cap value is contaminated by promoter
  misbehavior — hence quality-weighted value (module 06) and the hard governance
  veto (module 02).
- Sector composition: financials ≈ 30%+ of indices — sector caps (03) prevent the
  "diversified" portfolio that is actually one big rates bet.
- Monsoon/rural, government capex cycles, and election years are real earnings
  drivers for specific sectors — treated as thesis inputs for those names, never as
  market-timing tools.
- Currency: IT/pharma earn in USD; energy imports in USD — USDINR direction is a
  sector-rotation context input on the regime dashboard.
