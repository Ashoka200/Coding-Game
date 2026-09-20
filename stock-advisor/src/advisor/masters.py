"""The great investors, as checklists that actually run.

A quote is not a strategy. "Buy right, sit tight" tells you nothing you can
test; "return on equity above 15% for five straight years, debt below half of
equity, and earnings growing faster than sales" is the same idea in a form that
either passes or fails against a real balance sheet.

So each lens here turns one investor's stated method into criteria the system
can evaluate, and reports three things: which criteria passed, which failed, and
— the part most screeners hide — which could not be judged because the data was
not there. A lens that judged four of nine criteria has not endorsed anything.

Where lenses disagree is more informative than where they agree. A company that
passes Lynch on growth and fails Buffett on debt is not a contradiction; it is
the actual shape of the opportunity, and the consensus function surfaces exactly
that rather than averaging it away.

Sources are the investors' own published frameworks and interviews — Agrawal's
QGLP is stated by Motilal Oswal directly; Jhunjhunwala's method is drawn from
his repeated public account of it. Thresholds are this system's calibration to
Indian large- and mid-caps, not the investors' words, and are marked as such.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .calibrate import MarketContext


@dataclass
class Criterion:
    name: str
    passed: bool | None          # None means: could not be judged
    seen: str                    # what the number actually was
    why: str                     # why this criterion is in the list at all
    # Each lens words its criteria in its own author's language, so agreement
    # between lenses cannot be found by matching names — "Little debt" and
    # "Balance sheet not stretched" are the same concern. The theme is what
    # makes cross-lens comparison mean anything.
    theme: str = "other"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class LensVerdict:
    lens: str
    author: str
    idea: str
    score: float | None          # share of judged criteria passed
    judged: int
    unknown: int
    criteria: list[Criterion] = field(default_factory=list)
    verdict: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["criteria"] = [c.to_dict() for c in self.criteria]
        return d


# --------------------------------------------------------------------------
# helpers — every one of them returns None rather than guessing
# --------------------------------------------------------------------------
def _pct(x) -> str:
    return "not disclosed" if x is None else f"{x * 100:.1f}%"


def _num(x, d=2) -> str:
    return "not disclosed" if x is None else f"{x:.{d}f}"


def _ge(value, threshold) -> bool | None:
    return None if value is None else value >= threshold


def _le(value, threshold) -> bool | None:
    return None if value is None else value <= threshold


def _c(ctx, metric, f, stance, fallback_passed, fallback_seen):
    """Return (passed, seen) judged against live peers, or the fixed fallback."""
    value = f.get(metric)
    if ctx is not None and value is not None:
        judged = ctx.meets(metric, value, stance, f.get("sector"))
        if judged is not None:
            return judged, ctx.describe(metric, value, f.get("sector"))
    return fallback_passed, fallback_seen


def _adapt(ctx, metric, value, stance, fallback_test, sector=None):
    """Judge against today's peers when a market context exists, else the old
    fixed threshold.

    The stance is the doctrine and stays in the code: Damani is demanding on
    debt, Buffett moderate, and that difference is what makes them different
    investors. The level the stance corresponds to belongs to the market and is
    read off the live cross-section.
    """
    if ctx is not None:
        judged = ctx.meets(metric, value, stance, sector)
        if judged is not None:
            return judged, ctx.describe(metric, value, sector)
    return fallback_test, None


def _between(value, lo, hi) -> bool | None:
    return None if value is None else lo <= value <= hi


def _score(criteria: list[Criterion]) -> tuple[float | None, int, int]:
    judged = [c for c in criteria if c.passed is not None]
    unknown = len(criteria) - len(judged)
    if not judged:
        return None, 0, unknown
    return sum(1 for c in judged if c.passed) / len(judged), len(judged), unknown


def _verdict(score, judged, unknown, total) -> str:
    if score is None:
        return "cannot judge — none of the criteria had data behind them"
    if unknown > total / 2:
        return (f"too thin to rely on — only {judged} of {total} criteria could be "
                f"judged, so this is a hint, not a finding")
    if score >= 0.85:
        return "passes this lens cleanly"
    if score >= 0.6:
        return "mostly passes, with the failures below worth understanding"
    if score >= 0.35:
        return "fails more than it passes on this lens"
    return "this lens rejects it"


def _consistency(series: list[float] | None, min_years: int = 4) -> bool | None:
    """Did the line grow in most years, rather than once spectacularly?

    Longevity is the criterion nearly every screener skips, because it needs
    history rather than a snapshot. A company that grew 80% once and 2% for four
    years has the same five-year CAGR as one that grew 15% every year, and they
    are not remotely the same business.
    """
    if not series or len(series) < min_years + 1:
        return None
    ups = sum(1 for a, b in zip(series, series[1:]) if a and b and b > a)
    return ups >= (len(series) - 1) * 0.7


# --------------------------------------------------------------------------
# the lenses
# --------------------------------------------------------------------------
def qglp(f: dict, ctx: MarketContext | None = None) -> LensVerdict:
    """Raamdeo Agrawal's QGLP — Quality, Growth, Longevity, Price.

    Agrawal's own ordering matters and is preserved here: price comes last. A
    wonderful business at a fair price beats a fair business at a wonderful
    price, so a Price failure is reported but never vetoes the other three.
    """
    hist = f.get("revenue_history")
    c = [
        Criterion("Quality of business — returns on capital",
                  *_c(ctx, "roce", f, "moderate",
                      _ge(f.get("roce"), 0.15), _pct(f.get("roce"))),
                  "A business earning less on capital than it costs is shrinking "
                  "in real terms however fast revenue grows.", theme="returns"),
        Criterion("Quality of balance sheet — low debt",
                  *_c(ctx, "debtToEquity", f, "strict",
                      _le(f.get("debtToEquity"), 0.5), _num(f.get("debtToEquity"))),
                  "Leverage is what turns a bad few quarters into a permanent loss.", theme="debt"),
        Criterion("Quality of earnings — profit converts to cash",
                  _ge(f.get("cashConversion"), 0.75), _num(f.get("cashConversion")),
                  "Profit that never becomes cash is the most common prelude to a "
                  "restatement.", theme="cash"),
        Criterion("Growth — earnings compounding",
                  _ge(f.get("earningsCagr3y") or f.get("earningsGrowth"), 0.15),
                  _pct(f.get("earningsCagr3y") or f.get("earningsGrowth")),
                  "Over a decade the share price follows earnings and almost "
                  "nothing else.", theme="growth"),
        Criterion("Growth is real — sales grow too",
                  _ge(f.get("revenueCagr3y") or f.get("revenueGrowth"), 0.10),
                  _pct(f.get("revenueCagr3y") or f.get("revenueGrowth")),
                  "Profit growing without sales growing is cost-cutting, and cost "
                  "cutting has a floor.", theme="growth"),
        Criterion("Longevity — growth in most years, not one",
                  _consistency(hist), "history not available" if hist is None
                  else f"{len(hist)} years on record",
                  "Sustained compounding is the whole thesis; one good year is noise.", theme="consistency"),
        Criterion("Longevity — reinvests at high returns",
                  *_c(ctx, "roe", f, "moderate",
                      _ge(f.get("roe"), 0.15), _pct(f.get("roe"))),
                  "A compounder must be able to put retained profit back to work "
                  "at the same rate it earned it.", theme="returns"),
        Criterion("Price — not paying for a decade in advance",
                  _le(f.get("peg"), 1.5), _num(f.get("peg")),
                  "Agrawal puts price last, not nowhere: a great business bought "
                  "at any price is still a bad investment.", theme="price"),
    ]
    s, j, u = _score(c)
    return LensVerdict(
        lens="QGLP", author="Raamdeo Agrawal",
        idea="Quality, Growth, Longevity, Price — in that order, price last.",
        score=s, judged=j, unknown=u, criteria=c,
        verdict=_verdict(s, j, u, len(c)))


def jhunjhunwala(f: dict, ctx: MarketContext | None = None) -> LensVerdict:
    """Rakesh Jhunjhunwala's method, as he described it repeatedly.

    Two things distinguish it from a pure value screen and both are encoded.
    First, durable demand: he favoured what people would still be buying in ten
    years, which is a judgement about the product, not the multiple. Second,
    "markets are supreme" — he was a trader as well as an investor and did not
    fight the tape, so a stock below its long-term average fails this lens even
    when the business passes.
    """
    sector = (f.get("sector") or "").lower()
    durable = any(k in sector for k in (
        "consum", "fmcg", "pharma", "health", "bank", "financ", "insur", "auto",
        "retail", "jewel", "paint", "food", "beverage"))
    c = [
        Criterion("Earnings compounding hard",
                  _ge(f.get("earningsCagr3y") or f.get("earningsGrowth"), 0.20),
                  _pct(f.get("earningsCagr3y") or f.get("earningsGrowth")),
                  "He bought growth early and held it; 20% compounding doubles "
                  "money in under four years.", theme="growth"),
        Criterion("High return on equity",
                  *_c(ctx, "roe", f, "strict",
                      _ge(f.get("roe"), 0.18), _pct(f.get("roe"))),
                  "The engine of compounding — a low-ROE business cannot compound "
                  "however cheap it looks.", theme="returns"),
        Criterion("Debt under control",
                  *_c(ctx, "debtToEquity", f, "lenient",
                      _le(f.get("debtToEquity"), 0.6), _num(f.get("debtToEquity"))),
                  "He concentrated heavily, and concentration plus leverage is how "
                  "investors are permanently removed from the game.", theme="debt"),
        Criterion("Durable demand — needed in ten years",
                  durable if f.get("sector") else None,
                  f.get("sector") or "sector not identified",
                  "His stated test: if people need it today they will need it in "
                  "ten years. Jewellery, medicines, cars, insurance.", theme="demand"),
        Criterion("Not already priced for perfection",
                  *_c(ctx, "pe", f, "lenient",
                      _le(f.get("pe"), 40), _num(f.get("pe"), 1)),
                  "He bought before the story was consensus, not after.", theme="price"),
        Criterion("The tape agrees — above its long-term average",
                  f.get("above200dma"), "not computed"
                  if f.get("above200dma") is None
                  else ("above" if f.get("above200dma") else "below"),
                  "\"Markets are supreme.\" He respected the trend and did not "
                  "argue with a falling price.", theme="tape"),
    ]
    s, j, u = _score(c)
    return LensVerdict(
        lens="Buy early, sit tight", author="Rakesh Jhunjhunwala",
        idea="Compounding earnings in businesses people will still need in a "
             "decade — bought before consensus, held through noise, and never "
             "against the tape.",
        score=s, judged=j, unknown=u, criteria=c,
        verdict=_verdict(s, j, u, len(c)))


def buffett(f: dict, ctx: MarketContext | None = None) -> LensVerdict:
    """Owner-earnings: would you buy the whole business at this price?"""
    c = [
        Criterion("Consistently high return on equity",
                  *_c(ctx, "roe", f, "moderate",
                      _ge(f.get("roe"), 0.15), _pct(f.get("roe"))),
                  "The single number that best separates a franchise from a "
                  "commodity.", theme="returns"),
        Criterion("Little debt",
                  *_c(ctx, "debtToEquity", f, "moderate",
                      _le(f.get("debtToEquity"), 0.5), _num(f.get("debtToEquity"))),
                  "A good business with too much debt is a bad investment.", theme="debt"),
        Criterion("Wide, durable margins",
                  *_c(ctx, "netMargin", f, "moderate",
                      _ge(f.get("netMargin"), 0.10), _pct(f.get("netMargin"))),
                  "Margin is pricing power made visible.", theme="margin"),
        Criterion("Interest comfortably covered",
                  _ge(f.get("interestCover"), 5), _num(f.get("interestCover"), 1),
                  "Solvency is not a valuation question; it is a survival one.", theme="solvency"),
        Criterion("Profit turns into cash",
                  _ge(f.get("cashConversion"), 0.80), _num(f.get("cashConversion")),
                  "Owner earnings, not reported earnings, are what an owner gets.", theme="cash"),
        Criterion("Priced sensibly",
                  *_c(ctx, "pe", f, "moderate",
                      _le(f.get("pe"), 25), _num(f.get("pe"), 1)),
                  "Price is what you pay; value is what you get.", theme="price"),
    ]
    s, j, u = _score(c)
    return LensVerdict(
        lens="Owner earnings", author="Warren Buffett",
        idea="A business you would be happy to own outright, bought at a price "
             "that leaves room for being wrong.",
        score=s, judged=j, unknown=u, criteria=c,
        verdict=_verdict(s, j, u, len(c)))


def lynch(f: dict, ctx: MarketContext | None = None) -> LensVerdict:
    """Growth at a reasonable price, with Lynch's own upper bound on growth.

    The detail usually dropped from PEG screens: Lynch distrusted growth above
    roughly 50%, because it attracts competition and cannot persist. Encoding
    only the lower bound turns his method into a momentum screen.
    """
    g = f.get("earningsCagr3y") or f.get("earningsGrowth")
    c = [
        Criterion("Growth you are not overpaying for",
                  _le(f.get("peg"), 1.0), _num(f.get("peg")),
                  "The PEG ratio — his one genuinely original contribution.", theme="price"),
        Criterion("Growing fast, but not implausibly",
                  _between(g, 0.15, 0.50), _pct(g),
                  "Above roughly 50% growth invites competition and cannot last.", theme="growth"),
        Criterion("Balance sheet not stretched",
                  *_c(ctx, "debtToEquity", f, "moderate",
                      _le(f.get("debtToEquity"), 0.5), _num(f.get("debtToEquity"))),
                  "Debt is what stops a good story surviving a bad year.", theme="debt"),
        Criterion("Can pay its near-term bills",
                  _ge(f.get("currentRatio"), 1.5), _num(f.get("currentRatio")),
                  "Working capital is where growth companies die.", theme="solvency"),
    ]
    s, j, u = _score(c)
    return LensVerdict(
        lens="Growth at a reasonable price", author="Peter Lynch",
        idea="Buy growth, but never at a price that assumes it continues forever.",
        score=s, judged=j, unknown=u, criteria=c,
        verdict=_verdict(s, j, u, len(c)))


def damani(f: dict, ctx: MarketContext | None = None) -> LensVerdict:
    """Radhakishan Damani's patience: dull, cash-generative, barely leveraged.

    The lens that most often disagrees with the others, and usefully so — it
    rejects exciting businesses on principle. Its criteria are deliberately
    stricter on debt and looser on growth than every other lens here.
    """
    hist = f.get("revenue_history")
    c = [
        Criterion("Almost no debt",
                  *_c(ctx, "debtToEquity", f, "demanding",
                      _le(f.get("debtToEquity"), 0.3), _num(f.get("debtToEquity"))),
                  "Survives every cycle without needing anyone's permission.", theme="debt"),
        Criterion("High return on capital employed",
                  *_c(ctx, "roce", f, "strict",
                      _ge(f.get("roce"), 0.18), _pct(f.get("roce"))),
                  "Efficiency of the whole business, not just the equity slice.", theme="returns"),
        Criterion("Grows every year, dully",
                  _consistency(hist, min_years=5),
                  "history not available" if hist is None else f"{len(hist)} years",
                  "He held for decades; the question is not how fast but how "
                  "reliably.", theme="consistency"),
        Criterion("Returns capital to owners",
                  _ge(f.get("dividendYield"), 0.005), _pct(f.get("dividendYield")),
                  "A business that cannot pay anything out for years is "
                  "reinvesting or lying.", theme="payout"),
        Criterion("Not a wild ride",
                  *_c(ctx, "annualVol", f, "moderate",
                      _le(f.get("annualVol"), 0.40), _pct(f.get("annualVol"))),
                  "Volatility you can sit through is what makes a decades-long "
                  "hold possible at all.", theme="volatility"),
    ]
    s, j, u = _score(c)
    return LensVerdict(
        lens="Dull and durable", author="Radhakishan Damani",
        idea="Boring, cash-generative, almost unleveraged businesses held for "
             "decades rather than quarters.",
        score=s, judged=j, unknown=u, criteria=c,
        verdict=_verdict(s, j, u, len(c)))


LENSES = (qglp, jhunjhunwala, buffett, lynch, damani)


def derive(f: dict) -> dict:
    """Fill in the couple of ratios the lenses need but the sources do not give.

    PEG is computed here rather than taken from a data vendor because vendors
    differ on which growth rate they use, and a PEG built on a different growth
    number than the one displayed beside it is a quiet inconsistency.
    """
    out = dict(f)
    g = out.get("earningsCagr3y") or out.get("earningsGrowth")
    pe = out.get("pe")
    if out.get("peg") is None:
        # Growth must be positive and real for a PEG to mean anything; a PEG
        # computed off a shrinking business is arithmetic without meaning.
        out["peg"] = (pe / (g * 100)) if (pe and pe > 0 and g and g > 0.01) else None
    return out


def apply_all(f: dict, ctx: MarketContext | None = None) -> list[LensVerdict]:
    """Run every lens. With a market context the thresholds are read off today's
    cross-section; without one they fall back to the fixed levels, so a thin
    data day degrades to the old behaviour rather than to no behaviour."""
    facts = derive(f)
    return [lens(facts, ctx) for lens in LENSES]


def consensus(verdicts: list[LensVerdict]) -> dict:
    """What the lenses agree on, and — more usefully — where they split.

    Averaging five scores into one number destroys the only information worth
    having. A company that Lynch loves and Damani rejects is telling you it is
    a fast grower carrying debt, and that is a decision about what kind of risk
    you want, not a number to be smoothed away.
    """
    usable = [v for v in verdicts if v.score is not None]
    if not usable:
        return {"ok": False,
                "why": "no lens had enough data to judge this company",
                "agree": [], "split": []}

    passes = [v for v in usable if v.score >= 0.6]
    fails = [v for v in usable if v.score < 0.35]

    # Where do independent methods agree, once their different wordings are
    # reduced to the concern underneath? Two lenses failing on "debt" is a real
    # signal; two lenses failing on differently-named criteria is not comparable
    # at all, which is why this groups by theme.
    by_theme: dict[str, list[bool]] = {}
    for v in usable:
        for c in v.criteria:
            if c.passed is not None and c.theme != "other":
                by_theme.setdefault(c.theme, []).append(c.passed)

    unanimous_fail = sorted(t for t, r in by_theme.items()
                            if len(r) >= 2 and not any(r))
    unanimous_pass = sorted(t for t, r in by_theme.items()
                            if len(r) >= 2 and all(r))

    if len(passes) >= 4:
        stance = "rare agreement — four or more independent methods accept it"
    elif len(passes) >= 2 and not fails:
        stance = "broad acceptance, no lens actively rejects it"
    elif passes and fails:
        stance = "genuinely contested — read the split below before deciding"
    elif not passes and fails:
        stance = "rejected across the board"
    else:
        stance = "nothing here is compelling in either direction"

    return {
        "ok": True,
        "lenses_judging": len(usable),
        "accepted_by": [v.author for v in passes],
        "rejected_by": [v.author for v in fails],
        "stance": stance,
        "unanimous_strengths": unanimous_pass,
        "unanimous_weaknesses": unanimous_fail,
        "thinnest_evidence": max(usable, key=lambda v: v.unknown).lens
                             if usable else None,
        "split": [
            {"lens": v.lens, "author": v.author,
             "score": round(v.score, 2), "judged": v.judged, "unknown": v.unknown,
             "failed": [c.name for c in v.criteria if c.passed is False]}
            for v in usable
        ],
    }
