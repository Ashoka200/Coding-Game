"""Valuation: what is the business worth, and what does today's price assume?

Three lenses, deliberately triangulated rather than trusting one number
(knowledge module 02):

1. INTRINSIC   — FCFF discounted at WACC, terminal value by Gordon growth.
2. REVERSE DCF — the more useful direction: hold the price fixed and solve for
                 the growth rate it already assumes. You then judge whether that
                 hurdle is plausible, instead of pretending to forecast precisely.
3. RELATIVE    — multiples against the company's own history and its sector.

Nothing here invents an input. A missing figure produces an `unknown` entry and
the affected lens is skipped — a DCF built on guessed inputs is worse than no
DCF, because it launders a guess into a number with two decimal places.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

# India-specific capital-market assumptions, stated so they can be argued with.
RISK_FREE = 0.070          # ~10-year G-Sec
EQUITY_RISK_PREMIUM = 0.055
DEFAULT_BETA = 1.0
DEFAULT_TAX = 0.25         # headline corporate rate after the 2019 cut
TERMINAL_GROWTH = 0.045    # below nominal GDP; a business cannot outgrow its economy forever
PROJECTION_YEARS = 10
MAX_TERMINAL_SHARE = 0.60  # above this the "valuation" is mostly a terminal guess


@dataclass
class Lens:
    name: str
    value_per_share: float | None
    detail: dict = field(default_factory=dict)
    caveats: list[str] = field(default_factory=list)


@dataclass
class Valuation:
    symbol: str
    price: float | None
    lenses: list[Lens] = field(default_factory=list)
    fair_value_low: float | None = None
    fair_value_base: float | None = None
    fair_value_high: float | None = None
    margin_of_safety: float | None = None      # (base - price) / base
    implied_growth: float | None = None        # what the price already assumes
    verdict: str | None = None
    unknowns: list[dict] = field(default_factory=list)
    caveats: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["lenses"] = [asdict(l) if not isinstance(l, dict) else l for l in self.lenses]
        return d


def cost_of_equity(beta: float | None = None) -> float:
    return RISK_FREE + (beta if beta is not None else DEFAULT_BETA) * EQUITY_RISK_PREMIUM


def wacc(equity_value: float, debt: float, beta: float | None = None,
         cost_of_debt: float | None = None, tax: float = DEFAULT_TAX) -> float:
    """Weighted average cost of capital. Falls back to cost of equity when the
    capital structure is unknown — and says so via the caller's caveats."""
    ke = cost_of_equity(beta)
    if not debt or equity_value <= 0:
        return ke
    kd = cost_of_debt if cost_of_debt is not None else RISK_FREE + 0.020
    total = equity_value + debt
    return (equity_value / total) * ke + (debt / total) * kd * (1 - tax)


def dcf(fcff: float, growth: float, discount: float, shares: float,
        net_debt: float = 0.0, years: int = PROJECTION_YEARS,
        terminal_growth: float = TERMINAL_GROWTH,
        fade: bool = True) -> tuple[float, dict]:
    """Value per share from free cash flow to the firm.

    `fade` linearly decays the growth rate toward terminal growth over the
    projection window — a high rate held flat for ten years is the single most
    common way a DCF flatters a business.
    """
    if discount <= terminal_growth:
        raise ValueError("discount rate must exceed terminal growth")
    if shares <= 0:
        raise ValueError("share count must be positive")

    pv_explicit = 0.0
    cash = fcff
    for year in range(1, years + 1):
        g = (growth + (terminal_growth - growth) * (year - 1) / max(years - 1, 1)
             if fade else growth)
        cash *= (1 + g)
        pv_explicit += cash / ((1 + discount) ** year)

    terminal_cash = cash * (1 + terminal_growth)
    terminal_value = terminal_cash / (discount - terminal_growth)
    pv_terminal = terminal_value / ((1 + discount) ** years)

    enterprise = pv_explicit + pv_terminal
    equity = enterprise - net_debt
    per_share = equity / shares
    detail = {
        "enterprise_value": round(enterprise, 2),
        "equity_value": round(equity, 2),
        "pv_explicit": round(pv_explicit, 2),
        "pv_terminal": round(pv_terminal, 2),
        "terminal_share": round(pv_terminal / enterprise, 3) if enterprise else None,
        "discount_rate": round(discount, 4),
        "starting_growth": round(growth, 4),
        "terminal_growth": terminal_growth,
        "years": years,
    }
    return per_share, detail


def implied_growth(price: float, fcff: float, discount: float, shares: float,
                   net_debt: float = 0.0, years: int = PROJECTION_YEARS,
                   terminal_growth: float = TERMINAL_GROWTH) -> float | None:
    """Reverse DCF: what growth does the current price already assume?

    Solved by bisection. Returns None when no rate in a sane band explains the
    price — itself informative: the price implies something outside 0–60% growth.
    """
    if price <= 0 or shares <= 0 or fcff <= 0:
        return None
    lo, hi = -0.20, 0.60

    def value_at(g: float) -> float:
        return dcf(fcff, g, discount, shares, net_debt, years, terminal_growth)[0]

    try:
        if value_at(lo) > price or value_at(hi) < price:
            return None
    except ValueError:
        return None
    for _ in range(80):
        mid = (lo + hi) / 2
        if value_at(mid) < price:
            lo = mid
        else:
            hi = mid
    return round((lo + hi) / 2, 4)


