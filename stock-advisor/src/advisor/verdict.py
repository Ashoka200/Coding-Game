"""The decision engine: evidence in, one action out, through a fixed sequence.

Nine stages, always in this order. The order is the product — it is what makes
the answer reproducible and auditable instead of a judgement call:

    0 Evidence      what is actually known; caps confidence
    1 Vetoes        fraud, default, ruinous leverage — override everything
    2 Position      a breached exit price is a decision already made
    3 Business      is it still the company you thought you owned?
    4 Valuation     what are you paying for that business?
    5 News          has anything material changed?
    6 Trend         what is price doing?
    7 Regime        does this market reward new risk?
    8 Horizon       long-term (business) or short-term (trend)?
    9 Synthesis     action, conviction, levels, and the chain that produced them

Conflicts are resolved differently by book, because the two books are playing
different games (owner's instruction):

    INVESTING  fundamentals decide, the trend only times the entry. A cheap,
               sound business in a downtrend is a "wait", not an "avoid".
    TRADING    a genuine conflict returns NO POSITION with both cases stated.
               In a book that lives by the exit price, ambiguity is a reason to
               stand aside, not to pick a side.

Nothing here estimates a missing figure. An unknown stays unknown and lowers
the confidence ceiling instead.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict

ACTIONS = ("SELL", "TRIM", "HOLD", "WATCH", "AVOID", "ACCUMULATE", "BUY")


@dataclass
class Step:
    stage: str
    finding: str


@dataclass
class Verdict:
    symbol: str
    action: str
    conviction: int
    horizon: str
    chain: list[Step] = field(default_factory=list)
    levels: dict | None = None
    short_case: bool = False
    book: str = "investing"
    conflict: str | None = None
    unknowns: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["chain"] = [asdict(s) if not isinstance(s, dict) else s for s in self.chain]
        return d


def _levels(features: dict | None) -> dict | None:
    if not features or not features.get("atr14"):
        return None
    last = features["close"]
    stop = max(features.get("swing_low_20d", 0.0), last - 2 * features["atr14"])
    if stop >= last:
        stop = last - 2 * features["atr14"]
    risk = last - stop
    if risk <= 0:
        return None
    return {"reference_price": round(last, 2), "stop": round(stop, 2),
            "target1": round(last + 1.5 * risk, 2), "target2": round(last + 2.5 * risk, 2),
            "add_below": round(last * 0.94, 2)}


def decide(symbol: str, features: dict | None = None, fundamentals: dict | None = None,
           fundamental_score: float | None = None, news_items: list | None = None,
           news_pressure: dict | None = None, stage: int | None = None,
           regime_risk_on: bool = True, holding: dict | None = None,
           book: str = "investing", valuation: dict | None = None) -> Verdict:
    """Run the nine stages. Every argument may be None — missing evidence lowers
    the confidence ceiling rather than being filled in."""
    chain: list[Step] = []
    unknowns: list[str] = []
    conviction = 50.0

    def step(stage_name: str, finding: str) -> None:
        chain.append(Step(stage_name, finding))

    # --- 0: evidence -------------------------------------------------------
    have_price = features is not None
    have_fund = fundamentals is not None and fundamental_score is not None
    have_news = news_pressure is not None
    if not have_fund:
        unknowns.append("fundamentals")
    if not have_news:
        unknowns.append("news")
    if not have_price:
        unknowns.append("price_history")
    ceiling = 60 + (20 if have_fund else 0) + (20 if have_news else 0)
    step("Evidence", "Working from " + ", ".join(filter(None, [
        "price and trend" if have_price else "no price history",
        "financials" if have_fund else "no financials",
        "recent news" if have_news else "no news",
    ])) + f". Confidence is capped at {ceiling} because of what is missing.")

    def finish(action: str, conv: float, horizon: str, short_case: bool = False,
               conflict: str | None = None) -> Verdict:
        return Verdict(symbol=symbol, action=action,
                       conviction=int(max(5, min(ceiling, round(conv)))),
                       horizon=horizon, chain=chain, levels=_levels(features),
                       short_case=short_case, book=book, conflict=conflict,
                       unknowns=unknowns)

    # --- 1: hard vetoes ----------------------------------------------------
    veto = None
    if news_items:
        grave = [i for i in news_items
                 if getattr(i, "weight", i.get("weight", 0) if isinstance(i, dict) else 0) <= -3]
        if grave:
            g = grave[0]
            label = getattr(g, "event_label", None) or (g.get("event_label") if isinstance(g, dict) else "")
            title = getattr(g, "title", None) or (g.get("title") if isinstance(g, dict) else "")
            veto = f"A grave event is reported: {label.lower()} — “{title[:110]}”"
    if veto is None and fundamentals:
        de = fundamentals.get("debt_to_equity")
        cover = fundamentals.get("interest_cover")
        if de is not None and cover is not None and de > 3 and cover < 1.5:
            veto = (f"Debt is {de:.2f}× equity and operating profit covers interest only "
                    f"{cover:.1f}× — the balance sheet, not the business, now decides the outcome.")
    if veto:
        step("Veto", veto)
        return finish("SELL" if holding else "AVOID", 85,
                      "Long-term risk — this is about survival, not price")
    step("Veto check", "No fraud, default or ruinous-leverage flag found in the evidence held.")

    # --- 2: position state -------------------------------------------------
    forced_action = None
    if holding:
        stop = holding.get("stop")
        if stop and features and features["close"] <= stop:
            step("Position", f"Price {features['close']:.2f} is at or below the exit price "
                             f"of {stop:.2f} set when you bought.")
            return finish("SELL", 90,
                          "The decision was made when you were calm; this is the execution")
        weight = holding.get("weight")
        if weight is not None and weight > 0.15:
            step("Position", f"This position is {weight:.0%} of the portfolio — past the "
                             "15% concentration limit.")
            forced_action = "TRIM"

    # --- 3: business quality ----------------------------------------------
    quality = fundamental_score if have_fund else None
    if quality is not None:
        bits = [f"Fundamental score {quality:.0f}/100"]
        if fundamentals.get("roce") is not None:
            bits.append(f"ROCE {fundamentals['roce']:.1%}")
        elif fundamentals.get("roe") is not None:
            bits.append(f"ROE {fundamentals['roe']:.1%}")
        if fundamentals.get("debt_to_equity") is not None:
            bits.append(f"debt/equity {fundamentals['debt_to_equity']:.2f}")
        step("Business", ", ".join(bits) + ".")
        conviction += 12 if quality >= 70 else 4 if quality >= 55 else -6 if quality >= 40 else -18
    else:
        step("Business", "No financials available, so nothing here can be a long-term call.")

    # --- 4: valuation ------------------------------------------------------
    # A discounted-cash-flow view outranks a bare multiple when it exists: the
    # multiple tells you what you pay, the DCF tells you what you get.
    val_in = valuation if isinstance(valuation, dict) else None   # capture before rebinding
    valuation = "unknown"                                          # now the category
    if val_in and val_in.get("margin_of_safety") is not None:
        mos = val_in["margin_of_safety"]
        valuation = ("cheap" if mos > 0.15 else "fair" if mos > -0.15
                     else "rich" if mos > -0.35 else "extreme")
        bits = [f"Fair value about {val_in.get('fair_value_base')}, "
                f"a margin of safety of {mos:+.0%} — {valuation}"]
        if val_in.get("implied_growth") is not None:
            bits.append(f"the price already assumes {val_in['implied_growth']:.1%} "
                        "annual cash-flow growth")
        step("Valuation", "; ".join(bits) + ".")
        conviction += {"cheap": 12, "fair": 3, "rich": -8, "extreme": -16}[valuation]
    elif fundamentals and fundamentals.get("pe") and fundamentals["pe"] > 0:
        pe = fundamentals["pe"]
        valuation = ("cheap" if pe < 18 else "fair" if pe < 35
                     else "rich" if pe < 60 else "extreme")
        step("Valuation", f"P/E of {pe:.1f} — {valuation}. (No cash-flow valuation "
                          "available, so this is what you pay, not what you get.)")
        conviction += {"cheap": 10, "fair": 3, "rich": -6, "extreme": -14}[valuation]
    else:
        unknowns.append("valuation")

    # --- 5: news overlay ---------------------------------------------------
    tone = "none"
    if have_news:
        tone = news_pressure.get("tone", "mixed")
        material = news_pressure.get("material_count", 0)
        step("News", (f"{material} material item(s) recently; net tone {tone}."
                      if material else "Nothing material in the recent window."))
        net = news_pressure.get("net", 0)
        conviction += 8 if net > 1.5 else -12 if net < -1.5 else 0

    # --- 6: trend ----------------------------------------------------------
    st = stage if stage is not None else 1
    trend_word = {2: "uptrend", 1: "basing", 3: "topping", 4: "downtrend"}.get(st, "unclear")
    detail = f"Price is in a {trend_word}"
    if features and features.get("rsi14") is not None:
        detail += f", RSI {features['rsi14']:.0f}"
    if features and features.get("dist_52w_high") is not None:
        detail += f", {features['dist_52w_high']:+.1%} from its 52-week high"
    step("Trend", detail + ".")
    conviction += {2: 10, 1: 0, 3: -8, 4: -16}.get(st, 0)
    rsi = (features or {}).get("rsi14")
    overbought = rsi is not None and rsi > 78
    oversold = rsi is not None and rsi < 25

    # --- 7: regime ---------------------------------------------------------
    if not regime_risk_on:
        step("Market", "The market is not in a clean uptrend, so new buying is restrained "
                       "regardless of how good the stock looks.")
        conviction -= 8

    # --- 8: horizon --------------------------------------------------------
    if quality is not None and quality >= 60 and valuation != "extreme":
        horizon = "Long term — the case rests on the business compounding; measure it in years"
    elif st == 2 and (quality is None or quality >= 40):
        horizon = "Short term — the case rests on the trend; it lives and dies by the exit price"
    else:
        horizon = "No horizon qualifies — neither the business nor the trend supports a position"
    step("Horizon", horizon)

    # --- 8b: conflict detection --------------------------------------------
    # A conflict is the models disagreeing about direction, not merely being
    # lukewarm: cheap-and-falling, or expensive-and-rising.
    conflict = None
    cheap = valuation in ("cheap",)
    dear = valuation in ("rich", "extreme")
    sound = quality is not None and quality >= 55
    weak_trend = st in (3, 4)
    strong_trend = st == 2
    if cheap and sound and weak_trend:
        conflict = ("The numbers say cheap and sound; the price says the market "
                    "disagrees. One of them is wrong, and the market usually knows "
                    "something first.")
    elif dear and strong_trend:
        conflict = ("The trend is strong but the price already assumes a great deal. "
                    "You would be buying momentum, not value.")

    if conflict:
        step("Conflict", conflict)
        if book == "trading":
            # In the trading book, ambiguity is a reason to stand aside: this book
            # lives by the exit price, and a contested thesis has no clean one.
            step("Resolution", "Trading book: a genuine conflict returns no position. "
                               "Both cases are stated above; neither is adopted.")
            return finish("HOLD" if holding else "WATCH", min(conviction, 40),
                          "No horizon — the models disagree and this book does not "
                          "take contested trades", conflict=conflict)
        step("Resolution", "Investing book: the business decides and the trend only "
                           "times the entry. A sound, cheap business in a downtrend "
                           "is a wait, not an avoid.")

    # --- 9: synthesis ------------------------------------------------------
    action = forced_action
    if action is None:
        bad = quality is not None and quality < 45
        good = quality is not None and quality >= 65
        if st == 4 and (bad or tone == "negative"):
            action = "SELL" if holding else "AVOID"
        elif st == 4 and book == "investing" and good and valuation in ("cheap", "fair"):
            # fundamentals decide, the trend only times: wait for the turn
            action = "HOLD" if holding else "WATCH"
        elif st == 4:
            action = "HOLD" if holding else "WATCH"
        elif holding:
            if tone == "negative" and bad:
                action = "SELL"
            elif overbought and valuation == "extreme":
                action = "TRIM"
            else:
                action = "HOLD"
        else:
            if good and st == 2 and regime_risk_on and not overbought:
                action = "BUY"
            elif good and (valuation == "cheap" or oversold):
                action = "ACCUMULATE"
            elif st == 2 and regime_risk_on and quality is None:
                action = "BUY"
            elif bad:
                action = "AVOID"
            else:
                action = "WATCH"

    short_case = st == 4 and (tone == "negative" or (quality is not None and quality < 40))
    if short_case and not holding:
        step("Short?", "The bear case is real, but a naked short has unlimited loss and Indian "
                       "cash-market shorts must be squared off the same day. Use a defined-risk "
                       "bear put spread sized to 0.5–1% of capital — never a naked short.")
    return finish(action, conviction, horizon, short_case, conflict)
