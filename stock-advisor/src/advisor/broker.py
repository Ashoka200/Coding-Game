"""Broker layer: an APPROVED plan → orders in your Demat account.

Design stance — the orders leave this system as a *basket you confirm inside
your broker's own app*, with your own PIN. That is deliberate:

* it needs no stored broker password or permanent trading token here;
* you see every order before it is live, so a bad plan cannot execute silently;
* it matches how SEBI treats personal-account automation — you remain the one
  who places the trade.

Three routes, in order of how most people should use them:

1. `basket_form_html(plan)` — Zerodha Kite basket. Writes a small HTML file;
   opening it posts the basket to Kite, where you review and confirm. Needs
   only a free Kite Connect *api_key* (kite.trade), no secret, no subscription.
2. `to_csv(plan)` — broker-agnostic CSV to import into any order pad
   (Upstox, Angel One, Groww all accept a symbol/qty/price list).
3. `place_via_kite_connect(...)` — genuine programmatic placement. Requires a
   paid Kite Connect subscription plus a daily access token, and refuses to run
   unless you pass `i_understand=True`. Orders go live immediately; the module
   still refuses anything not approved.
"""
from __future__ import annotations

import csv
import html
import io
import json
import os
from datetime import datetime, timezone

from . import db
from .planner import LIMIT_BUFFER, get_plan

KITE_BASKET_URL = "https://kite.zerodha.com/connect/basket"
EXCHANGE = "NSE"


def _orders_from_plan(plan: dict, order_type: str = "LIMIT") -> list[dict]:
    """Plan lines → Kite-shaped order dicts (delivery/CNC buys)."""
    orders = []
    for line in plan["lines"]:
        if line["qty"] <= 0:
            continue
        order = {
            "variety": "regular",
            "tradingsymbol": line["symbol"],
            "exchange": EXCHANGE,
            "transaction_type": "BUY",
            "order_type": order_type,
            "quantity": int(line["qty"]),
            "product": "CNC",            # delivery — this is investing, not intraday
            "readonly": False,
        }
        if order_type == "LIMIT":
            # limit slightly above last so the order fills rather than lapsing
            order["price"] = round(line["price"] * (1 + LIMIT_BUFFER), 1)
        orders.append(order)
    return orders


def _require_approved(plan_id: int) -> dict:
    status, plan = get_plan(plan_id)
    if status not in ("approved", "placed"):
        raise ValueError(
            f"plan {plan_id} is '{status}' — approve it first "
            f"(advisor.cli plan approve --id {plan_id}). Orders are never built "
            "from an unapproved plan.")
    return plan


def basket_form_html(plan_id: int, api_key: str | None = None,
                     out_path: str | None = None,
                     order_type: str = "LIMIT") -> str:
    """Write a self-posting form that opens this plan as a basket in Kite.

    api_key: your Kite Connect api_key (free to create at kite.trade), or set
    KITE_API_KEY. Open the written file in a browser and Kite takes over —
    you confirm the basket there.
    """
    api_key = api_key or os.environ.get("KITE_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Set KITE_API_KEY (create a free app at kite.trade to get one) or "
            "pass api_key=... . No secret is needed for baskets.")
    plan = _require_approved(plan_id)
    orders = _orders_from_plan(plan, order_type)
    payload = html.escape(json.dumps(orders), quote=True)
    total = sum(o["quantity"] * o.get("price", 0) for o in orders)

    doc = f"""<!doctype html>
<meta charset="utf-8">
<title>Send basket to Kite</title>
<body style="font-family: system-ui, sans-serif; max-width: 560px; margin: 60px auto">
<h2>Plan #{plan_id}: {len(orders)} orders, about ₹{total:,.0f}</h2>
<p>Pressing the button opens Zerodha Kite with these orders pre-filled. You
review and confirm them there with your own PIN — nothing is placed until you do.</p>
<form method="POST" action="{KITE_BASKET_URL}" target="_blank">
  <input type="hidden" name="api_key" value="{html.escape(api_key, quote=True)}">
  <input type="hidden" name="data" value="{payload}">
  <button type="submit" style="font-size:16px;padding:12px 22px;border:none;
    border-radius:6px;background:#A8761F;color:#fff;cursor:pointer">
    Open basket in Kite</button>
</form>
<pre style="background:#f4f4f0;padding:14px;border-radius:6px;overflow-x:auto">{
    html.escape(json.dumps(orders, indent=2))}</pre>
</body>"""

    out_path = out_path or f"kite-basket-plan-{plan_id}.html"
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(doc)
    return out_path


