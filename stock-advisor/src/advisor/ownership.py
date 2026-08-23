"""Ownership and flow intelligence — who is actually buying and selling.

Institutional desks watch this before they watch the chart, because a
shareholding pattern is a record of what informed money DID, not what anyone
said. In India it is unusually informative: promoter stakes, pledges, FII and
DII positions are all disclosed quarterly, and promoters selling their own
company is one of the few signals that reliably precedes trouble.

The central question this module answers is not "is the stock owned" but
**who is selling to whom**. Institutions handing stock to retail is
distribution; the reverse is accumulation. Everything else here supports that.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

# A stake change is only meaningful above the noise of index rebalancing.
MATERIAL_PP = 1.0          # percentage points over the window
STRONG_PP = 3.0
WINDOW = 4                 # quarters


@dataclass
class Holder:
    name: str
    latest: float | None
    change_pp: float | None       # percentage-point change over the window
    direction: str                # rising | falling | stable | unknown


@dataclass
class OwnershipRead:
    symbol: str
    holders: list[Holder] = field(default_factory=list)
    flow: str = "unknown"                 # accumulation | distribution | mixed | stable
    smart_money_score: int | None = None  # 0-100
    flags: list[str] = field(default_factory=list)
    findings: list[str] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)
    quarters: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["holders"] = [asdict(h) if not isinstance(h, dict) else h for h in self.holders]
        return d


def _clean(series: list) -> list[float]:
    return [v for v in (series or []) if v is not None and isinstance(v, (int, float))]


def _trend(series: list, window: int = WINDOW) -> tuple[float | None, float | None, str]:
    """(latest, change in percentage points over the window, direction)."""
    vals = _clean(series)
    if not vals:
        return None, None, "unknown"
    latest = vals[-1]
    if len(vals) < 2:
        return latest, None, "unknown"
    ref = vals[max(0, len(vals) - 1 - window)]
    change = latest - ref
    direction = ("rising" if change >= MATERIAL_PP
                 else "falling" if change <= -MATERIAL_PP else "stable")
    return latest, round(change, 2), direction


def analyse(symbol: str, shareholding: dict | None,
            quarters: list[str] | None = None) -> OwnershipRead:
    """`shareholding` maps holder label -> quarterly percentage series."""
    read = OwnershipRead(symbol=symbol, quarters=quarters or [])
    if not shareholding:
        read.unknowns.append("shareholding pattern")
        read.findings.append("No shareholding data available, so nothing can be said "
                             "about who owns this or who is selling.")
        return read

    def pick(*names):
        for key in shareholding:
            low = key.lower()
            if any(n in low for n in names):
                return shareholding[key]
        return None

    series = {
        "Promoters": pick("promoter"),
        "FIIs": pick("fii", "foreign"),
        "DIIs": pick("dii", "domestic"),
        "Government": pick("government"),
        "Public": pick("public", "retail"),
    }

    for name, ser in series.items():
        latest, change, direction = _trend(ser)
        if latest is None and name in ("Government",):
            continue                       # absent for most companies; not a gap
        if latest is None:
            read.unknowns.append(name)
            continue
        read.holders.append(Holder(name, latest, change, direction))

    by_name = {h.name: h for h in read.holders}
    prom, fii, dii, pub = (by_name.get("Promoters"), by_name.get("FIIs"),
                           by_name.get("DIIs"), by_name.get("Public"))

    # --- promoter behaviour: the highest-signal series in Indian markets ---
    if prom:
        if prom.direction == "falling":
            severity = "high" if (prom.change_pp or 0) <= -STRONG_PP else "medium"
            read.flags.append(f"promoter_selling:{severity}")
            read.findings.append(
                f"Promoters have cut their stake by {abs(prom.change_pp):.1f} points to "
                f"{prom.latest:.1f}%. The people who know the business best owning less "
                "of it deserves an explanation before you own more.")
        elif prom.direction == "rising":
            read.findings.append(
                f"Promoters have added {prom.change_pp:.1f} points, now {prom.latest:.1f}%. "
                "Buying your own company with your own money is the most honest signal "
                "an insider can send.")
        if prom.latest is not None and prom.latest < 26:
            read.flags.append("low_promoter_holding")
            read.findings.append(
                f"Promoter holding of {prom.latest:.1f}% is below the level at which "
                "control is comfortable; special resolutions can be blocked.")

    # --- institutional behaviour ---
    inst_change = sum((h.change_pp or 0) for h in (fii, dii) if h)
    # Report institutions only when they actually moved. Narrating a non-event
    # ("holding is stable, +0.0 points") is noise that hides the real signals.
    if fii and fii.direction in ("rising", "falling"):
        read.findings.append(
            f"Foreign institutions are {fii.direction} — {fii.change_pp:+.1f} points "
            f"over the window, now {fii.latest:.1f}%.")
    if dii and dii.direction in ("rising", "falling"):
        read.findings.append(
            f"Domestic institutions are {dii.direction} — {dii.change_pp:+.1f} points, "
            f"now {dii.latest:.1f}%.")
    if fii and dii and fii.direction == "falling" and dii.direction == "rising":
        read.findings.append(
            "Foreign money is leaving while domestic institutions absorb it — the "
            "characteristic pattern of Indian markets since 2020. It supports the "
            "price, but it is a transfer of opinion, not an endorsement.")

    # --- the real question: who is selling to whom ---
    if pub and (fii or dii):
        if inst_change <= -MATERIAL_PP and (pub.change_pp or 0) >= MATERIAL_PP:
            read.flow = "distribution"
            read.flags.append("distribution_to_retail")
            read.findings.append(
                "Institutions are reducing while public shareholding rises. Stock is "
                "moving from informed hands to uninformed ones — historically a poor "
                "sign, whatever the chart says.")
        elif inst_change >= MATERIAL_PP and (pub.change_pp or 0) <= -MATERIAL_PP:
            read.flow = "accumulation"
            read.findings.append(
                "Institutions are accumulating from public shareholders — informed "
                "money taking the other side of retail selling.")
        elif abs(inst_change) < MATERIAL_PP:
            read.flow = "stable"
        else:
            read.flow = "mixed"

    # --- composite: 0-100, where 50 is neutral ---
    score = 50.0
    if prom and prom.change_pp is not None:
        score += max(-25, min(20, prom.change_pp * 6))
    if fii and fii.change_pp is not None:
        score += max(-12, min(12, fii.change_pp * 4))
    if dii and dii.change_pp is not None:
        score += max(-8, min(8, dii.change_pp * 3))
    if read.flow == "distribution":
        score -= 12
    elif read.flow == "accumulation":
        score += 10
    if "low_promoter_holding" in read.flags:
        score -= 5
    read.smart_money_score = int(max(0, min(100, round(score))))

    if not read.findings:
        read.findings.append("Ownership has been broadly unchanged — no one with "
                             "an information advantage is doing anything unusual.")
    return read


def pledge_read(pledged_percent: float | None,
                previous_percent: float | None = None) -> dict:
    """Promoter pledging: the fastest-moving governance red flag in Indian markets."""
    if pledged_percent is None:
        return {"known": False,
                "note": "Pledge data is disclosed to the exchanges but is not in most "
                        "free feeds. Check the company's shareholding disclosure before "
                        "any long-term position."}
    out = {"known": True, "pledged_percent": pledged_percent, "flags": []}
    if pledged_percent > 50:
        out["flags"].append("pledge_extreme")
        out["note"] = (f"{pledged_percent:.0f}% of the promoter stake is pledged. A fall "
                       "in the price can force lenders to sell, which pushes the price "
                       "down further — the mechanism behind most Indian small-cap "
                       "collapses.")
    elif pledged_percent > 20:
        out["flags"].append("pledge_high")
        out["note"] = (f"{pledged_percent:.0f}% pledged. Watch it quarterly; a rising "
                       "pledge alongside a falling price is the dangerous combination.")
    elif pledged_percent > 0:
        out["note"] = f"{pledged_percent:.0f}% pledged — modest, but worth tracking."
    else:
        out["note"] = "No promoter shares pledged."
    if previous_percent is not None and pledged_percent - previous_percent >= 5:
        out["flags"].append("pledge_rising")
        out["note"] += (f" It has risen {pledged_percent - previous_percent:.0f} points "
                        "since the last disclosure, which matters more than the level.")
    return out


def digest_deals(deals: list[dict], days: int = 30) -> dict:
    """Bulk and block deals: large trades the exchange forces into daylight.

    Each deal: {date, client, type: BUY|SELL, quantity, price}.
    """
    if not deals:
        return {"count": 0, "note": "No large disclosed trades in the window."}
    buys = [d for d in deals if str(d.get("type", "")).upper().startswith("B")]
    sells = [d for d in deals if str(d.get("type", "")).upper().startswith("S")]
    qty = lambda ds: sum(float(d.get("quantity") or 0) for d in ds)  # noqa: E731
    net = qty(buys) - qty(sells)
    repeat = {}
    for d in deals:
        client = str(d.get("client", "")).strip()
        if client:
            repeat[client] = repeat.get(client, 0) + 1
    persistent = sorted([c for c, n in repeat.items() if n >= 2])
    return {
        "count": len(deals), "buy_count": len(buys), "sell_count": len(sells),
        "net_quantity": net,
        "direction": "net buying" if net > 0 else "net selling" if net < 0 else "balanced",
        "repeat_participants": persistent,
        "note": (f"{len(deals)} large disclosed trades in {days} days, "
                 f"{'net buying' if net > 0 else 'net selling' if net < 0 else 'balanced'}."
                 + (f" Repeat participants: {', '.join(persistent[:3])} — a single buyer "
                    "returning is more informative than one large print."
                    if persistent else "")),
    }
