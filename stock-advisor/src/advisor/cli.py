"""Command-line entry point.

Usage (from stock-advisor/src):
    python -m advisor.cli init-db
    python -m advisor.cli update-universe
    python -m advisor.cli update-prices [--backfill] [--symbols RELIANCE,TCS]
    python -m advisor.cli ingest-bhavcopy [--date YYYY-MM-DD]
    python -m advisor.cli fetch-fundamentals [--symbols ...]
    python -m advisor.cli regime
    python -m advisor.cli screen [--book trading|investing] [--capital N]
    python -m advisor.cli backtest [--symbols ...]
    python -m advisor.cli report SYMBOL            (needs ANTHROPIC_API_KEY)
    python -m advisor.cli digest [--capital N]
    python -m advisor.cli portfolio show|add|close ...
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
    up.add_argument("--symbols")

    bh = sub.add_parser("ingest-bhavcopy")
    bh.add_argument("--date")

    ff = sub.add_parser("fetch-fundamentals")
    ff.add_argument("--symbols")

    sub.add_parser("regime")

    sc = sub.add_parser("screen")
    sc.add_argument("--book", default="trading", choices=["trading", "investing"])
    sc.add_argument("--capital", type=float, default=1_000_000)

    bt = sub.add_parser("backtest")
    bt.add_argument("--symbols")

    pl = sub.add_parser("plan")
    pl.add_argument("action", choices=["new", "show", "approve", "orders", "placed"])
    pl.add_argument("--amount", type=float)
    pl.add_argument("--profile", default="balanced",
                    choices=["careful", "balanced", "ambitious"])
    pl.add_argument("--id", type=int)
    pl.add_argument("--csv", action="store_true", help="orders: write CSV instead of Kite basket")

    sub.add_parser("factors")
    sub.add_parser("risk")
    wf = sub.add_parser("walkforward")
    wf.add_argument("--folds", type=int, default=4)
    nt = sub.add_parser("notify")
    nt.add_argument("--capital", type=float, default=1_000_000)

    rp = sub.add_parser("report")
    rp.add_argument("symbol")

    dg = sub.add_parser("digest")
    dg.add_argument("--capital", type=float, default=1_000_000)

    pf = sub.add_parser("portfolio")
    pf.add_argument("action", choices=["show", "add", "close"])
    pf.add_argument("--symbol"); pf.add_argument("--book", default="investing")
    pf.add_argument("--qty", type=int); pf.add_argument("--cost", type=float)
    pf.add_argument("--stop", type=float); pf.add_argument("--id", type=int)
    pf.add_argument("--exit", type=float)

    sub.add_parser("status")

    args = p.parse_args()

    if args.cmd == "init-db":
        db.init_db(); print(f"initialized {db.config.DB_PATH}")
    elif args.cmd == "update-universe":
        from .universe import update_universe
        n, dropped = update_universe()
        print(f"universe: {n} constituents, {dropped} marked inactive")
    elif args.cmd == "update-prices":
        from .ingest.prices import update_prices
        symbols = args.symbols.split(",") if args.symbols else None
        print(f"prices: {update_prices(symbols=symbols, backfill=args.backfill)} rows")
    elif args.cmd == "ingest-bhavcopy":
        from .ingest.bhavcopy import ingest_bhavcopy
        d = date.fromisoformat(args.date) if args.date else date.today()
        rows = ingest_bhavcopy(d)
        print(f"bhavcopy {d}: {rows} rows" + (" (holiday/absent)" if rows == 0 else ""))
    elif args.cmd == "fetch-fundamentals":
        from .fundamentals import fetch_fundamentals_yf
        from .universe import active_symbols
        symbols = args.symbols.split(",") if args.symbols else active_symbols()
        print(f"fundamentals: {fetch_fundamentals_yf(symbols)} values")
    elif args.cmd == "regime":
        from .regime import compute_regime, last_state, record_regime
        r = compute_regime(prev_state=last_state())
        if r is None:
            print("insufficient data — run update-prices --backfill first")
        else:
            record_regime(r)
            print(f"state: {r.state}\nbreadth>200sma: {r.breadth_200:.0%}  "
                  f"breadth>50sma: {r.breadth_50:.0%}\n"
                  f"drawdown: {r.index_drawdown:.1%}  signals: {r.signals}")
    elif args.cmd == "screen":
        from .screener import run_screen
        res = run_screen(book=args.book, capital=args.capital)
        if res["regime"]:
            print(f"regime: {res['regime'].state}")
        print(res["candidates"].to_string(index=False) if not res["candidates"].empty
              else "no candidates")
        for plan in res["plans"]:
            print(f"  plan: {plan.to_dict()}")
    elif args.cmd == "backtest":
        from .backtest import backtest_breakout, load_prices_from_db
        symbols = args.symbols.split(",") if args.symbols else None
        result = backtest_breakout(load_prices_from_db(symbols))
        print(result.stats or "no trades generated")
    elif args.cmd == "plan":
        from . import planner
        if args.action == "new":
            if not args.amount:
                p.error("plan new needs --amount")
            plan = planner.build_plan(args.amount, args.profile)
            print(planner.render_plan(plan))
            print(f"\nTo approve: python -m advisor.cli plan approve --id {plan.plan_id}")
        elif args.action == "show":
            status, plan = planner.get_plan(args.id)
            print(f"status: {status}\n")
            print(planner.render_plan(plan))
        elif args.action == "approve":
            plan = planner.approve_plan(args.id)
            print(f"Plan {args.id} approved. Build the orders with:\n"
                  f"  python -m advisor.cli plan orders --id {args.id}")
        elif args.action == "orders":
            from . import broker
            if args.csv:
                path = broker.to_csv(args.id)
                print(f"wrote {path} — import it into your broker's order pad")
            else:
                path = broker.basket_form_html(args.id)
                print(f"wrote {path} — open it in a browser to review and confirm "
                      "the basket inside Kite")
            summary = broker.basket_summary(args.id)
            print(f"{summary['n_orders']} orders, about ₹{summary['total_value']:,.0f}")
            print(f"After they execute: python -m advisor.cli plan placed --id {args.id}")
        elif args.action == "placed":
            from . import broker
            broker.mark_placed(args.id)
            print(f"plan {args.id} recorded as placed; holdings opened with stops. "
                  "Nightly digest now watches them.")
    elif args.cmd == "factors":
        from .factors import rank_factors
        table = rank_factors()
        print(table.head(30).to_string() if not table.empty
              else "no data — run backfill + fetch-fundamentals first")
    elif args.cmd == "risk":
        import json as _json
        from .risk import portfolio_risk_report
        print(_json.dumps(portfolio_risk_report(), indent=2, default=str))
    elif args.cmd == "walkforward":
        from .backtest import load_prices_from_db
        from .walkforward import walk_forward
        import json as _json
        print(_json.dumps(walk_forward(load_prices_from_db(), n_folds=args.folds),
                          indent=2))
    elif args.cmd == "notify":
        from .notify import notify_digest
        print(f"sent {notify_digest(capital=args.capital)} message(s)")
    elif args.cmd == "report":
        from .ai_report import generate_report
        print(generate_report(args.symbol))
    elif args.cmd == "digest":
        from .digest import build_digest
        print(build_digest(capital=args.capital))
    elif args.cmd == "portfolio":
        from . import portfolio as pfm
        if args.action == "add":
            hid = pfm.add_holding(args.symbol, args.book, args.qty, args.cost, args.stop)
            print(f"holding {hid} added")
        elif args.action == "close":
            pfm.close_holding(args.id, args.exit)
            print(f"holding {args.id} closed at {args.exit}")
        else:
            snap = pfm.snapshot()
            if snap["positions"].empty:
                print("no open positions")
            else:
                cols = ["id", "symbol", "book", "qty", "avg_cost", "last",
                        "pnl_pct", "weight", "stop"]
                print(snap["positions"][cols].to_string(index=False))
            print(f"total ₹{snap['total_value']:,.0f}  heat {snap['heat_pct']:.1%}")
            for a in snap["alerts"]:
                print(f"ALERT: {a}")
    elif args.cmd == "status":
        with db.connect() as conn:
            for label, q in [
                ("stocks (active)", "SELECT COUNT(*) FROM stocks WHERE active=1"),
                ("stocks (total)", "SELECT COUNT(*) FROM stocks"),
                ("price rows", "SELECT COUNT(*) FROM prices_eod"),
                ("price date range", "SELECT MIN(date) || ' .. ' || MAX(date) FROM prices_eod"),
                ("fundamental values", "SELECT COUNT(*) FROM fundamentals"),
                ("open journal decisions", "SELECT COUNT(*) FROM journal_decisions WHERE status='open'"),
                ("last refresh", "SELECT job || ' @ ' || run_at FROM refresh_log ORDER BY run_at DESC LIMIT 1"),
            ]:
                print(f"{label}: {conn.execute(q).fetchone()[0]}")


if __name__ == "__main__":
    main()
