"""Corridor scoring engine — the Hyderabad-pattern template (knowledge 01).

Score 0-100 = jobs 30 + connectivity 25 + policy 15 + supply 10 + stage 20,
where the analyst-maintained component inputs (0-1) come from the corridors table
and event momentum from the monitor nudges the reading and flags stage shifts.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from . import db

WEIGHTS = {"jobs_anchor": 30, "connectivity_delta": 25,
           "policy_persistence": 15, "supply_constraint": 10}
STAGE_SCORE = {"A": 8, "B": 20, "C": 12, "D": 0}   # B = the sweet spot; D = exit
STAGE_ADVICE = {
    "A": "announcement stage: highest potential, highest policy risk — small size only",
    "B": "construction visible: the core allocation stage (risk collapsed, price hasn't)",
    "C": "anchors operational: ordinary returns — quality locations only",
    "D": "mature/speculative: exit stage, not entry",
}


def event_momentum(slug: str) -> float:
    """Events mentioning this corridor: last 90d vs prior 90d (ratio, 1.0=flat)."""
    with db.connect() as conn:
        recent = conn.execute(
            "SELECT COUNT(*) FROM events WHERE corridors LIKE ? "
            "AND fetched_at >= datetime('now', '-90 days')", (f"%{slug}%",)).fetchone()[0]
        prior = conn.execute(
            "SELECT COUNT(*) FROM events WHERE corridors LIKE ? "
            "AND fetched_at < datetime('now', '-90 days') "
            "AND fetched_at >= datetime('now', '-180 days')", (f"%{slug}%",)).fetchone()[0]
    return round(recent / max(prior, 1), 2)


def score_corridor(slug: str) -> dict | None:
    with db.connect() as conn:
        row = conn.execute(
            "SELECT name, jobs_anchor, connectivity_delta, policy_persistence, "
            "supply_constraint, stage FROM corridors WHERE slug=?", (slug,)).fetchone()
    if row is None:
        return None
    name, jobs, conn_d, policy, supply, stage = row
    stage = (stage or "A").upper()
    parts = {
        "jobs_anchor": round(jobs * WEIGHTS["jobs_anchor"], 1),
        "connectivity_delta": round(conn_d * WEIGHTS["connectivity_delta"], 1),
        "policy_persistence": round(policy * WEIGHTS["policy_persistence"], 1),
        "supply_constraint": round(supply * WEIGHTS["supply_constraint"], 1),
        "stage": STAGE_SCORE.get(stage, 0),
    }
    momentum = event_momentum(slug)
    score = round(sum(parts.values()), 1)
    flags = []
    if momentum >= 2.0:
        flags.append("event_momentum_surge (verify: possible stage transition)")
    if stage == "A" and policy < 0.4:
        flags.append("announcement_only_low_persistence: lottery-ticket risk (knowledge 01)")
    if stage == "D":
        flags.append("exit_stage: system will not recommend entry")

    result = {"slug": slug, "name": name, "score": score, "stage": stage,
              "stage_advice": STAGE_ADVICE[stage], "components": parts,
              "event_momentum_90d": momentum, "flags": flags}
    with db.connect() as conn2:
        conn2.execute(
            "INSERT OR REPLACE INTO corridor_scores VALUES (?, ?, ?, ?, ?)",
            (slug, datetime.now(timezone.utc).date().isoformat(), score,
             momentum, json.dumps(parts)))
    return result


def rank_corridors() -> list[dict]:
    with db.connect() as conn:
        slugs = [r[0] for r in conn.execute("SELECT slug FROM corridors").fetchall()]
    scored = [s for s in (score_corridor(sl) for sl in slugs) if s]
    return sorted(scored, key=lambda s: s["score"], reverse=True)


def set_inputs(slug: str, **kwargs) -> None:
    """Update analyst-maintained component inputs (0-1 floats, stage letter)."""
    allowed = {"jobs_anchor", "connectivity_delta", "policy_persistence",
               "supply_constraint", "stage", "notes"}
    sets = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
    if not sets:
        return
    with db.connect() as conn:
        conn.execute(
            f"UPDATE corridors SET {', '.join(f'{k}=?' for k in sets)} WHERE slug=?",
            (*sets.values(), slug))
