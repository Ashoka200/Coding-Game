"""AI synthesis layer: assembles the knowledge doctrine as system prompt and asks
Claude for the 360° report. The LLM never computes — every number in the payload
comes from the engines; the prompt forbids inventing figures."""
from __future__ import annotations

import json
import os
from pathlib import Path

KNOWLEDGE_DIR = Path(__file__).resolve().parents[2] / "knowledge"
DEFAULT_MODEL = "claude-sonnet-5"

REPORT_INSTRUCTIONS = """
You are the 360° Stock Investor Advisory's senior analyst. The documents above are
your operating doctrine — analyze exactly this way. Rules:
1. Use ONLY the numbers provided in the engine payload. Never invent or estimate a
   figure that is not present; where data is missing, name the gap explicitly.
2. Structure: Thesis (one paragraph) · Bull case · Bear case (equally persuasive,
   module 08) · What invalidates the thesis (specific levels/events) · The plan
   (entry zone, stop, targets, size — restate the payload's numbers with rationale)
   · Data gaps & caveats.
3. Speak as the desk's risk manager once before concluding (module 08).
4. End with: "Decision-support only, not investment advice."
"""


def build_system_prompt(modules: list[str] | None = None) -> str:
    """Concatenate knowledge modules (default: all, in numeric order)."""
    files = sorted(KNOWLEDGE_DIR.glob("[0-9]*.md"))
    if modules:
        files = [f for f in files if any(f.name.startswith(m) for m in modules)]
    doctrine = "\n\n---\n\n".join(f.read_text() for f in files)
    return doctrine + "\n\n---\n" + REPORT_INSTRUCTIONS


def build_payload(symbol: str) -> dict:
    """Assemble everything the engines know about one symbol."""
    from . import db, technical
    from .fundamentals import fundamental_score, latest_fundamentals
    from .regime import compute_regime, last_state
    from .screener import _load_symbol_df

    with db.connect() as conn:
        df = _load_symbol_df(conn, symbol)
    f = technical.compute_features(df)
    fund = latest_fundamentals(symbol)
    fscore, flags = fundamental_score(fund)
    reading = compute_regime(prev_state=last_state())
    return {
        "symbol": symbol,
        "technical_features": f,
        "technical_score": technical.technical_score(f) if f else None,
        "stage": technical.stage(f) if f else None,
        "setups": technical.detect_setups(f, fscore) if f else [],
        "fundamentals": fund,
        "fundamental_score": fscore,
        "flags": flags,
        "market_regime": reading.__dict__ if reading else None,
    }


def generate_report(symbol: str, payload: dict | None = None,
                    model: str = DEFAULT_MODEL, max_tokens: int = 2000) -> str:
    """Call Claude. Requires ANTHROPIC_API_KEY; raises with guidance otherwise."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError(
            "ANTHROPIC_API_KEY not set. Get a key at console.anthropic.com and "
            "export ANTHROPIC_API_KEY=... ; then re-run.")
    import anthropic

    payload = payload or build_payload(symbol)
    client = anthropic.Anthropic()
    msg = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=build_system_prompt(),
        messages=[{"role": "user", "content":
                   f"Engine payload for {symbol}:\n```json\n"
                   f"{json.dumps(payload, indent=2, default=str)}\n```\n"
                   "Write the 360° report."}],
    )
    return msg.content[0].text
