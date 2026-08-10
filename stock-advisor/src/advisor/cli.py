"""Command-line entry point.

Usage (from stock-advisor/):
    python -m advisor.cli init-db
    python -m advisor.cli update-universe
    python -m advisor.cli update-prices [--backfill] [--symbols RELIANCE,TCS]
    python -m advisor.cli ingest-bhavcopy [--date YYYY-MM-DD]
    python -m advisor.cli status
"""
from __future__ import annotations

import argparse
from datetime import date

from . import db


def main() -> None:
    p = argparse.ArgumentParser(prog="advisor")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init-db")
    sub.add_parser("update-universe")

    up = sub.add_parser("update-prices")
    up.add_argument("--backfill", action="store_true")
    up.add_argument("--symbols", help="comma-separated NSE symbols; default: universe")

    bh = sub.add_parser("ingest-bhavcopy")
    bh.add_argument("--date", help="YYYY-MM-DD, default today")

    sub.add_parser("status")

    args = p.parse_args()

    if args.cmd == "init-db":
        db.init_db()
        print(f"initialized {db.config.DB_PATH}")
    elif args.cmd == "update-universe":
        from .universe import update_universe
        n, dropped = update_universe()
        print(f"universe: {n} constituents, {dropped} marked inactive")
    elif args.cmd == "update-prices":
        from .ingest.prices import update_prices
        symbols = args.symbols.split(",") if args.symbols else None
        rows = update_prices(symbols=symbols, backfill=args.backfill)
        print(f"prices: {rows} rows written")
    elif args.cmd == "ingest-bhavcopy":
        from .ingest.bhavcopy import ingest_bhavcopy
        d = date.fromisoformat(args.date) if args.date else date.today()
        rows = ingest_bhavcopy(d)
        print(f"bhavcopy {d}: {rows} rows" + (" (holiday/absent)" if rows == 0 else ""))
    elif args.cmd == "status":
        with db.connect() as conn:
            for label, q in [
                ("stocks (active)", "SELECT COUNT(*) FROM stocks WHERE active=1"),
                ("stocks (total)", "SELECT COUNT(*) FROM stocks"),
                ("price rows", "SELECT COUNT(*) FROM prices_eod"),
                ("price date range", "SELECT MIN(date) || ' .. ' || MAX(date) FROM prices_eod"),
                ("open journal decisions", "SELECT COUNT(*) FROM journal_decisions WHERE status='open'"),
                ("last refresh", "SELECT job || ' @ ' || run_at FROM refresh_log ORDER BY run_at DESC LIMIT 1"),
            ]:
                val = conn.execute(q).fetchone()[0]
                print(f"{label}: {val}")


if __name__ == "__main__":
    main()
