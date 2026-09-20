"""The feedback loop: parameters measured from the system's own record.

Until now the most consequential numbers in this system were assumptions with
plausible-sounding values. The information coefficient defaulted to 0.05 —
reasonable for good stock selection, and entirely unverified for *this* system.
The average correlation between the investor lenses defaulted to 0.35, and that
single guess decided whether a 50% annual target was reachable or not.

Both are recoverable from the journal, which has been recording every decision
before its outcome was known since long before anything read it back.

The rule this module exists to enforce: **every parameter declares whether it
was measured or assumed.** An assumed value is not wrong to use — there is no
alternative on day one — but presenting it as though it were measured is how a
system stops being able to tell the difference between working and not working.
So each figure travels with its provenance, its sample size, and whether it can
be distinguished from luck.

The pure functions here take records and return numbers; only `live_parameters`
touches the database. That separation is deliberate — the arithmetic is the part
worth testing, and it should be testable without a populated store.
"""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass

from .calibrate import detect_decay, measure_correlation, measure_skill

# Defaults used only until there is evidence. Each is a plausible published
# figure, and each is labelled as an assumption wherever it surfaces.
ASSUMED_IC = 0.05
ASSUMED_LENS_CORRELATION = 0.35
ASSUMED_TRANSFER = 0.5
MIN_CALLS_FOR_SKILL = 30


@dataclass
class Parameter:
    """A number the system uses, with the honesty about where it came from."""
    name: str
    value: float
    source: str              # "measured" | "assumed"
    n: int = 0
    trustworthy: bool = False
    note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# --------------------------------------------------------------------------
# pure computation over journal records
# --------------------------------------------------------------------------
def forward_return(record: dict) -> float | None:
    """Realised return on a closed call, from the prices actually recorded.

    Computed from entry and exit rather than taken from the R multiple, because
    an R multiple is a risk-adjusted count and correlating a score against it
    would measure something subtly different from what the sizing maths needs.
    """
    entry_low = record.get("entry_low")
    entry_high = record.get("entry_high")
    exit_price = record.get("exit_price")
    if entry_low is None or exit_price is None:
        return None
    entry = (entry_low + (entry_high if entry_high is not None else entry_low)) / 2
    if entry <= 0:
        return None
    r = exit_price / entry - 1
    # A "sell" or "avoid" call that was right shows as a fall, so its
    # forecast-versus-outcome sign has to be flipped before correlating.
    if record.get("action") in ("sell", "trim", "avoid"):
        r = -r
    return r


def skill_from_records(records: list[dict]) -> Parameter:
    """Information coefficient from closed calls: conviction against outcome."""
    rows = []
    for r in records:
        fr = forward_return(r)
        conv = r.get("conviction")
        if fr is not None and conv is not None:
            rows.append({"score": conv / 100.0, "forward_return": fr})

    m = measure_skill(rows)
    if not m.get("ok"):
        return Parameter(
            "information_coefficient", ASSUMED_IC, "assumed", n=len(rows),
            trustworthy=False,
            note=(f"{m.get('why', 'not enough evidence')} — using a published "
                  f"figure for good stock selection until the record can speak"))
    return Parameter(
        "information_coefficient", m["ic"], "measured", n=m["n"],
        trustworthy=bool(m["significant"]), note=m["reading"])


def lens_correlation_from_records(records: list[dict]) -> Parameter:
    """How much the investor lenses actually overlap, from their own scores.

    Reads the per-lens scores stored on each decision at the moment it was made.
    A lens that has not scored at least a dozen companies is left out rather
    than correlated on a handful of points.
    """
    history: dict[str, list[float]] = {}
    for r in records:
        raw = r.get("engine_json") or "{}"
        try:
            engines = json.loads(raw) if isinstance(raw, str) else dict(raw)
        except (ValueError, TypeError):
            continue
        for lens, score in (engines.get("lenses") or {}).items():
            if isinstance(score, (int, float)):
                history.setdefault(lens, []).append(float(score))

    m = measure_correlation(history)
    if not m.get("ok"):
        return Parameter(
            "lens_correlation", ASSUMED_LENS_CORRELATION, "assumed",
            n=len(history), trustworthy=False,
            note=(f"{m.get('why', 'no lens history')} — the ceiling this implies "
                  f"is therefore a guess, and it is the number that decides "
                  f"whether a return target is reachable"))
    return Parameter(
        "lens_correlation", m["average_correlation"], "measured",
        n=len(history), trustworthy=True,
        note=(f"{m['reading']}; most redundant pair: {m['most_redundant']}, "
              f"most diversifying: {m['most_diversifying']}"))


