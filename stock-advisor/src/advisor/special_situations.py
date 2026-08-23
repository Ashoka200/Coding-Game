"""Special situations: returns that come from a corporate event, not a view.

Buybacks, open offers, rights issues, mergers, demergers and delistings have
something ordinary stock-picking does not — a defined event, a defined price and
a defined date. That makes the arithmetic knowable and the risk nameable, which
is why event-driven desks exist.

Two Indian specifics dominate the maths and are handled explicitly:

1. ACCEPTANCE RATIO. In a tender buyback or open offer you rarely get all your
   shares taken. The small-shareholder reservation (15% of the offer, for
   holdings up to ₹2 lakh on the record date) means a small investor's
   acceptance ratio is usually far better than a large one's — which is exactly
   why this is one of the few edges genuinely available to retail.

2. BUYBACK TAX AFTER 1 OCTOBER 2024. Buyback proceeds are now taxed in the
   shareholder's hands as a deemed dividend at slab rate, with NO deduction for
   what you paid. The cost of the bought-back shares becomes a capital loss you
   can set against other capital gains. This reversed the arithmetic of retail
   buyback arbitrage, and a model that ignores it will recommend trades that
   lose money after tax.

Nothing here is estimated. An unknown acceptance ratio or missing offer price
produces an explicit gap, because a "return" computed on a guessed ratio is
just a wish with a percentage sign.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

RETAIL_RESERVATION = 0.15          # SEBI: 15% of a buyback reserved for small holders
SMALL_HOLDER_LIMIT = 200_000       # ₹2 lakh holding on the record date
LTCG_RATE = 0.125                  # equity, over 12 months, above the annual exemption
STCG_RATE = 0.20


@dataclass
class Situation:
    kind: str
    symbol: str
    headline: str
    gross_return: float | None = None      # on the money at risk, before tax
    net_return: float | None = None        # after the tax that actually applies
    annualised: float | None = None
    maths: dict = field(default_factory=dict)
    risks: list[str] = field(default_factory=list)
    unknowns: list[dict] = field(default_factory=list)
    verdict: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _annualise(ret: float | None, days: int | None) -> float | None:
    """Annualised return. Short windows magnify small edges, so this is the
    number that makes a 2% arb comparable with anything else you could own."""
    if ret is None or not days or days <= 0:
        return None
    if ret <= -1:
        return None
    return round((1 + ret) ** (365 / days) - 1, 4)


def buyback_tender(symbol: str, market_price: float, buyback_price: float,
                   acceptance_ratio: float | None = None,
                   expected_price_after: float | None = None,
                   days_to_settlement: int | None = None,
                   slab_rate: float = 0.30,
                   holding_is_long_term: bool = False,
                   post_oct_2024_tax: bool = True) -> Situation:
    """Tender-offer buyback arbitrage, with the acceptance ratio doing the work.

    You buy at the market price, tender everything, some fraction is accepted at
    the buyback price, and you are left holding the rest at whatever the price
    settles to afterwards.
    """
    s = Situation("buyback_tender", symbol,
                  f"Tender buyback at {buyback_price:,.2f} against a market price "
                  f"of {market_price:,.2f}")
    if market_price <= 0 or buyback_price <= 0:
        s.unknowns.append({"field": "prices", "reason": "both prices must be positive"})
        return s
    if acceptance_ratio is None:
        s.unknowns.append({
            "field": "acceptance_ratio",
            "reason": "the acceptance ratio decides the whole trade and is only known "
                      "after tendering closes. Estimate it from the previous buyback "
                      "of the same company, or treat this as unquantified."})
        s.risks.append("Without an acceptance ratio there is no return to compute — "
                       "only a price difference, which is not the same thing.")
        return s

    a = max(0.0, min(1.0, acceptance_ratio))
    # The unaccepted stub usually reprices toward the pre-announcement level.
    after = expected_price_after if expected_price_after is not None else market_price * 0.94

    proceeds = a * buyback_price + (1 - a) * after
    gross = proceeds / market_price - 1
    s.gross_return = round(gross, 4)

    if post_oct_2024_tax:
        # Accepted proceeds taxed as dividend at slab, no cost deduction; the cost
        # of those shares becomes a capital loss usable against other gains.
        tendered_proceeds = a * buyback_price
        dividend_tax = tendered_proceeds * slab_rate
        cg_rate = LTCG_RATE if holding_is_long_term else STCG_RATE
        loss_shield = a * market_price * cg_rate      # only if you have gains to offset
        stub_value = (1 - a) * after
        net_cash = tendered_proceeds - dividend_tax + loss_shield + stub_value
        s.net_return = round(net_cash / market_price - 1, 4)
        s.risks.append(
            f"Since 1 October 2024 buyback proceeds are taxed as dividend at your slab "
            f"rate ({slab_rate:.0%}) with no deduction for cost. The ₹{a * market_price:,.0f} "
            "cost of the accepted shares becomes a capital loss — worth "
            f"₹{loss_shield:,.0f} only if you have capital gains to set it against. "
            "Assume no offset and the trade is materially worse.")
    else:
        s.net_return = s.gross_return
        s.risks.append("Pre-October-2024 treatment assumed: the company paid the tax "
                       "and proceeds were tax-free to you. Verify which regime applies.")

    s.annualised = _annualise(s.net_return, days_to_settlement)
    s.maths = {
        "market_price": market_price, "buyback_price": buyback_price,
        "acceptance_ratio": round(a, 4),
        "premium_to_market": round(buyback_price / market_price - 1, 4),
        "assumed_price_after": round(after, 2),
        "blended_proceeds_per_share": round(proceeds, 2),
        "days_to_settlement": days_to_settlement,
    }
    s.risks.append("The stub you are left holding is the real risk: if the price after "
                   "the buyback falls further than assumed, the accepted portion's gain "
                   "is eaten by the portion that was not.")
    if a < 0.25:
        s.risks.append(f"An acceptance ratio of {a:.0%} means most of your money stays "
                       "in the stock. This is a stock position wearing an arbitrage "
                       "costume — judge it as one.")

    if s.net_return is None:
        s.verdict = None
    elif s.net_return > 0.04 and (s.annualised or 0) > 0.15:
        s.verdict = "worth doing if you can hold the stub"
    elif s.net_return > 0:
        s.verdict = "positive but thin — costs and slippage may take it"
    else:
        s.verdict = "negative after tax; do not tender for the arbitrage"
    return s


def retail_acceptance_advantage(buyback_size_value: float,
                                retail_tendered_value: float | None) -> dict:
    """Why small holders get a better deal, quantified.

    15% of the offer is reserved for holdings up to ₹2 lakh. If small holders
    tender less than that reservation, their acceptance ratio approaches 100%.
    """
    reserved = buyback_size_value * RETAIL_RESERVATION
    if not retail_tendered_value or retail_tendered_value <= 0:
        return {"reserved_value": reserved, "acceptance_ratio": None,
                "note": "Retail tendering is only known after the offer closes. The "
                        f"reservation is ₹{reserved:,.0f}; compare it with what small "
                        "holders actually tender in the company's past buybacks."}
    ratio = min(1.0, reserved / retail_tendered_value)
    return {
        "reserved_value": reserved, "retail_tendered_value": retail_tendered_value,
        "acceptance_ratio": round(ratio, 4),
        "note": (f"Small holders (up to ₹{SMALL_HOLDER_LIMIT:,} on the record date) share "
                 f"a reserved ₹{reserved:,.0f}. Against ₹{retail_tendered_value:,.0f} "
                 f"tendered, roughly {ratio:.0%} is accepted"
                 + (" — near-full acceptance, which is the retail edge in this structure."
                    if ratio > 0.8 else ".")),
    }


def open_offer(symbol: str, market_price: float, offer_price: float,
               shares_sought_fraction: float | None = None,
               days_to_close: int | None = None,
               deal_probability: float = 0.9) -> Situation:
    """SEBI takeover open offer: an acquirer crossing 25% must offer for 26% more."""
    s = Situation("open_offer", symbol,
                  f"Open offer at {offer_price:,.2f} against {market_price:,.2f}")
    if market_price <= 0 or offer_price <= 0:
        s.unknowns.append({"field": "prices", "reason": "both prices must be positive"})
        return s
    spread = offer_price / market_price - 1
    if shares_sought_fraction is None:
        s.unknowns.append({
            "field": "acceptance_ratio",
            "reason": "how much of your holding is taken depends on total tendering; "
                      "an over-subscribed offer accepts proportionately"})
        a = None
        blended = None
    else:
        a = max(0.0, min(1.0, shares_sought_fraction))
        blended = a * offer_price + (1 - a) * market_price * 0.95
        s.gross_return = round(blended / market_price - 1, 4)
        s.net_return = s.gross_return          # capital gains, not deemed dividend
        s.annualised = _annualise(s.net_return, days_to_close)

    s.maths = {"spread_to_offer": round(spread, 4), "acceptance_ratio": a,
               "blended_proceeds": round(blended, 2) if blended else None,
               "deal_probability_assumed": deal_probability,
               "days_to_close": days_to_close}
    s.risks = [
        f"A {deal_probability:.0%} completion assumption is doing real work here. If the "
        "offer lapses — regulatory objection, competing bid, acquirer withdrawal — the "
        "price usually returns to where it was before the announcement.",
        "Open offers can be extended. An arbitrage that annualises well over 40 days "
        "annualises poorly over 140.",
        "Gains are capital gains, not deemed dividend — a different, usually kinder "
        "treatment than a buyback.",
    ]
    if s.net_return is not None:
        expected = deal_probability * s.net_return + (1 - deal_probability) * -0.10
        s.maths["probability_weighted_return"] = round(expected, 4)
        s.verdict = ("attractive" if expected > 0.03
                     else "thin for the deal risk" if expected > 0
                     else "not worth the deal risk")
    return s


def rights_issue(symbol: str, cum_price: float, rights_price: float,
                 ratio_new: int, ratio_held: int) -> Situation:
    """Rights issue: what the entitlement is actually worth.

    ratio_new:ratio_held — e.g. 1 new share for every 5 held is (1, 5).
    """
    s = Situation("rights_issue", symbol,
                  f"{ratio_new}-for-{ratio_held} rights at {rights_price:,.2f} "
                  f"(market {cum_price:,.2f})")
    if min(cum_price, rights_price) <= 0 or ratio_new <= 0 or ratio_held <= 0:
        s.unknowns.append({"field": "terms", "reason": "prices and ratio must be positive"})
        return s
    worthless_note = []
    if rights_price >= cum_price:
        worthless_note.append(
            "The rights price is at or above the market price, so the entitlement is "
            "worthless — do not subscribe for the discount, because there is none.")
    # Theoretical ex-rights price: the blended value after the new shares exist.
    terp = (ratio_held * cum_price + ratio_new * rights_price) / (ratio_held + ratio_new)
    right_value = max(0.0, cum_price - terp)
    s.maths = {
        "theoretical_ex_rights_price": round(terp, 2),
        "value_of_one_right": round(right_value, 2),
        "discount_to_market": round(1 - rights_price / cum_price, 4),
        "dilution": round(ratio_new / (ratio_held + ratio_new), 4),
    }
    s.risks = worthless_note + [
        "The price falling to the theoretical ex-rights level is arithmetic, not a loss "
        "— you are compensated by owning more shares. Selling in a panic on the ex-date "
        "converts an accounting adjustment into a real loss.",
        "Ignoring your entitlement IS a loss: your stake is diluted and you receive "
        "nothing. Either subscribe or sell the right in the market.",
        "Ask why the money is being raised. Rights to fund growth are very different "
        "from rights to repay debt the business could not service.",
    ]
    s.verdict = ("entitlement has real value — subscribe or sell the right"
                 if right_value > 0 else "no value in the entitlement")
    return s


def merger_arb(symbol: str, target_price: float, acquirer_price: float,
               swap_ratio_target: float, swap_ratio_acquirer: float,
               days_to_close: int | None = None,
               deal_probability: float = 0.85) -> Situation:
    """Share-swap merger: the spread between the exchange value and the market."""
    s = Situation("merger_arb", symbol,
                  f"Swap {swap_ratio_target}:{swap_ratio_acquirer} — "
                  f"target {target_price:,.2f}, acquirer {acquirer_price:,.2f}")
    if min(target_price, acquirer_price) <= 0 or swap_ratio_acquirer <= 0:
        s.unknowns.append({"field": "terms", "reason": "prices and ratio must be positive"})
        return s
    implied = acquirer_price * (swap_ratio_acquirer / swap_ratio_target)
    spread = implied / target_price - 1
    s.gross_return = round(spread, 4)
    s.net_return = s.gross_return
    s.annualised = _annualise(spread, days_to_close)
    expected = deal_probability * spread + (1 - deal_probability) * -0.15
    s.maths = {"implied_value_per_target_share": round(implied, 2),
               "spread": round(spread, 4),
               "probability_weighted_return": round(expected, 4),
               "days_to_close": days_to_close}
    s.risks = [
        "The spread is not free money — it is the market pricing the chance the deal "
        "breaks. A wide spread usually means real doubt, not a mistake.",
        "A share swap leaves you exposed to the acquirer's price. Capturing the spread "
        "cleanly requires shorting the acquirer, which retail generally cannot do.",
        "Regulatory approvals in India (CCI, NCLT, sectoral regulators) routinely add "
        "months. Time is the enemy of an annualised return.",
    ]
    s.verdict = ("worth analysing further" if expected > 0.04
                 else "spread does not pay for the break risk")
    return s


def delisting(symbol: str, market_price: float, floor_price: float,
              indicative_price: float | None = None) -> Situation:
    """Voluntary delisting by reverse book building — high variance by design."""
    s = Situation("delisting", symbol,
                  f"Delisting with a floor of {floor_price:,.2f} (market {market_price:,.2f})")
    if min(market_price, floor_price) <= 0:
        s.unknowns.append({"field": "prices", "reason": "prices must be positive"})
        return s
    s.maths = {"premium_to_floor": round(floor_price / market_price - 1, 4)}
    if indicative_price:
        s.gross_return = round(indicative_price / market_price - 1, 4)
        s.net_return = s.gross_return
        s.maths["indicative_price"] = indicative_price
    else:
        s.unknowns.append({
            "field": "discovered_price",
            "reason": "reverse book building discovers the price from what holders "
                      "demand; it is unknowable in advance and has historically landed "
                      "far above the floor"})
    s.risks = [
        "The floor is a floor, not the price. In reverse book building the discovered "
        "price is set by tendering shareholders and has often been multiples of it.",
        "A failed delisting is the real risk: the price typically falls back hard, and "
        "you are left holding an illiquid stock with a disengaged promoter.",
        "If you do not tender and the delisting succeeds, you hold unlisted shares with "
        "a limited exit window — the worst outcome available.",
    ]
    s.verdict = ("speculative — the payoff is unknowable in advance; size it as a "
                 "lottery ticket, not as arbitrage")
    return s


def demerger(symbol: str, price_before: float, parts: list[dict]) -> Situation:
    """Demerger value unlock. parts: [{name, value_per_share}]."""
    s = Situation("demerger", symbol, f"Demerger of {symbol} into {len(parts)} parts")
    valued = [p for p in parts if p.get("value_per_share") is not None]
    if not valued:
        s.unknowns.append({"field": "part_values",
                           "reason": "no segment value supplied; the unlock cannot be "
                                     "quantified, only asserted"})
        return s
    total = sum(p["value_per_share"] for p in valued)
    s.gross_return = round(total / price_before - 1, 4) if price_before > 0 else None
    s.net_return = s.gross_return
    s.maths = {"sum_of_parts": round(total, 2), "price_before": price_before,
               "parts": valued,
               "unvalued_parts": [p.get("name") for p in parts
                                  if p.get("value_per_share") is None]}
    s.risks = [
        "Sum-of-the-parts values are judgement dressed as arithmetic. The market often "
        "applies a holding-company discount for good reasons: the parts may be worth "
        "less apart if they shared customers, capital or management.",
        "Index funds are forced sellers of the demerged entity when it does not qualify "
        "for the index — which creates the dip that patient buyers wait for.",
        "Listing of the demerged entity can take months, during which its value is "
        "trapped and untradeable.",
    ]
    s.verdict = ("value on paper — verify the parts can stand alone"
                 if (s.gross_return or 0) > 0.10 else "no material unlock in these numbers")
    return s
