"""Penny and micro-cap stocks, sized by how you get out rather than why you got in.

Every penny-stock screener finds the same thing: a small company that is cheap
and growing. That is the easy half and it is not where the money is lost. The
money is lost on the way out, and the exit is governed by three things that do
not exist in large caps at all.

**Circuit bands.** A stock in a 5% band that opens limit-down has no buyers at
any price. You are not holding a losing position, you are holding an unsellable
one. A 30% fall takes six consecutive locked sessions, and during all six the
screen shows a price you cannot transact at.

**Surveillance stages.** The exchanges move suspicious or thinly traded scrips
through graded measures. By Stage II the stock is trade-for-trade — no
intraday, delivery compulsory — and buyers post an additional surveillance
deposit of half the trade value. By Stage III it trades *once a week*. A
position you need out of on a Tuesday waits until the following Monday.

**Liquidity.** A position worth twenty times a stock's daily turnover is not a
position, it is a commitment. The only honest way to size here is to start from
how many days the exit takes and work backwards.

So this module inverts the usual order. It asks what the exit costs first, and
only then whether the business is any good — because a wonderful business you
cannot sell is worth less than an ordinary one you can.

Rules encoded here follow the exchanges' published surveillance framework and
change often; the stage a scrip currently sits in must come from the daily
exchange file, never from memory.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field

# Participation rates. Far lower than the 25% used for large caps, because in a
# thin stock your own order IS the volume — and the historical daily turnover
# you are sizing against was itself partly other people doing the same thing.
SAFE_PARTICIPATION = 0.10
ACCEPTABLE_EXIT_DAYS = 5

# What each surveillance stage actually does to you. The consequence, not the
# label, is what a position holder needs to know.
SURVEILLANCE = {
    "none": ("", 0),
    "esm_1": ("Enhanced Surveillance: price band narrowed, usually to 5%.", 2),
    "esm_2": ("Enhanced Surveillance stage 2: trade-for-trade and a 2% or 5% band.", 3),
    "asm_short": ("Short-term Additional Surveillance: margins raised, band cut.", 2),
    "asm_long": ("Long-term Additional Surveillance: 100% margin, narrow band.", 3),
    "gsm_1": ("Graded Surveillance stage 1: trade-for-trade, 5% band.", 3),
    "gsm_2": ("Graded Surveillance stage 2: trade-for-trade plus a surveillance "
              "deposit of 50% of trade value, blocked for months.", 4),
    "gsm_3": ("Graded Surveillance stage 3: trading permitted ONCE A WEEK, "
              "deposit 100% of trade value.", 5),
    "gsm_4": ("Graded Surveillance stage 4: weekly trading, 100% deposit, and a "
              "band that ratchets down. Exit is effectively at the exchange's "
              "discretion.", 5),
    "t2t": ("Trade-for-trade: no intraday, delivery compulsory, typically a 5% band.", 2),
}


@dataclass
class ExitAnalysis:
    position_value: float
    median_daily_turnover: float
    participation: float
    days_to_exit: float
    impact_cost_pct: float
    round_trip_cost_pct: float
    max_safe_position: float
    circuit_band: float
    locked_days_for_30pct_fall: float
    verdict: str
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def days_to_exit(position_value: float, median_daily_turnover: float,
                 participation: float = SAFE_PARTICIPATION) -> float | None:
    """Sessions needed to liquidate without being the whole market.

    The number retail investors never compute and institutions compute first.
    """
    if median_daily_turnover is None or median_daily_turnover <= 0:
        return None
    if position_value <= 0:
        return 0.0
    return position_value / (median_daily_turnover * participation)


def max_safe_position(median_daily_turnover: float,
                      participation: float = SAFE_PARTICIPATION,
                      acceptable_days: int = ACCEPTABLE_EXIT_DAYS) -> float | None:
    """The largest position you can still get out of in a working week.

    This is the binding constraint in micro-caps, and it binds long before any
    conviction-based or volatility-based limit does. Conviction cannot buy
    liquidity.
    """
    if median_daily_turnover is None or median_daily_turnover <= 0:
        return None
    return median_daily_turnover * participation * acceptable_days


def impact_cost(position_value: float, median_daily_turnover: float,
                daily_vol: float, spread_pct: float = 0.01) -> float | None:
    """What moving this size actually costs, one way.

    The square-root law: impact grows with the square root of the fraction of
    daily volume you take, scaled by the stock's own volatility. It is the
    practitioner standard because it fits observed execution data far better
    than a linear model, which badly understates large orders.

    Half the quoted spread is added because you cross it on the way in and
    again on the way out, and in a penny stock that spread is often 1-3% rather
    than the basis points a large cap shows.
    """
    if not median_daily_turnover or median_daily_turnover <= 0 or daily_vol is None:
        return None
    frac = position_value / median_daily_turnover
    return spread_pct / 2 + daily_vol * math.sqrt(max(0.0, frac))


def locked_days_to_fall(target_fall: float, band: float) -> float | None:
    """Consecutive limit-down sessions a given fall requires.

    Worth stating because it reframes the risk entirely: in a 5% band, a 30%
    fall is not one bad day you might have sold into. It is six sessions during
    which no sale was possible at any price.
    """
    if not (0 < band < 1) or not (0 < target_fall < 1):
        return None
    return math.log(1 - target_fall) / math.log(1 - band)


def circuit_hit_rate(closes: list[float], band: float) -> float | None:
    """How often this stock has actually closed at its limit.

    Measured, not assumed. A scrip that locks twice a month is telling you what
    its exit looks like on the day you need one.
    """
    if not closes or len(closes) < 40 or not (0 < band < 1):
        return None
    hits = 0
    for a, b in zip(closes, closes[1:]):
        if a > 0 and abs(b / a - 1) >= band * 0.98:
            hits += 1
    return hits / (len(closes) - 1)


def surveillance_veto(stage: str | None) -> dict:
    """Whether the exchange has already made this position hard to leave."""
    key = (stage or "none").lower()
    note, severity = SURVEILLANCE.get(key, ("Unrecognised surveillance stage — "
                                            "treat as restricted until confirmed.", 4))
    return {
        "stage": key,
        "severity": severity,
        "blocked": severity >= 3,
        "note": note or "No surveillance measure recorded against this scrip.",
        "why_it_matters": (
            "Surveillance stages are the exchange saying it does not trust the "
            "price formation in this scrip. Whatever the business is worth, the "
            "exit is now on the exchange's terms rather than yours."
            if severity >= 3 else ""),
    }


def analyse_exit(position_value: float, median_daily_turnover: float,
                 daily_vol: float, band: float = 0.05,
                 spread_pct: float = 0.015,
                 closes: list[float] | None = None) -> ExitAnalysis:
    """The full exit picture, before any question about the business."""
    warnings: list[str] = []
    d = days_to_exit(position_value, median_daily_turnover)
    cap = max_safe_position(median_daily_turnover)
    one_way = impact_cost(position_value, median_daily_turnover, daily_vol, spread_pct)
    round_trip = one_way * 2 if one_way is not None else None
    locked = locked_days_to_fall(0.30, band)

    if d is None:
        warnings.append("No turnover data — position size cannot be justified at all.")
    elif d > ACCEPTABLE_EXIT_DAYS:
        warnings.append(
            f"Exiting this position takes about {d:.0f} sessions at a safe "
            f"participation rate. Anything that forces a faster exit will be paid "
            f"for in price.")
    if round_trip is not None and round_trip > 0.05:
        warnings.append(
            f"Getting in and out costs roughly {round_trip * 100:.1f}% before the "
            f"stock does anything. The idea has to clear that before it earns a rupee.")
    if band <= 0.05:
        warnings.append(
            f"A {band * 100:.0f}% circuit band means a 30% fall takes about "
            f"{locked:.0f} locked sessions with no buyers. A stop-loss cannot "
            f"execute inside a circuit.")
    hit = circuit_hit_rate(closes, band) if closes else None
    if hit is not None and hit > 0.03:
        warnings.append(
            f"This scrip has closed at its limit on {hit * 100:.0f}% of sessions — "
            f"locking is its normal behaviour, not an exception.")

    if d is None:
        verdict = "cannot size this — no liquidity data"
    elif d > ACCEPTABLE_EXIT_DAYS * 3:
        verdict = "not investable at this size; the exit is the whole risk"
    elif d > ACCEPTABLE_EXIT_DAYS:
        verdict = "oversized — cut to the safe position below"
    else:
        verdict = "exitable within a working week at this size"

    return ExitAnalysis(
        position_value=position_value,
        median_daily_turnover=median_daily_turnover,
        participation=SAFE_PARTICIPATION,
        days_to_exit=d if d is not None else float("inf"),
        impact_cost_pct=one_way if one_way is not None else float("nan"),
        round_trip_cost_pct=round_trip if round_trip is not None else float("nan"),
        max_safe_position=cap if cap is not None else 0.0,
        circuit_band=band,
        locked_days_for_30pct_fall=locked if locked is not None else float("nan"),
        verdict=verdict, warnings=warnings,
    )


# --------------------------------------------------------------------------
# the markers that separate a small company from a story
# --------------------------------------------------------------------------
FRAUD_MARKERS = (
    ("auditor_resigned", "The auditor resigned",
     "The single most predictive warning there is. Auditors rarely resign over "
     "nothing, and they resign before the problem is public."),
    ("promoter_pledge_high", "Promoters have pledged most of their holding",
     "A pledged promoter is a forced seller if the price falls, which turns an "
     "ordinary decline into a cascade."),
    ("frequent_preferential", "Repeated preferential allotments or warrants",
     "Capital raised at a discount to people who are not you, diluting the "
     "holding you paid full price for."),
    ("negative_networth", "Negative net worth",
     "The accumulated losses exceed everything shareholders ever put in."),
    ("name_changed_recently", "The company changed its name recently",
     "Not damning alone, and a common cosmetic step before a story is sold — "
     "especially into whatever sector is fashionable."),
    ("audit_qualified", "The audit opinion is qualified",
     "The auditor has said, in the only language available to them, that they "
     "do not agree with the accounts."),
    ("promoter_holding_falling", "Promoter holding is falling",
     "The people who know most about the business are reducing their stake."),
)


def integrity_check(f: dict) -> dict:
    """Markers that override any valuation case.

    None of these is a prediction. Each is a reason the numbers in the accounts
    may not describe the company, and in a segment with thin audit scrutiny that
    possibility deserves to come before the analysis rather than after it.
    """
    fired, unknown = [], []
    for key, label, why in FRAUD_MARKERS:
        v = f.get(key)
        if v is None:
            unknown.append(label)
        elif v:
            fired.append({"marker": label, "why": why})
    return {
        "fired": fired,
        "unknown": unknown,
        "clean": not fired and len(unknown) <= 2,
        "verdict": (
            "integrity markers present — treat the accounts as unverified and the "
            "valuation case as void" if fired else
            f"no marker fired, though {len(unknown)} could not be checked"
            if unknown else "no integrity markers found"),
    }


def screen(f: dict) -> dict:
    """The business question, asked only after the exit and integrity questions.

    Deliberately stricter than the large-cap lenses on exactly two things —
    debt and cash — because in a micro-cap there is no balance-sheet depth to
    absorb a mistake and no analyst coverage to notice one early.
    """
    reasons, against = [], []

    def ok(cond, good, bad):
        if cond is None:
            return None
        (reasons if cond else against).append(good if cond else bad)
        return cond

    profitable = ok(None if f.get("netMargin") is None else f["netMargin"] > 0,
                    "profitable", "loss-making")
    ok(None if f.get("debtToEquity") is None else f["debtToEquity"] <= 0.5,
       "debt is modest", "carries debt a company this size cannot refinance easily")
    ok(None if f.get("cashConversion") is None else f["cashConversion"] >= 0.6,
       "profit turns into cash", "reported profit is not becoming cash")
    ok(None if f.get("revenueGrowth") is None else f["revenueGrowth"] > 0.10,
       "sales growing", "sales flat or shrinking")
    ok(None if f.get("roce") is None else f["roce"] >= 0.12,
       "earns a real return on capital", "returns on capital are poor")
    ok(None if f.get("promoterHolding") is None else f["promoterHolding"] >= 0.40,
       "promoters retain a large stake", "promoters hold little of it themselves")

    judged = len(reasons) + len(against)
    return {
        "judged": judged,
        "for": reasons,
        "against": against,
        "score": len(reasons) / judged if judged else None,
        "profitable": profitable,
        "verdict": ("too little disclosed to judge" if judged < 3 else
                    "a real business on these numbers" if len(reasons) >= judged * 0.7
                    else "the numbers do not support a case"),
    }


def assess(f: dict, position_value: float) -> dict:
    """The whole answer, in the order that matters.

    Exit first, integrity second, business third. That ordering is the argument
    this module makes: in this segment the quality of the company is the least
    binding of the three, because you can be right about the business and still
    lose everything to a circuit you could not sell into.
    """
    veto = surveillance_veto(f.get("surveillance_stage"))
    band = f.get("circuit_band") or (0.05 if veto["severity"] >= 2 else 0.10)
    exit_view = analyse_exit(
        position_value=position_value,
        median_daily_turnover=f.get("medianTurnover") or 0,
        daily_vol=f.get("dailyVol") or 0.05,
        band=band,
        spread_pct=f.get("spread") or 0.015,
        closes=f.get("closes"),
    )
    integrity = integrity_check(f)
    business = screen(f)

    # Each gate must be positively cleared. Absence of evidence is not a pass —
    # a scrip with no turnover data is the most dangerous kind, not the safest,
    # and an earlier version of this let it read as "passes all three gates"
    # while the warnings underneath said no size could be justified.
    if veto["blocked"]:
        headline = ("blocked by the exchange's own surveillance — the business case "
                    "is irrelevant while the exit is restricted")
        investable = False
    elif integrity["fired"]:
        headline = "integrity markers fired — the accounts cannot be relied on"
        investable = False
    elif not exit_view.max_safe_position or exit_view.days_to_exit == float("inf"):
        headline = ("no turnover data — the exit cannot be evaluated, so no size "
                    "can be justified")
        investable = False
    elif exit_view.verdict.startswith("not investable"):
        headline = "the position cannot be exited; size it down or leave it"
        investable = False
    elif exit_view.verdict.startswith("oversized"):
        headline = "oversized for its liquidity — cut to the figure below"
        investable = False
    elif business["score"] is None or business["judged"] < 3:
        headline = "too little disclosed about the business to take a view"
        investable = False
    elif business["verdict"] == "the numbers do not support a case":
        headline = "exitable and clean, but the business case is not there"
        investable = False
    elif not integrity["clean"]:
        headline = ("exitable, but too many integrity markers could not be checked "
                    "to call this clean")
        investable = False
    else:
        headline = "passes all three gates at this size"
        investable = True

    # The realistic return: whatever the idea is worth, less what it costs to
    # express. In this segment that subtraction changes the answer more often
    # than any analytical judgement does.
    rt = exit_view.round_trip_cost_pct
    return {
        "investable": investable,
        "headline": headline,
        "surveillance": veto,
        "exit": exit_view.to_dict(),
        "integrity": integrity,
        "business": business,
        "cost_hurdle": (None if rt != rt else rt),
        "cost_note": (None if rt != rt else
                      f"Any thesis here has to be worth more than "
                      f"{rt * 100:.1f}% before it is worth anything at all."),
        "position_advice": (
            f"Cap this at {exit_view.max_safe_position:,.0f} so it can be exited "
            f"inside a week." if exit_view.max_safe_position else
            "No turnover data, so no size can be justified."),
    }