def rolling_ic(records: list[dict], buckets: int = 8) -> list[float]:
    """Information coefficient period by period, oldest first.

    Splitting the record into equal buckets by date is crude but it is what
    decay detection needs, and a more elaborate scheme would imply a precision
    the sample size does not support.
    """
    rows = []
    for r in records:
        fr = forward_return(r)
        conv = r.get("conviction")
        if fr is not None and conv is not None:
            rows.append((r.get("created_at") or "", conv / 100.0, fr))
    rows.sort(key=lambda x: x[0])
    if len(rows) < buckets * 8:          # need enough per bucket to mean anything
        return []

    size = len(rows) // buckets
    out = []
    for i in range(buckets):
        chunk = rows[i * size:(i + 1) * size] if i < buckets - 1 else rows[i * size:]
        m = measure_skill([{"score": s, "forward_return": f} for _, s, f in chunk])
        out.append(m["ic"] if m.get("ok") else 0.0)
    return out


# --------------------------------------------------------------------------
# what the rest of the system should actually use
# --------------------------------------------------------------------------
def live_parameters(records: list[dict] | None = None) -> dict:
    """The parameters the sizing and target maths should run on today.

    One place, so a caller cannot quietly pick up a default that nobody checked.
    Everything carries its provenance, and the summary says plainly how much of
    the model is currently resting on assumption.
    """
    if records is None:
        records = read_journal()

    ic = skill_from_records(records)
    corr = lens_correlation_from_records(records)
    transfer = Parameter(
        "transfer_coefficient", ASSUMED_TRANSFER, "assumed",
        trustworthy=False,
        note=("how much of the signal survives position limits, lot sizes and "
              "liquidity — measurable only once live fills can be compared with "
              "intended weights"))

    params = [ic, corr, transfer]
    measured = [p for p in params if p.source == "measured"]
    trusted = [p for p in params if p.trustworthy]

    decay = None
    series = rolling_ic(records)
    if series:
        decay = detect_decay(series)

    return {
        "parameters": {p.name: p.to_dict() for p in params},
        "measured_count": len(measured),
        "total_count": len(params),
        "decay": decay,
        "closed_calls": sum(1 for r in records if forward_return(r) is not None),
        "summary": (
            f"{len(measured)} of {len(params)} parameters measured, "
            f"{len(trusted)} of them distinguishable from luck"
            + ("" if measured else
               " — every figure below is a published default, not this system's "
               "own record")),
        "warning": (
            "Position sizing currently rests on an assumed skill level. Treat "
            "recommended sizes as provisional until the journal has at least "
            f"{MIN_CALLS_FOR_SKILL} closed calls."
            if not ic.trustworthy else None),
    }


def read_journal() -> list[dict]:
    """Closed decisions with their outcomes. Empty rather than failing when the
    store is not there — a fresh install has no record, which is a state to
    report, not an error."""
    try:
        from . import db
        with db.connect() as conn:
            rows = conn.execute(
                """
                SELECT d.id, d.created_at, d.symbol, d.book, d.action,
                       d.conviction, d.entry_low, d.entry_high, d.stop,
                       d.engine_json, o.exit_price, o.r_multiple, o.closed_at
                FROM journal_decisions d
                JOIN journal_outcomes o ON o.decision_id = d.id
                """
            ).fetchall()
        cols = ("id", "created_at", "symbol", "book", "action", "conviction",
                "entry_low", "entry_high", "stop", "engine_json", "exit_price",
                "r_multiple", "closed_at")
        return [dict(zip(cols, r)) for r in rows]
    except Exception:
        return []


def requirements_with_measured(target_annual_return: float,
                               records: list[dict] | None = None) -> dict:
    """What a target requires, using measured parameters wherever they exist.

    The same arithmetic as before, but no longer silently fed defaults. Where a
    parameter is still assumed the result says so, because a reachability
    verdict built on two guesses is a guess itself however precise it looks.
    """
    from .ensemble import requirements_for

    live = live_parameters(records)
    p = live["parameters"]
    r = requirements_for(
        target_annual_return,
        ic=p["information_coefficient"]["value"],
        transfer_coefficient=p["transfer_coefficient"]["value"],
        average_correlation=p["lens_correlation"]["value"],
    )
    r["parameter_provenance"] = {
        k: {"value": v["value"], "source": v["source"], "trustworthy": v["trustworthy"]}
        for k, v in p.items()
    }
    r["confidence"] = (
        "resting on measured skill" if p["information_coefficient"]["source"] == "measured"
        else "resting on assumed skill — this verdict is provisional")
    return r
