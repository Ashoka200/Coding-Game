"""Where each master's method breaks, tested against live data.

Every one of the five lenses has a documented way of failing, and the failures
are not random — each is the *specific* blind spot created by that method's
strength. A lens that rewards high returns on capital will eventually pay any
price for them. A lens that respects the trend will be wrong at exactly the
turn. A lens that demands cheapness will buy a business that is cheap because
it is dying.

So this module does not score companies. It asks a different question: given
what the data says right now, is this the situation in which the lens that
likes this stock is known to be wrong? When the answer is yes, the lens's
endorsement should be discounted or ignored — which is the whole point of
knowing an investor's failures as well as their method.

The rule underneath: a strength and its failure mode are the same property seen
from two sides, so a lens can never detect its own blind spot. Only an outside
check can, and that is what these are.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

# Which lens each failure mode invalidates. Named rather than inferred, because
# the mapping is the actual content: it says whose endorsement to stop trusting.
QUALITY_LENSES = ("Raamdeo Agrawal", "Warren Buffett", "Radhakishan Damani")
VALUE_LENSES = ("Warren Buffett", "Peter Lynch")
TREND_LENSES = ("Rakesh Jhunjhunwala",)
ALL_LENSES = ("Raamdeo Agrawal", "Rakesh Jhunjhunwala", "Warren Buffett",
              "Peter Lynch", "Radhakishan Damani")

CYCLICAL_HINTS = ("metal", "mining", "steel", "cement", "commodity", "chemical",
                  "oil", "gas", "energy", "shipping", "sugar", "paper", "auto")


@dataclass
class FailureMode:
    name: str
    triggered: bool | None        # None = could not be tested
    severity: str                 # "none" | "watch" | "serious"
    invalidates: tuple[str, ...]
    evidence: str
    mechanism: str                # why this breaks the method
    what_to_do: str

    def to_dict(self) -> dict:
        d = asdict(self)
        d["invalidates"] = list(self.invalidates)
        return d


def _sev(trig: bool | None, serious: bool = False) -> str:
    if trig is None:
        return "unknown"
    if not trig:
        return "none"
    return "serious" if serious else "watch"


# --------------------------------------------------------------------------
def quality_trap(f: dict) -> FailureMode:
    """The failure that cost Indian quality investors most of 2022 to 2024.

    A great business whose growth has stopped, still priced as though it had
    not. Every quality lens keeps endorsing it, because the things they measure
    — returns on capital, low debt, margins — are all still excellent. They are
    lagging descriptions of a franchise, and none of them notices that the
    price already contains a decade of growth that is no longer arriving.

    Detected as the conjunction, never as high valuation alone: high returns,
    a valuation rich against the company's own history, and decelerating
    growth. Any two of those is normal; all three is the trap.
    """
    roe = f.get("roe")
    pe = f.get("pe")
    pe_hist = f.get("pe_percentile")          # where PE sits in its own 10y range
    g_now = f.get("earningsGrowth")
    g_past = f.get("earningsCagr3y")

    if roe is None or pe_hist is None or g_now is None or g_past is None:
        return FailureMode(
            "Quality trap", None, "unknown", QUALITY_LENSES,
            "needs return on equity, valuation percentile and both growth rates",
            "A quality lens cannot see its own blind spot; this check needs the "
            "company's valuation history, which the lens never looks at.",
            "Get the valuation history before trusting a quality endorsement.")

    decelerating = g_now < g_past - 0.03
    rich = pe_hist >= 0.80
    high_quality = roe >= 0.18
    trig = bool(high_quality and rich and decelerating)
    return FailureMode(
        "Quality trap", trig, _sev(trig, serious=(pe_hist >= 0.90)), QUALITY_LENSES,
        f"return on equity {roe * 100:.0f}%, valuation at the "
        f"{pe_hist * 100:.0f}th percentile of its own history, growth "
        f"{g_now * 100:.0f}% against a three-year rate of {g_past * 100:.0f}%",
        "Returns on capital and margins describe the franchise that was built; "
        "they say nothing about what is being paid for it now. When growth "
        "decelerates from a rich starting valuation, the derating alone can take "
        "years of earnings growth back.",
        "Do not treat the quality lenses as confirming anything here. Require a "
        "valuation case on its own terms, or wait for the derating.")


def value_trap(f: dict) -> FailureMode:
    """Cheap for a reason. The mirror image, and the older mistake.

    Low multiples plus deteriorating returns plus a falling price is not a
    bargain; it is the market pricing a decline the accounts have not finished
    reporting. The value lenses see only the first of those three.
    """
    pe = f.get("pe")
    roe_now, roe_past = f.get("roe"), f.get("roe_3y_ago")
    above = f.get("above200dma")

    if pe is None or roe_now is None or roe_past is None or above is None:
        return FailureMode(
            "Value trap", None, "unknown", VALUE_LENSES,
            "needs valuation, returns now against three years ago, and the trend",
            "Cheapness is only information alongside the direction of the "
            "business and the direction of the price.",
            "Get the earlier return on equity before acting on a low multiple.")

    cheap = pe is not None and 0 < pe <= 15
    deteriorating = roe_now < roe_past - 0.03
    falling = above is False
    trig = bool(cheap and deteriorating and falling)
    return FailureMode(
        "Value trap", trig, _sev(trig, serious=(roe_now < roe_past - 0.08)),
        VALUE_LENSES,
        f"price-earnings {pe:.1f}, return on equity {roe_now * 100:.0f}% against "
        f"{roe_past * 100:.0f}% three years ago, price "
        f"{'below' if falling else 'above'} its long-term average",
        "A falling multiple on falling returns is not mean reversion. The "
        "multiple is low because earnings are expected to be lower still, and "
        "the accounts are the last place that shows up.",
        "Require evidence the deterioration has stopped — a stabilised margin or "
        "a return on equity that has turned — before treating cheapness as a reason.")


def cyclical_peg_illusion(f: dict) -> FailureMode:
    """Lynch's method inverted by the cycle — and he said so himself.

    At a cyclical peak, earnings are at their maximum and the multiple at its
    minimum, so PEG looks its most attractive at the single worst moment to buy.
    A commodity producer on four times earnings after a record year is not a
    growth stock at a discount; it is a cyclical at the top.
    """
    sector = (f.get("sector") or "").lower()
    peg = f.get("peg")
    margin_now = f.get("opMargin")
    margin_peak = f.get("opMargin_5y_high")

    if not sector or peg is None or margin_now is None or margin_peak is None:
        return FailureMode(
            "Cyclical PEG illusion", None, "unknown", ("Peter Lynch",),
            "needs the sector, PEG, and margin against its five-year high",
            "PEG assumes earnings are a trend. In a cyclical they are a wave.",
            "Get the margin history before using PEG on a cyclical.")

    cyclical = any(h in sector for h in CYCLICAL_HINTS)
    at_peak = margin_peak > 0 and margin_now >= margin_peak * 0.92
    cheap_peg = peg <= 1.0
    trig = bool(cyclical and at_peak and cheap_peg)
    return FailureMode(
        "Cyclical PEG illusion", trig, _sev(trig, serious=at_peak and peg <= 0.6),
        ("Peter Lynch",),
        f"{f.get('sector')}, PEG {peg:.2f}, operating margin {margin_now * 100:.1f}% "
        f"against a five-year high of {margin_peak * 100:.1f}%",
        "Peak-cycle earnings make every valuation ratio look cheap at once. The "
        "correct multiple for a cyclical at the top of its margin range is a "
        "high one, not a low one.",
        "Value it on mid-cycle margins, not current ones. Lynch classified "
        "cyclicals separately for exactly this reason.")


def momentum_reversal_risk(f: dict) -> FailureMode:
    """Where "markets are supreme" gets you hurt.

    Trend rules work most of the time and fail violently at turns. The worst
    case is well documented: after a deep market fall, the rebound is led by the
    most beaten-down names, and anything positioned by trend is positioned
    exactly wrong. Jhunjhunwala's respect for the tape is a real edge with a
    known, concentrated cost.
    """
    dd = f.get("market_drawdown")            # index distance from its high, negative
    rebounding = f.get("market_rebounding")  # index rising off the low

    if dd is None or rebounding is None:
        return FailureMode(
            "Momentum reversal", None, "unknown", TREND_LENSES,
            "needs the index drawdown and whether it has turned up",
            "A trend rule cannot tell a continuation from a turn; only the "
            "market's own state hints at which is likelier.",
            "Track the index drawdown to know when trend signals are fragile.")

    trig = bool(dd <= -0.20 and rebounding)
    return FailureMode(
        "Momentum reversal", trig, _sev(trig, serious=(dd <= -0.30)), TREND_LENSES,
        f"index {dd * 100:.0f}% from its high and "
        f"{'turning up' if rebounding else 'still falling'}",
        "Momentum crashes happen in rebounds, not in falls. The names that fell "
        "hardest rise fastest, and a trend filter is by construction out of all "
        "of them.",
        "Suspend the tape requirement during the rebound, or size trend-based "
        "entries down until the index reclaims its long-term average.")


def crowding(f: dict) -> FailureMode:
    """Everyone already owns it, so the buying is already done.

    A consensus quality name can keep passing every checklist while having no
    marginal buyer left. High institutional ownership plus a premium valuation
    is the condition where good news stops moving the price and bad news moves
    it a great deal.
    """
    inst = f.get("institutionalHolding")
    pe_hist = f.get("pe_percentile")

    if inst is None or pe_hist is None:
        return FailureMode(
            "Crowded position", None, "unknown", ALL_LENSES,
            "needs institutional ownership and the valuation percentile",
            "Checklists measure the business, never who already owns it.",
            "Get the shareholding pattern before adding to a consensus name.")

    trig = bool(inst >= 0.55 and pe_hist >= 0.75)
    return FailureMode(
        "Crowded position", trig, _sev(trig, serious=(inst >= 0.70)), ALL_LENSES,
        f"institutions hold {inst * 100:.0f}%, valuation at the "
        f"{pe_hist * 100:.0f}th percentile of its own history",
        "When the informed buyers have finished buying, the next large flow is "
        "more likely to be a seller. Ownership is a better guide to who is left "
        "to act than any fundamental ratio.",
        "Size smaller than the checklists suggest, and prefer names where the "
        "same quality has not yet been fully recognised.")


def accounting_divergence(f: dict) -> FailureMode:
    """The one that breaks every lens at once.

    Profit rising while the cash it should generate is not — the most reliable
    early warning there is, and invisible to every ratio built on reported
    earnings, which is most of them. Return on equity, margins and growth all
    improve right up to the restatement.
    """
    cc_now = f.get("cashConversion")
    cc_past = f.get("cashConversion_3y_avg")
    growing = f.get("earningsGrowth")

    if cc_now is None or cc_past is None or growing is None:
        return FailureMode(
            "Earnings not becoming cash", None, "unknown", ALL_LENSES,
            "needs cash conversion now and its three-year average",
            "Every lens here is built on reported profit. None of them checks "
            "whether the profit arrived.",
            "Get the cash flow statement; this is the check worth having most.")

    trig = bool(growing > 0.05 and cc_now < 0.6 and cc_now < cc_past - 0.20)
    return FailureMode(
        "Earnings not becoming cash", trig,
        _sev(trig, serious=(cc_now is not None and cc_now < 0.4)), ALL_LENSES,
        f"cash conversion {cc_now:.2f} against a three-year average of "
        f"{cc_past:.2f}, while earnings grow {growing * 100:.0f}%",
        "Profit that does not convert to cash is either being consumed by "
        "working capital or was never really earned. Both end the same way, and "
        "no ratio built on reported earnings sees either coming.",
        "Treat every lens's endorsement as suspended until cash conversion "
        "recovers. This overrides quality, value and trend alike.")


CHECKS = (quality_trap, value_trap, cyclical_peg_illusion,
          momentum_reversal_risk, crowding, accounting_divergence)


def run_all(f: dict) -> list[FailureMode]:
    return [check(f) for check in CHECKS]


def discount_lenses(f: dict, verdicts: list) -> dict:
    """Which endorsements to stop trusting, and why.

    Takes the master lenses' verdicts and the live failure checks, and returns
    the set of authors whose opinion is currently unreliable. This is the whole
    purpose of the module: not to find better stocks, but to know when a method
    that usually works is in the situation where it does not.
    """
    modes = run_all(f)
    fired = [m for m in modes if m.triggered]
    untestable = [m for m in modes if m.triggered is None]

    suspended: dict[str, list[str]] = {}
    for m in fired:
        for author in m.invalidates:
            suspended.setdefault(author, []).append(m.name)

    still_good = [v.author for v in verdicts
                  if v.score is not None and v.score >= 0.6
                  and v.author not in suspended]

    if not fired:
        headline = ("no known failure mode is active — the lenses can be read at "
                    "face value" if not untestable else
                    f"no failure mode fired, but {len(untestable)} could not be "
                    f"tested for want of data")
    elif any(m.severity == "serious" for m in fired):
        headline = (f"{len(fired)} failure mode(s) active, at least one serious — "
                    f"the endorsements below are not reliable right now")
    else:
        headline = f"{len(fired)} failure mode(s) worth watching before acting"

    return {
        "headline": headline,
        "fired": [m.to_dict() for m in fired],
        "untestable": [m.name for m in untestable],
        "suspended_authors": suspended,
        "endorsements_still_standing": still_good,
        "all_modes": [m.to_dict() for m in modes],
    }
