"""Weekly digest: corridor ranking + notable events + tracked-parcel status."""
from __future__ import annotations

import json
from datetime import date

from . import db
from .corridor import rank_corridors
from .legal import DISCLAIMER
from .monitor import recent_events


def build_digest() -> str:
    lines = [f"# Real Estate Advisor digest — {date.today().isoformat()}", ""]

    lines.append("## Corridor ranking (Hyderabad-pattern template)")
    for c in rank_corridors():
        flag_txt = f"  ⚠ {'; '.join(c['flags'])}" if c["flags"] else ""
        lines.append(f"- **{c['name']}** {c['score']}/100 · stage {c['stage']} "
                     f"({c['stage_advice']}) · momentum ×{c['event_momentum_90d']}{flag_txt}")
    lines.append("")

    events = recent_events(days=14)
    lines.append("## Notable public signals (14d)")
    if events:
        for e in events[:15]:
            tag = f" → {e['corridors']}" if e["corridors"] else ""
            lines.append(f"- [{e['categories']}] {e['title']}{tag}")
    else:
        lines.append("_no classified events — run a sweep_")
    lines.append("")

    with db.connect() as conn:
        parcels = conn.execute(
            "SELECT label, verdict, report FROM parcels "
            "ORDER BY created_at DESC LIMIT 10").fetchall()
    lines.append("## Tracked parcels")
    if parcels:
        for label, verdict, report in parcels:
            rec = json.loads(report).get("recommendation", "")
            lines.append(f"- **{label}**: {verdict} — {rec}")
    else:
        lines.append("_none evaluated yet_")

    lines += ["", f"_{DISCLAIMER}_"]
    return "\n".join(lines)
