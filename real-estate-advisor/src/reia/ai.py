"""AI layer: event enrichment + parcel narrative reports (knowledge docs as doctrine)."""
from __future__ import annotations

import json
import os
from pathlib import Path

KNOWLEDGE_DIR = Path(__file__).resolve().parents[2] / "knowledge"
DEFAULT_MODEL = "claude-sonnet-5"

EVENT_INSTRUCTIONS = """
Classify this government/news item for a land-investment monitor. Return JSON only:
{"material": bool,            // does it plausibly move land values anywhere?
 "severity": 1-5,             // 5 = funded mega-project, 1 = routine mention
 "stage_signal": "announcement|funded|construction|operational|stalled",
 "corridors_hint": [strings], // place names / corridors affected
 "why": one sentence}
Public information only; if the item reads as rumor/unsourced, material=false.
"""

REPORT_INSTRUCTIONS = """
You are the real-estate advisory's senior analyst. The documents above are your
doctrine. Write the parcel/corridor report using ONLY the numbers and verdicts in
the payload — never invent facts, prices, or legal conclusions. Structure: Thesis ·
Corridor context (stage, what must go right) · Legal risk summary (verbatim
verdict; list open lawyer questions) · Return case vs index equity · What would
kill this deal · Recommendation (restate the engine's, with rationale).
End with the payload's disclaimer verbatim.
"""


def _client():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY not set — export it to enable AI features.")
    import anthropic
    return anthropic.Anthropic()


def build_system_prompt() -> str:
    files = sorted(KNOWLEDGE_DIR.glob("*.md"))
    return "\n\n---\n\n".join(f.read_text() for f in files)


def classify_event(title: str, body: str = "", model: str = DEFAULT_MODEL) -> dict:
    msg = _client().messages.create(
        model=model, max_tokens=400,
        system=EVENT_INSTRUCTIONS,
        messages=[{"role": "user", "content": f"{title}\n\n{body}"}])
    return json.loads(msg.content[0].text)


def enrich_recent_events(limit: int = 20, model: str = DEFAULT_MODEL) -> int:
    """AI-enrich stored events lacking ai_json. Returns count enriched."""
    from . import db

    with db.connect() as conn:
        rows = conn.execute(
            "SELECT id, title, body FROM events WHERE ai_json IS NULL "
            "ORDER BY fetched_at DESC LIMIT ?", (limit,)).fetchall()
        n = 0
        for eid, title, body in rows:
            try:
                enriched = classify_event(title, body or "", model)
            except Exception:
                continue
            conn.execute("UPDATE events SET ai_json=? WHERE id=?",
                         (json.dumps(enriched), eid))
            n += 1
    return n


def parcel_report(payload: dict, model: str = DEFAULT_MODEL) -> str:
    msg = _client().messages.create(
        model=model, max_tokens=2000,
        system=build_system_prompt() + "\n\n---\n" + REPORT_INSTRUCTIONS,
        messages=[{"role": "user", "content":
                   "Engine payload:\n```json\n"
                   + json.dumps(payload, indent=2, default=str) + "\n```"}])
    return msg.content[0].text
