"""Daily digest: regime + shortlists + portfolio alerts as one text block.

Phase 5 delivery target: pipe this into a Telegram bot / email. For now the CLI
prints it and cron can mail it (`... digest | mail -s "Advisor" you@x`).
"""
from __future__ import annotations

from datetime import date


def build_digest(capital: float = 1_000_000) -> str:
    from .portfolio import snapshot
    from .regime import compute_regime, last_state, record_regime
    from .screener import run_screen

    lines = [f"# 360° Advisor digest — {date.today().isoformat()}", ""]

    reading = compute_regime(prev_state=last_state())
    if reading:
        record_regime(reading)
        lines += [f"## Regime: {reading.state}",
                  f"breadth>200sma {reading.breadth_200:.0%} · "
                  f"drawdown {reading.index_drawdown:.1%} · "
                  f"signals: {', '.join(reading.signals) or 'none'}", ""]
        if not reading.risk_on():
            lines += ["**Playbook active (module 10): no new trading longs; "
                      "review the crisis shopping list.**", ""]
    else:
        lines += ["## Regime: insufficient data (run backfill)", ""]

    for book in ("trading", "investing"):
        res = run_screen(book=book, capital=capital)
        cand = res["candidates"]
        lines.append(f"## Top {book} candidates")
        if cand.empty:
            lines.append("_none (no qualifying setups or risk-off regime)_")
        else:
            for _, r in cand.head(10).iterrows():
                lines.append(
                    f"- **{r['symbol']}** conv {r['conviction']:.0f} "
                    f"(F{r['fund_score']:.0f}/T{r['tech_score']:.0f}/RS{r['rs_pct']:.0f}) "
                    f"stage {r['stage']} {', '.join(r['setups']) or ''}")
        if book == "trading":
            for p in res["plans"][:5]:
                lines.append(
                    f"    plan {p.symbol}: entry {p.entry_low}-{p.entry_high} "
                    f"stop {p.stop} T1 {p.target1} T2 {p.target2} "
                    f"qty {p.shares} (risk ₹{p.capital_at_risk:,.0f})")
        lines.append("")

    snap = snapshot()
    lines.append("## Portfolio")
    lines.append(f"value ₹{snap['total_value']:,.0f} · heat {snap['heat_pct']:.1%}")
    if snap["alerts"]:
        lines.append("**Alerts:**")
        lines += [f"- {a}" for a in snap["alerts"]]
    else:
        lines.append("no alerts")
    lines += ["", "_Decision-support only, not investment advice._"]
    return "\n".join(lines)
