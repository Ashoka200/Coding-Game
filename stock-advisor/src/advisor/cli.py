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
import sys
from datetime import date

from . import db

# Hosts a step depends on, so the message can name the one that refused.
_HOST_HINTS = {
    "nseindia": "NSE (archives.nseindia.com / nsearchives.nseindia.com)",
    "yahoo": "Yahoo Finance",
    "screener": "screener.in",
    "bseindia": "BSE",
    "telegram": "Telegram",
}


def _friendly_network_error(exc: Exception) -> str:
    """Turn a requests traceback into something a person can act on."""
    text = str(exc)
    host = next((label for key, label in _HOST_HINTS.items() if key in text), None)
    lines = [f"Could not reach {host}." if host else "A data source could not be reached."]
    low = text.lower()
    if "403" in text or "forbidden" in low:
        lines.append("The connection was refused (403). This usually means a proxy, VPN or "
                     "corporate network is blocking it, or the source is throttling your IP.")
        lines.append("Try again from a normal home connection, or wait and retry.")
    elif "timed out" in low or "timeout" in low:
        lines.append("The request timed out. The source may be slow or briefly down; retry "
                     "in a few minutes.")
    elif "name or service not known" in low or "nodename" in low or "getaddrinfo" in low:
        lines.append("DNS could not resolve the host — check that this machine is online.")
    else:
        lines.append(f"Underlying error: {type(exc).__name__}: {text[:200]}")
    lines.append("Nothing was written to the database. No figures are ever guessed to fill a gap.")
    return "\n".join(lines)


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

    # --- the engines that had no way in until now ---
    ln = sub.add_parser("lenses", help="what five great investors would say")
    ln.add_argument("symbol")
    ln.add_argument("--log", action="store_true",
                    help="record this reading in the journal so the system can "
                         "later measure how well its own scores predicted")

    tg = sub.add_parser("target", help="what a return target actually requires")
    tg.add_argument("--annual", type=float, default=0.50,
                    help="target annual return, e.g. 0.50 for 50%%")

    gr = sub.add_parser("grade", help="grade a trade plan statistically")
    gr.add_argument("symbol")
    gr.add_argument("--entry", type=float, required=True)
    gr.add_argument("--target", type=float, required=True)
    gr.add_argument("--stop", type=float, required=True)

    sub.add_parser("calibration", help="what the system has measured about itself")

    mc = sub.add_parser("microcap", help="can this small-cap position be exited?")
    mc.add_argument("symbol")
    mc.add_argument("--amount", type=float, required=True)

    args = p.parse_args()

    try:
        _dispatch(p, args)
    except KeyboardInterrupt:
        print("\ninterrupted — nothing partial was committed")
        sys.exit(130)
    except Exception as exc:                     # noqa: BLE001 - top-level UX boundary
        import requests
        if isinstance(exc, (requests.RequestException, OSError)):
            print(_friendly_network_error(exc), file=sys.stderr)
            sys.exit(2)
        raise


def _dispatch(p, args) -> None:
    if args.cmd == "lenses":
        _cmd_lenses(args)
    elif args.cmd == "target":
        _cmd_target(args)
    elif args.cmd == "grade":
        _cmd_grade(args)
    elif args.cmd == "calibration":
        _cmd_calibration(args)
    elif args.cmd == "microcap":
        _cmd_microcap(args)
    elif args.cmd == "init-db":
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



# --------------------------------------------------------------------------
# the analytical surface — engines that were built but unreachable
# --------------------------------------------------------------------------
def _facts_for(symbol: str) -> dict:
    """Assemble what the lenses need from whatever the store actually holds."""
    from .fundamentals import latest_fundamentals
    try:
        f = latest_fundamentals(symbol) or {}
    except Exception:
        f = {}
    return dict(f, symbol=symbol)


