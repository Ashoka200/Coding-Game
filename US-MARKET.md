# The US desk

Two markets, one doctrine. The analysis engine does not care which country a
company trades in — widening margins and falling debt read the same in Mumbai
and New York. What differs is plumbing and law, and all of it lives in
`public/markets.js`. Adding a third market should mean adding an entry there,
not editing screens.

## What the research changed

**SEC EDGAR replaced everything else for fundamentals.** The India side scrapes
three sources and hopes one answers. The US has an official, free, keyless XBRL
API carrying every fact a company has ever filed — *with the filing date
attached to each number*.

That last part is the one institutions pay for. A figure can be used
**point-in-time**: as it was known on the day it was filed, rather than the
restated version visible today. Backtests built on restated fundamentals are the
classic way to discover an edge that never existed.

So on a US company page every number can name the 10-K it came from and the day
it was filed, and a stale filing is reported as stale.

The SEC asks for a User-Agent naming the app with a contact address, and under
10 requests a second. Both are honoured. Set `SEC_CONTACT` in the Netlify
environment to your own email.

## What Wall Street actually runs, and what was worth copying

Aladdin, Bloomberg PORT, FactSet and Axioma. Their common shape is not stock
picking — it is **position-level risk aggregated to the portfolio, with every
number traceable to a source**. That is the part worth copying at this scale,
and it is what the reasoning chain already does.

Deliberately not copied: real-time multi-asset risk aggregation, transaction cost
analysis and order management. They serve a mandate and a compliance department;
one investor with a demat account has neither.

## Sources

| Need | Source | Key? |
|---|---|---|
| Financial statements | SEC EDGAR XBRL `companyfacts` | no |
| Ticker → CIK | SEC `company_tickers.json` | no |
| Live prices | Yahoo v7 batch (cookie+crumb) | no |
| Fallback prices | Stooq CSV, labelled delayed | no |
| Indicators | Yahoo 1-year daily bars via `/api/quotes?market=us` | no |

## The clock

US sessions are three, not one: pre-market 04:00–09:30, regular 09:30–16:00,
after hours 16:00–20:00 ET. Only the regular session is called *live*.

Daylight saving is never computed by hand — it is asked of the platform's own
timezone database. Hand-rolling it is how you end up an hour wrong twice a year.
Tests pin 09:30 ET at 14:30 UTC in January and 13:30 UTC in July.

Extended-hours prints are real trades but thin, and the gap they show often does
not survive the opening auction. They are labelled, never presented as the price.

## What an Indian investor is not usually told

Surfaced on the US desk's home screen, because these change the answer more than
most stock analysis does:

- **LRS** caps remittance at $250,000 per financial year. TCS is nil up to ₹10
  lakh (raised from ₹7 lakh on 1 April 2026), 20% above. TCS is not a cost — it
  is credited or refunded, but it ties up cash until you file.
- **Dividends** are withheld at 25% for Indian residents; the treaty does not
  reduce it. Reclaim via foreign tax credit — but **Form 67 must be filed before
  your return**, or the credit is lost.
- **Section 111A does not apply to foreign-listed shares.** The familiar 20%
  short-term rate is unavailable: gains held 24 months or less are taxed **at
  your slab rate**. This is the single most misunderstood point, and several
  brokerage guides state it wrongly.
- Beyond 24 months, **12.5% without indexation**.
- **Schedule FA** disclosure is required whether or not the holding produced
  income. Omission is penalised under the Black Money Act.
- **USD/INR is a second position** you hold whether you meant to or not.
- **Pattern day trader**: under $25,000 in a margin account, more than three day
  trades in five business days restricts the account for 90 days.

Tax positions are as understood for FY 2026-27 and move with every Budget. The
page says so, and says to confirm with a chartered accountant.

## Not built yet

- **Ownership** — 13F institutional holdings and Form 4 insider transactions are
  in EDGAR and would be the natural next build.
- **Sector map** — the Indian one encodes NSE sector realities and does not
  transfer; the US needs its own, on GICS.
- **Streaming** — Zerodha is Indian instruments only. The US equivalent would be
  Alpaca or Finnhub, both of which offer keyless-tier WebSockets; the tape
  already accepts a pushed feed, so it is an adapter, not a rebuild.

Where an engine does not exist, the market registry holds `null` and the page
shows a gap saying what is missing — it does not fabricate or silently hide it.
