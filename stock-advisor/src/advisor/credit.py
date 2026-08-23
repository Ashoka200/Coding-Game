"""Credit and solvency: what kills capital permanently.

A bad stock pick costs you money. A balance-sheet failure costs you the
position. This module implements the forensic screens credit desks actually
use, with two disciplines that matter more than the formulas:

* APPLICABILITY. Altman-Z was fitted on manufacturers and is meaningless for a
  bank, whose entire business is leverage. Applying it anyway produces a
  confident, wrong number. Every score here refuses to run where it does not
  belong and says which lens to use instead.
* PARTIAL DATA. Each score names the components it could not compute. A
  Beneish M-score built from four of its eight ratios is not a Beneish
  M-score, and calling it one launders a guess into a threshold.

Financial-sector companies get their own lens (capital adequacy, asset quality,
credit cost), because for a lender the loan book IS the risk.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

FINANCIAL_SECTORS = {"bank", "banks", "nbfc", "finance", "financial services",
                     "insurance", "housing finance"}

# Covenants typical of Indian corporate debt; used to measure headroom, not to
# assert what any particular loan agreement says.
TYPICAL_COVENANTS = {
    "net_debt_to_ebitda_max": 3.0,
    "interest_cover_min": 2.0,
    "dscr_min": 1.2,
}


@dataclass
class Score:
    name: str
    value: float | None
    band: str | None = None
    applicable: bool = True
    components: dict = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)
    note: str | None = None


@dataclass
class CreditRead:
    symbol: str
    sector_kind: str = "corporate"        # corporate | financial
    scores: list[Score] = field(default_factory=list)
    maturity_wall: dict | None = None
    covenant_headroom: dict | None = None
    flags: list[str] = field(default_factory=list)
    findings: list[str] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)
    verdict: str | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["scores"] = [asdict(s) if not isinstance(s, dict) else s for s in self.scores]
        return d


def _is_financial(sector: str | None) -> bool:
    if not sector:
        return False
    low = sector.lower()
    return any(k in low for k in FINANCIAL_SECTORS)


def _need(d: dict, keys: list[str]) -> list[str]:
    return [k for k in keys if d.get(k) is None]


# --------------------------------------------------------------- Altman Z

def altman_z(f: dict, manufacturer: bool = True, sector: str | None = None) -> Score:
    """Distance from bankruptcy. Two variants, because the original was fitted
    on listed manufacturers and travels badly."""
    if _is_financial(sector):
        return Score("altman_z", None, applicable=False,
                     note="Altman-Z does not apply to banks or lenders: leverage is "
                          "their business model, not a warning sign. Use capital "
                          "adequacy, asset quality and credit cost instead.")

    if manufacturer:
        need = ["working_capital", "total_assets", "retained_earnings", "ebit",
                "market_cap", "total_liabilities", "sales"]
        missing = _need(f, need)
        if missing:
            return Score("altman_z", None, missing=missing,
                         note="Cannot be computed without every component; a partial "
                              "Z-score is not a Z-score.")
        ta = f["total_assets"]
        if ta <= 0 or f["total_liabilities"] <= 0:
            return Score("altman_z", None, note="Total assets and liabilities must be positive.")
        x1, x2 = f["working_capital"] / ta, f["retained_earnings"] / ta
        x3 = f["ebit"] / ta
        x4 = f["market_cap"] / f["total_liabilities"]
        x5 = f["sales"] / ta
        z = 1.2 * x1 + 1.4 * x2 + 3.3 * x3 + 0.6 * x4 + 1.0 * x5
        band = "safe" if z > 2.99 else "grey" if z >= 1.81 else "distress"
        return Score("altman_z", round(z, 2), band,
                     components={"x1_working_capital": round(x1, 3),
                                 "x2_retained_earnings": round(x2, 3),
                                 "x3_ebit": round(x3, 3),
                                 "x4_equity_to_liabilities": round(x4, 3),
                                 "x5_asset_turnover": round(x5, 3)},
                     note="Original Altman-Z for listed manufacturers. Above 2.99 is "
                          "safe, below 1.81 is the distress zone.")

    # Z'' for non-manufacturers and emerging markets: no asset-turnover term,
    # book equity instead of market value, and an emerging-market constant.
    need = ["working_capital", "total_assets", "retained_earnings", "ebit",
            "book_equity", "total_liabilities"]
    missing = _need(f, need)
    if missing:
        return Score("altman_z_double_prime", None, missing=missing,
                     note="Cannot be computed without every component.")
    ta = f["total_assets"]
    if ta <= 0 or f["total_liabilities"] <= 0:
        return Score("altman_z_double_prime", None,
                     note="Total assets and liabilities must be positive.")
    x1, x2 = f["working_capital"] / ta, f["retained_earnings"] / ta
    x3 = f["ebit"] / ta
    x4 = f["book_equity"] / f["total_liabilities"]
    z = 6.56 * x1 + 3.26 * x2 + 6.72 * x3 + 1.05 * x4 + 3.25
    band = "safe" if z > 2.6 else "grey" if z >= 1.1 else "distress"
    return Score("altman_z_double_prime", round(z, 2), band,
                 components={"x1": round(x1, 3), "x2": round(x2, 3),
                             "x3": round(x3, 3), "x4": round(x4, 3)},
                 note="Altman Z'' for non-manufacturers in emerging markets. Above 2.6 "
                      "is safe, below 1.1 is the distress zone.")


# --------------------------------------------------------------- Beneish M

def beneish_m(cur: dict, prev: dict) -> Score:
    """Probability that earnings are being manipulated. Needs two full years."""
    need = ["receivables", "sales", "cogs", "current_assets", "ppe", "securities",
            "total_assets", "depreciation", "sga", "net_income", "cfo",
            "current_liabilities", "long_term_debt"]
    missing = sorted(set(_need(cur, need) + [f"prior_{k}" for k in _need(prev, need)]))
    if missing:
        return Score("beneish_m", None, missing=missing,
                     note="Every one of the eight ratios needs both years. A partial "
                          "M-score is not an M-score.")

    def gm(d):        # gross margin
        return (d["sales"] - d["cogs"]) / d["sales"] if d["sales"] else None

    def safe_div(a, b):
        return a / b if b else None

    dsri = safe_div(safe_div(cur["receivables"], cur["sales"]),
                    safe_div(prev["receivables"], prev["sales"]))
    gmi = safe_div(gm(prev), gm(cur))
    aqi_cur = 1 - (cur["current_assets"] + cur["ppe"] + cur["securities"]) / cur["total_assets"]
    aqi_prev = 1 - (prev["current_assets"] + prev["ppe"] + prev["securities"]) / prev["total_assets"]
    aqi = safe_div(aqi_cur, aqi_prev)
    sgi = safe_div(cur["sales"], prev["sales"])
    dep_rate_cur = safe_div(cur["depreciation"], cur["depreciation"] + cur["ppe"])
    dep_rate_prev = safe_div(prev["depreciation"], prev["depreciation"] + prev["ppe"])
    depi = safe_div(dep_rate_prev, dep_rate_cur)
    sgai = safe_div(safe_div(cur["sga"], cur["sales"]), safe_div(prev["sga"], prev["sales"]))
    lev_cur = safe_div(cur["current_liabilities"] + cur["long_term_debt"], cur["total_assets"])
    lev_prev = safe_div(prev["current_liabilities"] + prev["long_term_debt"], prev["total_assets"])
    lvgi = safe_div(lev_cur, lev_prev)
    tata = safe_div(cur["net_income"] - cur["cfo"], cur["total_assets"])

    parts = {"DSRI": dsri, "GMI": gmi, "AQI": aqi, "SGI": sgi, "DEPI": depi,
             "SGAI": sgai, "LVGI": lvgi, "TATA": tata}
    unusable = [k for k, v in parts.items() if v is None]
    if unusable:
        return Score("beneish_m", None, missing=unusable,
                     note="Some ratios divided by zero; the score cannot be formed.")

    m = (-4.84 + 0.920 * dsri + 0.528 * gmi + 0.404 * aqi + 0.892 * sgi
         + 0.115 * depi - 0.172 * sgai + 4.679 * tata - 0.327 * lvgi)
    band = "flagged" if m > -1.78 else "clean"
    return Score("beneish_m", round(m, 2), band,
                 components={k: round(v, 3) for k, v in parts.items()},
                 note=("Above -1.78 the model flags a raised probability of earnings "
                       "manipulation. It is a screen, not a verdict: honest companies "
                       "with fast growth and rising receivables also trip it. Treat a "
                       "flag as a reason to read the notes to accounts, not as proof."))


# --------------------------------------------------------------- Piotroski F

def piotroski_f(cur: dict, prev: dict) -> Score:
    """Nine binary tests of fundamental improvement. Best on cheap stocks:
    it separates the cheap-and-mending from the cheap-and-dying."""
    tests, missing = {}, []

    def has(*keys):
        for k in keys:
            src = cur if not k.startswith("prev_") else prev
            key = k[5:] if k.startswith("prev_") else k
            if src.get(key) is None:
                missing.append(k)
                return False
        return True

    if has("net_income", "total_assets"):
        tests["roa_positive"] = cur["net_income"] / cur["total_assets"] > 0
    if has("cfo"):
        tests["cfo_positive"] = cur["cfo"] > 0
    if has("net_income", "total_assets", "prev_net_income", "prev_total_assets"):
        tests["roa_improving"] = (cur["net_income"] / cur["total_assets"]
                                  > prev["net_income"] / prev["total_assets"])
    if has("cfo", "net_income", "total_assets"):
        tests["accruals_healthy"] = (cur["cfo"] / cur["total_assets"]
                                     > cur["net_income"] / cur["total_assets"])
    if has("long_term_debt", "total_assets", "prev_long_term_debt", "prev_total_assets"):
        tests["leverage_falling"] = (cur["long_term_debt"] / cur["total_assets"]
                                     < prev["long_term_debt"] / prev["total_assets"])
    if has("current_assets", "current_liabilities",
           "prev_current_assets", "prev_current_liabilities"):
        tests["liquidity_improving"] = (
            cur["current_assets"] / cur["current_liabilities"]
            > prev["current_assets"] / prev["current_liabilities"])
    if has("shares_outstanding", "prev_shares_outstanding"):
        tests["no_dilution"] = cur["shares_outstanding"] <= prev["shares_outstanding"]
    if has("sales", "cogs", "prev_sales", "prev_cogs"):
        tests["margin_improving"] = ((cur["sales"] - cur["cogs"]) / cur["sales"]
                                     > (prev["sales"] - prev["cogs"]) / prev["sales"])
    if has("sales", "total_assets", "prev_sales", "prev_total_assets"):
        tests["turnover_improving"] = (cur["sales"] / cur["total_assets"]
                                       > prev["sales"] / prev["total_assets"])

    if not tests:
        return Score("piotroski_f", None, missing=sorted(set(missing)),
                     note="None of the nine tests could be computed.")
    score = sum(1 for v in tests.values() if v)
    band = ("strong" if score >= 7 and len(tests) >= 8
            else "weak" if score <= 3 else "middling")
    note = f"{score} of {len(tests)} computable tests passed."
    if len(tests) < 9:
        note += (f" {9 - len(tests)} test(s) could not be computed, so this is not "
                 "comparable with a full nine-point score.")
    return Score("piotroski_f", score, band,
                 components={k: bool(v) for k, v in tests.items()},
                 missing=sorted(set(missing)), note=note)


# --------------------------------------------------------------- debt profile

def maturity_wall(debt_due_12m: float | None, cash: float | None,
                  cfo: float | None, undrawn_lines: float | None = None) -> dict:
    """Can the next twelve months of repayments actually be met?

    Refinancing is an assumption, not a fact — and it is the assumption that
    fails precisely when credit markets tighten.
    """
    if debt_due_12m is None:
        return {"known": False,
                "note": "Debt maturing within a year is disclosed in the notes to "
                        "accounts but is not in most free feeds. It is the single most "
                        "useful credit number there is — read it before a large position."}
    sources = sum(x for x in (cash, cfo, undrawn_lines) if x is not None)
    named = [n for n, v in (("cash", cash), ("operating cash flow", cfo),
                            ("undrawn lines", undrawn_lines)) if v is not None]
    if debt_due_12m <= 0:
        return {"known": True, "coverage": None, "band": "none due",
                "note": "Nothing material matures within a year."}
    coverage = sources / debt_due_12m if debt_due_12m else None
    band = ("comfortable" if coverage >= 2 else "adequate" if coverage >= 1.2
            else "tight" if coverage >= 1 else "shortfall")
    note = (f"₹{debt_due_12m:,.0f} falls due within a year against ₹{sources:,.0f} "
            f"from {', '.join(named)} — {coverage:.2f}× cover.")
    if coverage < 1:
        note += (" On these numbers the company must refinance or sell something. "
                 "Refinancing is available right up until it isn't.")
    return {"known": True, "debt_due_12m": debt_due_12m, "sources": sources,
            "coverage": round(coverage, 2), "band": band, "note": note}


def covenant_headroom(net_debt: float | None, ebitda: float | None,
                      interest: float | None,
                      covenants: dict | None = None) -> dict:
    """How far EBITDA can fall before a typical covenant breaks.

    A breach is not merely embarrassing: it usually makes the debt immediately
    repayable, which turns a bad year into a crisis.
    """
    cov = {**TYPICAL_COVENANTS, **(covenants or {})}
    out = {"assumed_covenants": cov, "measures": {}, "note": None}
    if ebitda is None or ebitda <= 0:
        out["note"] = ("EBITDA is unavailable or negative, so covenant headroom cannot "
                       "be measured. Negative EBITDA against any debt is itself the "
                       "finding.")
        return out
    if net_debt is not None:
        leverage = net_debt / ebitda
        limit = cov["net_debt_to_ebitda_max"]
        # EBITDA can fall until net_debt/EBITDA hits the limit
        fall_allowed = 1 - (net_debt / limit) / ebitda if limit else None
        out["measures"]["net_debt_to_ebitda"] = {
            "value": round(leverage, 2), "limit": limit,
            "breached": leverage > limit,
            "ebitda_fall_before_breach": (round(max(fall_allowed, 0), 3)
                                          if fall_allowed is not None else None),
        }
    if interest and interest > 0:
        cover = ebitda / interest
        limit = cov["interest_cover_min"]
        fall_allowed = 1 - (limit * interest) / ebitda
        out["measures"]["interest_cover"] = {
            "value": round(cover, 2), "limit": limit, "breached": cover < limit,
            "ebitda_fall_before_breach": round(max(fall_allowed, 0), 3),
        }
    falls = [m["ebitda_fall_before_breach"] for m in out["measures"].values()
             if m.get("ebitda_fall_before_breach") is not None]
    if falls:
        tightest = min(falls)
        out["tightest_headroom"] = tightest
        out["note"] = (f"EBITDA can fall about {tightest:.0%} before the tightest "
                       "typical covenant is breached."
                       + (" That is thin: an ordinary bad year becomes a solvency event."
                          if tightest < 0.20 else ""))
    if any(m.get("breached") for m in out["measures"].values()):
        out["note"] = ("A typical covenant is already breached on these numbers. "
                       "Check the actual loan terms — lenders may have waived it, but "
                       "waivers come with a price.") + (" " + (out["note"] or ""))
    return out


# --------------------------------------------------------------- financials

def financial_sector_lens(f: dict) -> dict:
    """For a lender the loan book IS the risk, so a different set of numbers."""
    out = {"applicable_metrics": {}, "flags": [], "missing": [], "note": None}
    checks = [
        ("capital_adequacy_ratio", 0.11, "above", "capital adequacy",
         "Below the regulatory minimum the bank must raise capital, usually by "
         "diluting you at a bad price."),
        ("gross_npa_ratio", 0.05, "below", "gross bad loans",
         "Rising gross NPAs lead reported profit by several quarters."),
        ("net_npa_ratio", 0.02, "below", "net bad loans",
         "Net NPAs are what is left after provisions — the loss not yet taken."),
        ("provision_coverage_ratio", 0.70, "above", "provision coverage",
         "Low coverage means future profits are already committed to past mistakes."),
    ]
    for key, threshold, direction, label, why in checks:
        v = f.get(key)
        if v is None:
            out["missing"].append(label)
            continue
        ok = v >= threshold if direction == "above" else v <= threshold
        out["applicable_metrics"][key] = {"value": v, "threshold": threshold, "ok": ok}
        if not ok:
            out["flags"].append(f"{key}_weak")
            out["applicable_metrics"][key]["why"] = why
    if out["missing"]:
        out["note"] = ("Bank metrics not available from the free feeds: "
                       + ", ".join(out["missing"]) +
                       ". These are in the quarterly results; a lender cannot be "
                       "judged without them.")
    return out


# --------------------------------------------------------------- synthesis

def assess(symbol: str, current: dict, previous: dict | None = None,
           sector: str | None = None, manufacturer: bool = True) -> CreditRead:
    """Run every applicable screen and produce one credit read."""
    read = CreditRead(symbol=symbol,
                      sector_kind="financial" if _is_financial(sector) else "corporate")

    if read.sector_kind == "financial":
        lens = financial_sector_lens(current)
        read.flags.extend(lens["flags"])
        read.findings.append(
            "This is a lender, so corporate solvency screens do not apply — leverage "
            "is the business model. Judged instead on capital adequacy, asset quality "
            "and provision coverage.")
        if lens["note"]:
            read.findings.append(lens["note"])
            read.unknowns.extend(lens["missing"])
        for key, m in lens["applicable_metrics"].items():
            if not m["ok"]:
                read.findings.append(f"{key.replace('_', ' ')} at {m['value']:.2%} — "
                                     + m.get("why", ""))
        read.verdict = ("weak on the lender metrics available" if lens["flags"]
                        else "no weakness in the lender metrics available"
                        if lens["applicable_metrics"] else None)
        read.scores.append(altman_z(current, manufacturer, sector))  # records inapplicability
        return read

    z = altman_z(current, manufacturer, sector)
    read.scores.append(z)
    if z.value is not None and z.band == "distress":
        read.flags.append("altman_distress")
        read.findings.append(
            f"Altman-Z of {z.value} places this in the distress zone. The model is a "
            "screen, not a prophecy, but companies that sit here for several years "
            "rarely reward equity holders.")
    elif z.missing:
        read.unknowns.append("altman_z inputs")

    if previous:
        m = beneish_m(current, previous)
        read.scores.append(m)
        if m.value is not None and m.band == "flagged":
            read.flags.append("beneish_flagged")
            read.findings.append(
                f"Beneish M-score of {m.value} is above the -1.78 threshold. Read the "
                "receivables and the gap between profit and operating cash flow before "
                "anything else.")
        f_score = piotroski_f(current, previous)
        read.scores.append(f_score)
        if f_score.value is not None:
            if f_score.band == "weak":
                read.flags.append("piotroski_weak")
                read.findings.append(
                    f"Piotroski score of {f_score.value} — the fundamentals are "
                    "deteriorating, not mending. Cheapness here is a symptom.")
            elif f_score.band == "strong":
                read.findings.append(
                    f"Piotroski score of {f_score.value} — profitability, balance sheet "
                    "and efficiency are all improving together, which is rare and "
                    "usually persists.")
    else:
        read.unknowns.append("prior-year statements (needed for Beneish and Piotroski)")

    read.maturity_wall = maturity_wall(current.get("debt_due_12m"), current.get("cash"),
                                       current.get("cfo"), current.get("undrawn_lines"))
    if read.maturity_wall.get("known") and read.maturity_wall.get("coverage") is not None:
        if read.maturity_wall["coverage"] < 1:
            read.flags.append("maturity_wall_shortfall")
        read.findings.append(read.maturity_wall["note"])
    elif not read.maturity_wall.get("known"):
        read.unknowns.append("debt maturing within a year")

    read.covenant_headroom = covenant_headroom(
        current.get("net_debt"), current.get("ebitda"), current.get("interest"))
    if read.covenant_headroom.get("note"):
        read.findings.append(read.covenant_headroom["note"])
    tight = read.covenant_headroom.get("tightest_headroom")
    if tight is not None and tight < 0.20:
        read.flags.append("covenant_headroom_thin")

    severe = {"altman_distress", "maturity_wall_shortfall", "beneish_flagged"}
    if severe & set(read.flags):
        read.verdict = "serious credit risk — this is how capital is lost permanently"
    elif read.flags:
        read.verdict = "credit weaknesses worth pricing in"
    elif read.scores and any(s.value is not None for s in read.scores):
        read.verdict = "no credit weakness in the numbers available"
    if not read.findings:
        read.findings.append("Nothing in the available numbers suggests balance-sheet "
                             "stress.")
    return read