def _cmd_lenses(args) -> None:
    from .calibrate import build_context
    from .failures import discount_lenses
    from .masters import apply_all, consensus

    facts = _facts_for(args.symbol)
    # A live cross-section if the store has one; otherwise the fixed fallbacks.
    try:
        from .fundamentals import all_latest_fundamentals
        universe = all_latest_fundamentals()
    except Exception:
        universe = []
    ctx = build_context(universe, None, as_of="today") if universe else None

    verdicts = apply_all(facts, ctx)
    print(f"\n{args.symbol} — five investors\n" + "-" * 58)
    for v in verdicts:
        score = "  n/a" if v.score is None else f"{v.score * 100:4.0f}%"
        print(f"{score}  {v.author:<22} {v.verdict}")
        for c in v.criteria:
            mark = "?" if c.passed is None else ("+" if c.passed else "-")
            print(f"         {mark} {c.name}: {c.seen}")
        print()

    con = consensus(verdicts)
    if con["ok"]:
        print(f"Consensus: {con['stance']}")
        if con["unanimous_weaknesses"]:
            print(f"  every lens that tested them fails on: "
                  f"{', '.join(con['unanimous_weaknesses'])}")

    if getattr(args, "log", False):
        _log_lens_reading(args.symbol, verdicts, con)

    d = discount_lenses(facts, verdicts)
    print(f"\nFailure modes: {d['headline']}")
    for m in d["fired"]:
        print(f"  ! {m['name']} ({m['severity']}) — {m['evidence']}")
        print(f"    {m['what_to_do']}")
    if d["suspended_authors"]:
        print(f"  endorsements to discount: {', '.join(d['suspended_authors'])}")


def _log_lens_reading(symbol: str, verdicts, con) -> None:
    """Record the scores before the outcome is known.

    This is the only way the correlation between lenses and the system's own
    skill ever become measurable: they need a history of scores written down at
    the moment of the call, not reconstructed afterwards when the answer is
    already visible.
    """
    from .journal import log_decision

    scored = {v.author: v.score for v in verdicts if v.score is not None}
    if not scored:
        print("\n  nothing scored, so nothing logged")
        return
    conviction = int(round(sum(scored.values()) / len(scored) * 100))
    try:
        did = log_decision(
            symbol=symbol, book="investing", action="watch",
            conviction=conviction,
            thesis=(con.get("stance") if isinstance(con, dict) and con.get("ok")
                    else "lens reading"),
            engine_scores={"lenses": scored},
        )
        print(f"\n  logged as decision {did} (conviction {conviction}) — close it "
              f"with an exit price later and it becomes evidence")
    except Exception as exc:                     # noqa: BLE001
        print(f"\n  could not log: {exc}")


def _cmd_target(args) -> None:
    from .learning import requirements_with_measured
    from .stats import feasible_target

    r = requirements_with_measured(args.annual)
    f = feasible_target((1 + args.annual) ** (1 / 250) - 1)
    print(f"\nA target of {args.annual * 100:.0f}% a year\n" + "-" * 58)
    print(f"  requires a Sharpe ratio of        {r['required_sharpe']:.2f}")
    print(f"  {f.verdict}")
    if r["independent_decisions_per_year"]:
        print(f"  independent decisions per year    "
              f"{r['independent_decisions_per_year']:.0f} "
              f"({r['independent_decisions_per_trading_day']:.1f} a day)")
    print(f"  {r['confidence']}")
    for name, p in r["parameter_provenance"].items():
        mark = "measured" if p["source"] == "measured" else "ASSUMED"
        print(f"    {name:<26} {p['value']:.3f}  [{mark}]")
    sig = r["signal_requirement"]
    if sig.get("reachable"):
        print(f"  different signals needed          {sig['signals_needed']}")
    else:
        print(f"  {sig['why']}")
        for path in (r.get("paths_if_unreachable") or []):
            print(f"    - signals of Sharpe {path['single_signal_sharpe']:.1f} "
                  f"need correlation below {path['max_average_correlation']:.2f} "
                  f"({path['note']})")


