# 07 — Derivatives & F&O (CFA L2 derivatives, retail-survival edition)

Activated only in Phase 6, after the cash-market system is proven. Doctrine: SEBI's
own study found >90% of retail F&O traders lose money — the ones who survive use
derivatives to *shape risk they already have*, not to manufacture leverage.

## Options pricing intuition the AI must reason with

- An option price = intrinsic + time value; time value peaks ATM and decays
  non-linearly (theta accelerates in the last 2 weeks).
- **Implied volatility is the price of the option.** Buying options = buying IV;
  selling = selling IV. Every strategy call starts with: where is IV vs its own
  1-year percentile (IVP)? High IVP → prefer net-credit/defined-risk selling
  structures; low IVP → prefer debit structures. Direction second, vol first.
- Greeks the engine computes (Black-Scholes adequate for screening): delta
  (directional exposure & rough ITM probability), gamma (risk near expiry), theta
  (daily bleed in ₹), vega (₹ per IV point — the hidden killer in event trades).

## Permitted strategy menu (defined-risk only)

| View | High IVP | Low IVP |
|---|---|---|
| Moderately bullish | Bull put spread | Bull call spread |
| Moderately bearish | Bear call spread | Bear put spread |
| Rangebound | Iron condor (index only) | — (no edge) |
| Holding + income | Covered call (OTM, on holdings) | — |
| Hedging the book | Protective puts / put spread collar on index | Same |
| Event (results) | — stay out | — stay out (IV crush eats direction wins) |

**Banned permanently:** naked short options, short straddles/strangles, expiry-day
gamma scalping, buying deep-OTM weekly lottery tickets, and any position whose max
loss is undefined or exceeds the trade's risk budget.

## Position rules

- Same risk arithmetic as module 04: max loss of the structure = the "entry−stop"
  quantity; sized to ≤ 0.5–1% of equity. Margin used is not risk; max loss is.
- Index (Nifty/BankNifty) preferred over stock options: tighter spreads, no
  single-name gap catastrophe, better liquidity. Stock options only in top-liquidity
  names and only spreads.
- Exit credit spreads at 50–60% of max profit or at 2× credit loss; never hold shorts
  into the final week for the last few rupees (gamma risk >> remaining theta).

## Open-interest analytics (context, not signals)

OI buildup classification (long/short buildup, covering, unwinding), PCR extremes,
max-pain, and IV skew are computed and reported as *market-positioning context*.
Doctrine: OI data describes crowd positioning; it does not predict direction reliably
enough to trade standalone — no trade is taken on OI alone.

## Futures

Used for two purposes only: hedging portfolio beta (short index futures sized by
portfolio beta × value ÷ contract value, when a hedge is explicitly wanted), and
cash-futures basis awareness (steep premium = bullish positioning crowding; discount
near events = fear). No standalone directional futures speculation — the leverage
(~5–7×) is incompatible with the 1% risk rule at retail capital sizes.