def to_csv(plan_id: int, out_path: str | None = None,
           order_type: str = "LIMIT") -> str:
    """Broker-agnostic CSV of the approved orders."""
    plan = _require_approved(plan_id)
    orders = _orders_from_plan(plan, order_type)
    out_path = out_path or f"orders-plan-{plan_id}.csv"
    with open(out_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["Exchange", "Symbol", "Transaction", "Quantity",
                    "OrderType", "Price", "Product"])
        for o in orders:
            w.writerow([o["exchange"], o["tradingsymbol"], o["transaction_type"],
                        o["quantity"], o["order_type"], o.get("price", ""),
                        o["product"]])
    return out_path


def basket_summary(plan_id: int, order_type: str = "LIMIT") -> dict:
    """What the orders would be, without writing anything (for review/UI)."""
    plan = _require_approved(plan_id)
    orders = _orders_from_plan(plan, order_type)
    return {"plan_id": plan_id, "n_orders": len(orders),
            "total_value": round(sum(o["quantity"] * o.get("price", 0)
                                     for o in orders), 2),
            "orders": orders}


def mark_placed(plan_id: int, note: str = "") -> None:
    """Record that the basket was actually placed, and open the holdings."""
    from .portfolio import add_holding

    plan = _require_approved(plan_id)
    with db.connect() as conn:
        conn.execute("UPDATE plans SET status='placed' WHERE id=?", (plan_id,))
    for line in plan["lines"]:
        add_holding(line["symbol"],
                    "investing" if line["role"] == "core" else "trading",
                    qty=int(line["qty"]), avg_cost=float(line["price"]),
                    stop=line.get("stop"))
    with db.connect() as conn:
        db.log_refresh(conn, "orders_placed", True,
                       f"plan {plan_id} at "
                       f"{datetime.now(timezone.utc).isoformat(timespec='seconds')} {note}")


def place_via_kite_connect(plan_id: int, i_understand: bool = False,
                           api_key: str | None = None,
                           access_token: str | None = None,
                           order_type: str = "LIMIT") -> list[str]:
    """Place the approved plan programmatically (orders go LIVE immediately).

    Requires a paid Kite Connect subscription, `pip install kiteconnect`, and a
    daily access token (KITE_ACCESS_TOKEN). Deliberately gated: pass
    i_understand=True to confirm you accept that this places real orders with
    no further confirmation step.
    """
    if not i_understand:
        raise RuntimeError(
            "Refusing to place live orders without i_understand=True. The basket "
            "route (basket_form_html) is safer: you confirm inside Kite.")
    api_key = api_key or os.environ.get("KITE_API_KEY")
    access_token = access_token or os.environ.get("KITE_ACCESS_TOKEN")
    if not api_key or not access_token:
        raise RuntimeError("KITE_API_KEY and KITE_ACCESS_TOKEN are both required.")

    plan = _require_approved(plan_id)
    try:
        from kiteconnect import KiteConnect
    except ImportError as e:
        raise RuntimeError("pip install kiteconnect to use direct placement") from e

    kite = KiteConnect(api_key=api_key)
    kite.set_access_token(access_token)
    ids = []
    for o in _orders_from_plan(plan, order_type):
        ids.append(kite.place_order(
            variety=kite.VARIETY_REGULAR, exchange=o["exchange"],
            tradingsymbol=o["tradingsymbol"],
            transaction_type=o["transaction_type"], quantity=o["quantity"],
            product=kite.PRODUCT_CNC, order_type=o["order_type"],
            price=o.get("price")))
    mark_placed(plan_id, note=f"kite_connect ids={','.join(map(str, ids))}")
    return ids