def _cmd_grade(args) -> None:
    from .stats import describe_returns, grade_trade
    closes = _closes_for(args.symbol)
    prof = describe_returns(closes) if closes else None
    if prof is None:
        print(f"{args.symbol}: not enough price history to grade a plan")
        return
    g = grade_trade(args.entry, args.target, args.stop, prof)
    if not g["ok"]:
        print(g["why"]); return
    o = g["odds"]
    print(f"\n{args.symbol} — entry {args.entry}, target {args.target}, "
          f"stop {args.stop}\n" + "-" * 58)
    print(f"  reward to risk                 {o['reward_to_risk']:.2f} : 1")
    print(f"  chance of target before stop   {o['p_target_first'] * 100:.0f}%")
    print(f"  breakeven win rate needed      {o['breakeven_win_rate'] * 100:.0f}%")
    print(f"  noise alone reaches this stop  {g['noise_stop_probability'] * 100:.0f}% "
          f"of the time")
    print(f"  closest sensible stop          "
          f"{g['minimum_safe_stop_pct'] * 100:.1f}% away")
    print(f"  risk per trade                 "
          f"{g['sizing']['recommended'] * 100:.2f}% of capital")
    print(f"\n  {g['verdict']}")
    for flag in g["flags"]:
        print(f"    ! {flag}")


def _cmd_microcap(args) -> None:
    from .microcap import assess
    facts = _facts_for(args.symbol)
    facts.setdefault("closes", _closes_for(args.symbol))
    r = assess(facts, args.amount)
    e = r["exit"]
    print(f"\n{args.symbol} at {args.amount:,.0f}\n" + "-" * 58)
    print(f"  {r['headline']}\n")
    print(f"  sessions to exit            {e['days_to_exit']:.1f}")
    print(f"  round trip cost             {e['round_trip_cost_pct'] * 100:.1f}%")
    print(f"  largest exitable position   {e['max_safe_position']:,.0f}")
    print(f"  circuit band                {e['circuit_band'] * 100:.0f}% "
          f"({e['locked_days_for_30pct_fall']:.0f} locked days for a 30% fall)")
    print(f"  surveillance                {r['surveillance']['note']}")
    for w in e["warnings"]:
        print(f"    ! {w}")
    if r["integrity"]["fired"]:
        for m in r["integrity"]["fired"]:
            print(f"    ! {m['marker']} — {m['why']}")
    print(f"\n  {r['position_advice']}")
    if r["cost_note"]:
        print(f"  {r['cost_note']}")


def _closes_for(symbol: str) -> list:
    try:
        import pandas as pd
        from . import db
        with db.connect() as con:
            rows = con.execute(
                "SELECT close FROM prices WHERE symbol=? ORDER BY date", (symbol,)
            ).fetchall()
        return [r[0] for r in rows if r[0]]
    except Exception:
        return []


def _cmd_calibration(args) -> None:
    """What the system has actually learned about itself, as opposed to what it
    was told to assume."""
    from .learning import live_parameters

    live = live_parameters()
    print("\nCalibration\n" + "-" * 58)
    print(f"  {live['summary']}")
    print(f"  closed calls on record: {live['closed_calls']}\n")
    for name, p in live["parameters"].items():
        mark = "measured" if p["source"] == "measured" else "ASSUMED"
        trust = "" if p["trustworthy"] else "  (not yet distinguishable from luck)"
        print(f"  {name}")
        print(f"    {p['value']:.4f}  [{mark}]  n={p['n']}{trust}")
        print(f"    {p['note']}\n")
    if live["decay"] and live["decay"].get("ok"):
        d = live["decay"]
        print(f"  signal decay: recent IC {d['recent_ic']:.3f} against "
              f"{d['earlier_ic']:.3f} earlier")
        print(f"    {d['action']}\n")
    if live["warning"]:
        print(f"  ! {live['warning']}")


if __name__ == "__main__":
    main()