def relative_value(eps: float | None, book_value: float | None,
                   sector_pe: float | None, sector_pb: float | None) -> Lens:
    """Multiples applied to the company's own earnings and book."""
    values, notes = [], []
    if eps and eps > 0 and sector_pe and sector_pe > 0:
        values.append(eps * sector_pe)
        notes.append(f"EPS {eps:.2f} × sector P/E {sector_pe:.1f}")
    if book_value and book_value > 0 and sector_pb and sector_pb > 0:
        values.append(book_value * sector_pb)
        notes.append(f"book {book_value:.2f} × sector P/B {sector_pb:.1f}")
    if not values:
        return Lens("relative", None, {},
                    ["Needs EPS or book value plus a sector multiple; not available."])
    return Lens("relative", round(sum(values) / len(values), 2),
                {"components": notes},
                ["A sector multiple imports the sector's mood, including its mistakes."])


def sum_of_parts(segments: list[dict], net_debt: float, shares: float) -> Lens:
    """Conglomerates (Reliance, ITC, Grasim) are worth the sum of their businesses.

    Each segment: {name, metric_value, multiple, basis}. Nothing is assumed —
    a segment without a multiple is skipped and named in the caveats.
    """
    total, used, skipped = 0.0, [], []
    for seg in segments:
        mv, mult = seg.get("metric_value"), seg.get("multiple")
        if mv is None or mult is None:
            skipped.append(seg.get("name", "unnamed segment"))
            continue
        value = mv * mult
        total += value
        used.append({"name": seg.get("name"), "basis": seg.get("basis"),
                     "value": round(value, 2)})
    if not used or shares <= 0:
        return Lens("sum_of_parts", None, {"segments": used},
                    ["Not enough segment detail to value the parts."])
    per_share = (total - net_debt) / shares
    caveats = ["Segment multiples are judgement, not observation."]
    if skipped:
        caveats.append(f"Skipped for want of a multiple: {', '.join(skipped)}.")
    return Lens("sum_of_parts", round(per_share, 2),
                {"segments": used, "gross_value": round(total, 2),
                 "net_debt": net_debt}, caveats)


def value_company(symbol: str, price: float | None, inputs: dict) -> Valuation:
    """Run every lens the available inputs support.

    inputs may contain: fcff, shares, net_debt, beta, eps, book_value,
    sector_pe, sector_pb, growth, segments, cost_of_debt.
    """
    v = Valuation(symbol=symbol, price=price)
    unknown = v.unknowns.append

    fcff = inputs.get("fcff")
    shares = inputs.get("shares")
    net_debt = inputs.get("net_debt") or 0.0
    beta = inputs.get("beta")
    growth = inputs.get("growth")

    if price is None:
        unknown({"field": "price", "reason": "no market price supplied"})

    # --- intrinsic ---
    if fcff and shares and fcff > 0 and shares > 0:
        equity_mkt = (price or 0) * shares
        rate = wacc(equity_mkt, inputs.get("total_debt") or 0.0, beta,
                    inputs.get("cost_of_debt"))
        g = growth if growth is not None else 0.10
        base, detail = dcf(fcff, g, rate, shares, net_debt)
        caveats = []
        if growth is None:
            caveats.append("No growth estimate supplied, so 10% was used as a "
                           "neutral placeholder — treat the level as illustrative "
                           "and rely on the reverse DCF instead.")
        if detail["terminal_share"] and detail["terminal_share"] > MAX_TERMINAL_SHARE:
            caveats.append(f"{detail['terminal_share']:.0%} of this value sits in the "
                           "terminal assumption, which makes it closer to a guess "
                           "than a valuation.")
        v.lenses.append(Lens("dcf", round(base, 2), detail, caveats))

        # bear / bull by moving growth, not by fudging the discount rate
        bear = dcf(fcff, max(g - 0.06, -0.02), rate + 0.01, shares, net_debt)[0]
        bull = dcf(fcff, g + 0.05, max(rate - 0.01, TERMINAL_GROWTH + 0.02),
                   shares, net_debt)[0]
        v.fair_value_low, v.fair_value_base, v.fair_value_high = (
            round(bear, 2), round(base, 2), round(bull, 2))

        if price:
            v.implied_growth = implied_growth(price, fcff, rate, shares, net_debt)
    else:
        for field_name in ("fcff", "shares"):
            if not inputs.get(field_name):
                unknown({"field": field_name,
                         "reason": "required for a discounted cash flow; the lens was skipped"})

    # --- relative ---
    rel = relative_value(inputs.get("eps"), inputs.get("book_value"),
                         inputs.get("sector_pe"), inputs.get("sector_pb"))
    v.lenses.append(rel)
    if rel.value_per_share is None:
        unknown({"field": "sector multiples", "reason": "no peer set supplied"})

    # --- sum of the parts ---
    if inputs.get("segments"):
        v.lenses.append(sum_of_parts(inputs["segments"], net_debt, shares or 0))

    # --- synthesis ---
    usable = [l.value_per_share for l in v.lenses if l.value_per_share]
    if usable:
        if v.fair_value_base is None:
            v.fair_value_base = round(sum(usable) / len(usable), 2)
            v.fair_value_low = round(min(usable) * 0.85, 2)
            v.fair_value_high = round(max(usable) * 1.15, 2)
        if price:
            v.margin_of_safety = round((v.fair_value_base - price) / v.fair_value_base, 4)
            v.verdict = ("materially cheap" if v.margin_of_safety > 0.30
                         else "cheap" if v.margin_of_safety > 0.15
                         else "around fair" if v.margin_of_safety > -0.15
                         else "expensive" if v.margin_of_safety > -0.35
                         else "priced for perfection")
    else:
        v.verdict = None
        v.caveats.append("No valuation lens had the inputs it needs. This is a gap, "
                         "not a view — do not infer a value from the other tabs.")

    if v.implied_growth is not None:
        v.caveats.append(
            f"At {price:.2f} the market is already assuming about "
            f"{v.implied_growth:.1%} annual cash-flow growth. The question is not "
            "whether the company can grow — it is whether it can beat that.")
    return v
