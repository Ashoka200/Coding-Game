"""The never-guess response envelope.

Every tool result is wrapped by `ok()` or `unavailable()`. The shape is the
enforcement mechanism: a figure the sources did not supply lands in `unknown`
with a reason, and the rules that forbid inventing it travel in-band with the
data so a model that never read the README still receives the constraint.
"""
from __future__ import annotations

from datetime import datetime, timezone

RULES = [
    "Every figure you report must come from `data` in this response. "
    "Do not use remembered or trained-in prices, ratios or dates.",
    "Do not estimate, interpolate or infer any field listed in `unknown`. "
    "Say it is unavailable and why.",
    "Do not compute derived figures the engines did not return; ask for the "
    "tool that computes them instead.",
    "Cite the source and as-of date from `provenance` when stating a figure.",
    "Data is end-of-day unless a caveat says otherwise. Never present it as live.",
    "This is decision support, not investment advice, and never an instruction to trade.",
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def ok(data: dict, provenance: list[dict] | None = None,
       unknown: list[dict] | None = None, caveats: list[str] | None = None) -> dict:
    return {
        "ok": True,
        "data": data,
        "provenance": provenance or [],
        "unknown": unknown or [],
        "caveats": caveats or [],
        "rules": RULES,
        "generated_at": _now(),
    }


def unavailable(what: str, reason: str, caveats: list[str] | None = None) -> dict:
    """A clean 'we do not know' — never a fallback guess."""
    return {
        "ok": False,
        "data": None,
        "provenance": [],
        "unknown": [{"field": what, "reason": reason}],
        "caveats": caveats or [],
        "rules": RULES + [
            f"{what} is unavailable. Do not substitute a figure from memory or "
            "from another company. Tell the user it could not be retrieved."],
        "generated_at": _now(),
    }


def missing_fields(record: dict, wanted: dict[str, str]) -> list[dict]:
    """Turn absent keys into explicit unknowns. `wanted` maps field -> why it matters."""
    out = []
    for field, why in wanted.items():
        if record.get(field) is None:
            out.append({"field": field,
                        "reason": f"not supplied by the source; {why}"})
    return out
