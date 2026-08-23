"""CLI. From real-estate-advisor/src:

    python -m reia.cli init-db
    python -m reia.cli sweep                      # fetch + classify all sources
    python -m reia.cli events [--days 30] [--corridor slug]
    python -m reia.cli corridors                  # ranked scores
    python -m reia.cli set-corridor SLUG --jobs 0.6 --conn 0.7 --policy 0.5 --supply 0.3 --stage B
    python -m reia.cli checklist                  # print the legal checklist (blank form)
    python -m reia.cli evaluate --file parcel.json  # evaluate a parcel (see checklist)
    python -m reia.cli enrich                     # AI-enrich events (ANTHROPIC_API_KEY)
    python -m reia.cli digest
"""
from __future__ import annotations

import argparse
import json

from . import db


def main() -> None:
    p = argparse.ArgumentParser(prog="reia")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init-db")
    sub.add_parser("sweep")

    ev = sub.add_parser("events")
    ev.add_argument("--days", type=int, default=30)
    ev.add_argument("--corridor")

    sub.add_parser("corridors")

    sc = sub.add_parser("set-corridor")
    sc.add_argument("slug")
    sc.add_argument("--jobs", type=float); sc.add_argument("--conn", type=float)
    sc.add_argument("--policy", type=float); sc.add_argument("--supply", type=float)
    sc.add_argument("--stage"); sc.add_argument("--notes")

    sub.add_parser("checklist")

    evp = sub.add_parser("evaluate")
    evp.add_argument("--file", required=True,
                     help="JSON: {label, corridor, asking_price, guidance_value, "
                          "extent_acres, survey_no, parcel_type, horizon_years, "
                          "expected_multiple, answers: {item_id: true/false/null}}")

    en = sub.add_parser("enrich")
    en.add_argument("--limit", type=int, default=20)

    sub.add_parser("digest")

    args = p.parse_args()

    if args.cmd == "init-db":
        db.init_db(); print(f"initialized {db.config.DB_PATH}")
    elif args.cmd == "sweep":
        from .monitor import sweep
        for src, res in sweep().items():
            print(f"{src}: {res}")
    elif args.cmd == "events":
        from .monitor import recent_events
        for e in recent_events(args.days, args.corridor):
            print(f"[{e['categories']}] {e['title']}"
                  + (f"  → {e['corridors']}" if e["corridors"] else ""))
    elif args.cmd == "corridors":
        from .corridor import rank_corridors
        for c in rank_corridors():
            print(f"{c['score']:5.1f}  {c['slug']:20s} stage {c['stage']} "
                  f"mom ×{c['event_momentum_90d']}  {'; '.join(c['flags'])}")
    elif args.cmd == "set-corridor":
        from .corridor import set_inputs
        set_inputs(args.slug, jobs_anchor=args.jobs, connectivity_delta=args.conn,
                   policy_persistence=args.policy, supply_constraint=args.supply,
                   stage=args.stage, notes=args.notes)
        print("updated")
    elif args.cmd == "checklist":
        from .legal import CHECKLIST, blank_answers
        print(json.dumps({"answers": blank_answers()}, indent=2))
        print("\n# Questions:")
        for i in CHECKLIST:
            print(f"- [{i['sev'].upper():7s}] {i['id']}: {i['q']}")
    elif args.cmd == "evaluate":
        from .parcel import evaluate_parcel
        spec = json.loads(open(args.file).read())
        report = evaluate_parcel(
            label=spec["label"], corridor_slug=spec.get("corridor"),
            asking_price=spec["asking_price"],
            guidance_value=spec.get("guidance_value"),
            legal_answers=spec.get("answers", {}),
            extent_acres=spec.get("extent_acres"), survey_no=spec.get("survey_no"),
            parcel_type=spec.get("parcel_type", "raw_land"),
            horizon_years=spec.get("horizon_years", 5),
            expected_multiple=spec.get("expected_multiple"))
        print(json.dumps(report, indent=2, default=str))
    elif args.cmd == "enrich":
        from .ai import enrich_recent_events
        print(f"enriched {enrich_recent_events(args.limit)} events")
    elif args.cmd == "digest":
        from .digest import build_digest
        print(build_digest())


if __name__ == "__main__":
    main()
