"""Portfolio planner: amount in → complete, approvable plan out.

The decision-first entry point (modules 03/04). Given an amount and a risk
profile, allocates across a core index sleeve and a satellite sleeve of the
screener's highest-conviction names, sizes every position, attaches a stop to
each, and reports the honest downside before the user approves anything.

Nothing here places an order. `broker.py` turns an APPROVED plan into a basket
the user confirms inside their own broker app.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

from . import db

# Core sleeve: liquid index ETFs on NSE. Symbol → what it tracks.
CORE_ETFS = [
    ("NIFTYBEES", "Nifty 50 index fund", 0.70),
    ("JUNIORBEES", "Nifty Next 50 index fund", 0.30),
]

# profile → (core, satellite, cash), max single satellite weight, risk per position
PROFILES = {
    "careful":   {"mix": (0.70, 0.15, 0.15), "max_pos": 0.05, "stop_mult": 2.5},
    "balanced":  {"mix": (0.60, 0.30, 0.10), "max_pos": 0.08, "stop_mult": 2.0},
    "ambitious": {"mix": (0.50, 0.40, 0.10), "max_pos": 0.12, "stop_mult": 2.0},
}
MIN_AMOUNT = 25_000
LIMIT_BUFFER = 0.002      # limit price 0.2% above last, so buys actually fill


@dataclass
class PlanLine:
    symbol: str
    role: str                 # 'core' | 'satellite'
    description: str
    qty: int
    price: float
    value: float
    stop: float | None
    risk_amount: float        # ₹ lost if the stop is hit
    conviction: float | None = None


@dataclass
class PortfolioPlan:
    created_at: str
    amount: float
    profile: str
    regime: str | None
    lines: list[PlanLine] = field(default_factory=list)
    invested: float = 0.0
    cash_left: float = 0.0
    total_risk: float = 0.0
    bad_month_estimate: float = 0.0
    notes: list[str] = field(default_factory=list)
    plan_id: int | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["lines"] = [asdict(l) if not isinstance(l, dict) else l for l in self.lines]
        return d


PLAN_SCHEMA = """
CREATE TABLE IF NOT EXISTS plans (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at  TEXT NOT NULL,
    amount      REAL NOT NULL,
    profile     TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'proposed',  -- proposed|approved|rejected|placed
    approved_at TEXT,
    plan_json   TEXT NOT NULL
);
"""


def _ensure(conn) -> None:
    conn.executescript(PLAN_SCHEMA)


def _last_price(conn, symbol: str) -> float | None:
    row = conn.execute(
        "SELECT close FROM prices_eod WHERE symbol=? AND source='yfinance' "
        "ORDER BY date DESC LIMIT 1", (symbol,)).fetchone()
    return float(row[0]) if row else None


def build_plan(amount: float, profile: str = "balanced",
               max_satellite_names: int = 5) -> PortfolioPlan:
    """Build a complete, approvable portfolio plan for `amount`."""
    profile = profile.lower()
    if profile not in PROFILES:
        raise ValueError(f"profile must be one of {sorted(PROFILES)}")
    if amount < MIN_AMOUNT:
        raise ValueError(f"minimum amount is ₹{MIN_AMOUNT:,} — below this, "
                         "brokerage and lot sizes eat the diversification")

    cfg = PROFILES[profile]
    core_w, sat_w, _cash_w = cfg["mix"]
    notes: list[str] = []

    from .regime import compute_regime, last_state
    from .screener import run_screen
    from .technical import compute_features
    from .indicators import atr

    reading = compute_regime(prev_state=last_state())
    regime_state = reading.state if reading else None

    # Risk-off: shift the satellite sleeve to cash (module 10 playbook)
    if reading is not None and not reading.risk_on():
        notes.append(f"Market regime is {reading.state}: the stock sleeve is held in "
                     "cash and only the index core is bought. This is the playbook, "
                     "not a forecast.")
        sat_w = 0.0
        core_w = min(core_w, 0.6)

    lines: list[PlanLine] = []
    with db.connect() as conn:
        _ensure(conn)

        # --- core sleeve ---
        core_amt = amount * core_w
        for symbol, desc, share in CORE_ETFS:
            price = _last_price(conn, symbol)
            if price is None:
                notes.append(f"No price for {symbol} — core allocation reduced. "
                             "Run update-prices with this symbol included.")
                continue
            qty = int(core_amt * share / price)
            if qty <= 0:
                continue
            lines.append(PlanLine(symbol=symbol, role="core", description=desc,
                                  qty=qty, price=round(price, 2),
                                  value=round(qty * price, 2), stop=None,
                                  risk_amount=0.0))

        # --- satellite sleeve ---
        if sat_w > 0:
            screen = run_screen(book="investing", capital=amount,
                                top_n=max_satellite_names * 3)
            cand = screen["candidates"]
            picked = 0
            if not cand.empty:
                # Pass 1: who actually qualifies (price + full technical read)?
                core_symbols = {s for s, _, _ in CORE_ETFS}
                eligible = []
                for _, row in cand.iterrows():
                    if len(eligible) >= max_satellite_names:
                        break
                    sym = row["symbol"]
                    if sym in core_symbols:
                        continue      # the index is the core sleeve, never a "pick"
                    price = _last_price(conn, sym)
                    if price is None:
                        continue
                    px = pd_read_prices(conn, sym)
                    feats = compute_features(px) if px is not None else None
                    if feats is None:
                        continue
                    eligible.append((sym, price, feats, float(row["conviction"])))

                # Pass 2: split the sleeve across the names that DID qualify, so
                # a short list concentrates (up to the profile cap) instead of
                # stranding the budget in unintended cash.
                sat_amt = amount * sat_w
                if eligible:
                    per_name = min(sat_amt / len(eligible), amount * cfg["max_pos"])
                    for sym, price, feats, conviction in eligible:
                        stop = max(feats["swing_low_20d"],
                                   price - cfg["stop_mult"] * feats["atr14"])
                        if stop >= price:
                            stop = price - cfg["stop_mult"] * feats["atr14"]
                        qty = int(per_name / price)
                        if qty <= 0:
                            continue
                        # risk uses the SHOWN price and stop, so the rupee figure
                        # the user approves reconciles exactly
                        shown_price, shown_stop = round(price, 2), round(stop, 2)
                        lines.append(PlanLine(
                            symbol=sym, role="satellite",
                            description=f"conviction {conviction:.0f}/100",
                            qty=qty, price=shown_price,
                            value=round(qty * shown_price, 2),
                            stop=shown_stop,
                            risk_amount=round(qty * (shown_price - shown_stop), 2),
                            conviction=round(conviction, 1)))
                        picked += 1
                    if len(eligible) < max_satellite_names:
                        notes.append(
                            f"Only {len(eligible)} stock(s) passed the filters, so each "
                            "gets a larger share (capped at the profile's position "
                            "limit) and the remainder stays in cash.")
            if picked == 0:
                notes.append("No stock passed the quality and trend filters today, so "
                             "that sleeve stays in cash. A forced trade is worse than "
                             "no trade.")

    invested = sum(l.value for l in lines)
    total_risk = sum(l.risk_amount for l in lines)
    # Honest downside. The index sleeve falls with the market (~7% in a bad
    # month). For a stock pick we take the WORSE of its stop distance and a
    # ~9% market shock — deliberately refusing to credit the stop, because in
    # the month that matters prices gap through stops (module 04: stops are
    # thesis invalidation, not insurance).
    core_val = sum(l.value for l in lines if l.role == "core")
    sat_bad = sum(max(l.risk_amount, l.value * 0.09)
                  for l in lines if l.role == "satellite")
    bad_month = core_val * 0.07 + sat_bad

    plan = PortfolioPlan(
        created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        amount=round(amount, 2), profile=profile, regime=regime_state,
        lines=lines, invested=round(invested, 2),
        cash_left=round(amount - invested, 2), total_risk=round(total_risk, 2),
        bad_month_estimate=round(bad_month, 2), notes=notes)

    with db.connect() as conn:
        _ensure(conn)
        cur = conn.execute(
            "INSERT INTO plans (created_at, amount, profile, plan_json) VALUES (?,?,?,?)",
            (plan.created_at, plan.amount, plan.profile,
             json.dumps(plan.to_dict(), default=str)))
        plan.plan_id = int(cur.lastrowid)
    return plan


def pd_read_prices(conn, symbol: str):
    """OHLCV frame for one symbol (None when absent)."""
    import pandas as pd

    df = pd.read_sql_query(
        "SELECT date, open, high, low, close, volume FROM prices_eod "
        "WHERE symbol=? AND source='yfinance' ORDER BY date",
        conn, params=[symbol], parse_dates=["date"])
    return df.set_index("date") if not df.empty else None


def approve_plan(plan_id: int) -> dict:
    """Mark a proposed plan approved. Orders can only be built from this state."""
    with db.connect() as conn:
        _ensure(conn)
        row = conn.execute("SELECT status, plan_json FROM plans WHERE id=?",
                           (plan_id,)).fetchone()
        if row is None:
            raise ValueError(f"no plan {plan_id}")
        if row[0] == "approved":
            return json.loads(row[1])
        if row[0] != "proposed":
            raise ValueError(f"plan {plan_id} is {row[0]} — build a fresh plan")
        conn.execute(
            "UPDATE plans SET status='approved', approved_at=? WHERE id=?",
            (datetime.now(timezone.utc).isoformat(timespec="seconds"), plan_id))
    return json.loads(row[1])


def get_plan(plan_id: int) -> tuple[str, dict]:
    with db.connect() as conn:
        _ensure(conn)
        row = conn.execute("SELECT status, plan_json FROM plans WHERE id=?",
                           (plan_id,)).fetchone()
    if row is None:
        raise ValueError(f"no plan {plan_id}")
    return row[0], json.loads(row[1])


def render_plan(plan: PortfolioPlan | dict) -> str:
    """Human-readable plan for the terminal or a message."""
    p = plan.to_dict() if isinstance(plan, PortfolioPlan) else plan
    out = [f"Plan #{p.get('plan_id')} — ₹{p['amount']:,.0f}, {p['profile']} profile"]
    if p.get("regime"):
        out.append(f"Market regime: {p['regime']}")
    out.append("")
    out.append(f"{'Symbol':<14}{'Role':<11}{'Qty':>8}{'Price':>11}"
               f"{'Value':>13}{'Exit at':>11}")
    for l in p["lines"]:
        stop = f"{l['stop']:,.2f}" if l["stop"] else "hold"
        out.append(f"{l['symbol']:<14}{l['role']:<11}{l['qty']:>8,}"
                   f"{l['price']:>11,.2f}{l['value']:>13,.0f}{stop:>11}")
    out += ["",
            f"Invested ₹{p['invested']:,.0f} · cash left ₹{p['cash_left']:,.0f}",
            f"If every stop is hit: -₹{p['total_risk']:,.0f}",
            f"A normal bad month: about -₹{p['bad_month_estimate']:,.0f}"]
    for n in p.get("notes", []):
        out.append(f"NOTE: {n}")
    out += ["", "Nothing is bought until you approve this plan.",
            "Decision-support only, not investment advice."]
    return "\n".join(out)
