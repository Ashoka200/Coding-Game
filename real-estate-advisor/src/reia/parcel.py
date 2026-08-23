"""Parcel evaluator: corridor context + price sanity + legal verdict → one report.

Return math discipline (knowledge 01): every thesis is benchmarked against index
equity after holding costs; the report says so with numbers, not vibes.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from . import db, legal
from .corridor import score_corridor

EQUITY_BENCHMARK_CAGR = 0.12     # Nifty 500 TRI long-run assumption for comparison
HOLDING_COST_PCT_PA = 0.01       # fencing, taxes, caretaking, weeds (both kinds)
EXIT_FRICTION_PCT = 0.06         # brokerage + time-discount on illiquid exit


def evaluate_parcel(label: str, corridor_slug: str | None, asking_price: float,
                    guidance_value: float | None,
                    legal_answers: dict[str, bool | None],
                    extent_acres: float | None = None,
                    survey_no: str | None = None,
                    parcel_type: str = "raw_land",
                    horizon_years: int = 5,
                    expected_multiple: float | None = None) -> dict:
    """Full 360° parcel screen. expected_multiple: user's bull-case price multiple
    over the horizon (e.g. 3.0 = triples); scored against the equity benchmark."""
    legal_result = legal.evaluate(legal_answers, parcel_type)
    corridor = score_corridor(corridor_slug) if corridor_slug else None

    notes: list[str] = []
    if corridor:
        if corridor["stage"] == "D":
            notes.append("corridor at exit stage D — entry not recommended (knowledge 01)")
        if corridor["score"] < 40:
            notes.append(f"corridor score {corridor['score']} is weak — thesis rests "
                         "on hope, not committed anchors")
    if guidance_value:
        premium = asking_price / guidance_value - 1
        notes.append(f"asking is {premium:.0%} over guidance value"
                     + (" — typical" if premium < 3 else " — very rich, negotiate/verify"))

    benchmark = None
    if expected_multiple:
        land_net = (expected_multiple * (1 - EXIT_FRICTION_PCT)
                    * (1 - HOLDING_COST_PCT_PA) ** horizon_years)
        equity_alt = (1 + EQUITY_BENCHMARK_CAGR) ** horizon_years
        benchmark = {
            "land_net_multiple": round(land_net, 2),
            "equity_alt_multiple": round(equity_alt, 2),
            "beats_equity": land_net > equity_alt * 1.25,   # illiquidity margin
        }
        if not benchmark["beats_equity"]:
            notes.append("bull case does not beat index equity by the required "
                         "margin after costs — why take title risk for this?")

    if legal_result["verdict"] == "VETO":
        recommendation = "REJECT — legal veto; the defect can zero the value"
    elif corridor and corridor["stage"] == "D":
        recommendation = "REJECT — corridor mature; entry window closed"
    elif legal_result["verdict"] == "RESOLVE_FIRST":
        recommendation = ("HOLD — resolve legal items via escrow/conditions first; "
                          "money moves only after advocate's opinion")
    elif benchmark and not benchmark["beats_equity"]:
        recommendation = "PASS — clean but return case doesn't justify illiquidity"
    else:
        recommendation = ("PROCEED TO LAWYER — screen clean and thesis viable; "
                          "commission the 30-year title opinion + surveyor")

    report = {
        "label": label, "corridor": corridor, "legal": legal_result,
        "benchmark": benchmark, "notes": notes,
        "recommendation": recommendation,
        "disclaimer": legal.DISCLAIMER,
    }
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO parcels (created_at, label, corridor, survey_no, "
            "extent_acres, asking_price, guidance_value, checklist_json, verdict, report) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (datetime.now(timezone.utc).isoformat(timespec="seconds"), label,
             corridor_slug, survey_no, extent_acres, asking_price, guidance_value,
             json.dumps(legal_answers), legal_result["verdict"],
             json.dumps(report, default=str)))
    return report
