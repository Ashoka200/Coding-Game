// The live path, end to end without a network: market clock → feed parsing →
// the tape writing prices into the DOM. The point of these checks is that the
// page never calls something "live" that isn't.
import fs from "fs";
import { marketState, secondsToNextChange } from "./netlify/functions/_market.mjs";

let pass = 0, fail = 0;
const ok = (c, m) => { console.log((c ? "PASS " : "FAIL ") + m); c ? pass++ : fail++; };

/* ---------- 1. the clock ---------- */
const at = (iso) => marketState(new Date(iso));
ok(at("2026-08-23T06:30:00Z").state === "weekend", "Sunday is the weekend");
ok(at("2026-08-23T06:30:00Z").live === false, "weekend is never live");
ok(at("2026-08-24T03:35:00Z").state === "pre_open", "09:05 IST is the pre-open");
ok(at("2026-08-24T05:30:00Z").state === "open", "11:00 IST is open");
ok(at("2026-08-24T05:30:00Z").live === true, "mid-session is live");
ok(at("2026-08-24T10:15:00Z").state === "closing_auction", "15:45 IST is the auction");
ok(at("2026-08-24T10:15:00Z").live === false, "the auction is NOT live");
ok(at("2026-08-24T14:30:00Z").live === false, "20:00 IST is not live");
ok(secondsToNextChange(new Date("2026-08-24T03:35:00Z")) === 600, "10 min to the bell");

/* ---------- 2. the feed ---------- */
const realFetch = globalThis.fetch;
globalThis.fetch = async (url) => {
  const u = String(url);
  if (u.includes("equity-stockIndices")) return { ok: true, json: async () => ({
    timestamp: "24-Aug-2026 11:04:31",
    data: [
      { symbol: "NIFTY 50", lastPrice: 24810.2 },
      { symbol: "RELIANCE", lastPrice: "1,412.60", previousClose: "1,398.00",
        change: "14.60", pChange: "1.04", totalTradedVolume: "8,412,003",
        lastUpdateTime: "24-Aug-2026 11:04:31" },
    ] }) };
  if (u.includes("allIndices")) return { ok: true, json: async () => ({
    timestamp: "24-Aug-2026 11:04:31",
    data: [{ index: "NIFTY 50", last: "24,810.20", previousClose: "24,600.00",
             variation: "210.20", percentChange: "0.85" }] }) };
  if (u.includes("nseindia.com")) return {
    ok: true, headers: { getSetCookie: () => ["nsit=a; Path=/"] }, text: async () => "" };
  throw new Error("network blocked in test");
};
const live = (await import("./netlify/functions/live.mjs")).default;
const res = await live(new Request("https://x/api/live?index=1&symbols=RELIANCE,NOSUCH"));
const body = await res.json();
const rel = body.quotes.find((q) => q.symbol === "RELIANCE");

ok(res.headers.get("Cache-Control").includes("no-store"), "a live price is never cached");
ok(rel.ltp === 1412.6, "Indian comma format parsed to a number");
ok(Math.abs(rel.pChange - 0.0104) < 1e-9, "percent normalised to a fraction");
ok(rel.volume === 8412003, "volume parsed");
ok(rel.exchange === "NSE", "the source is named on the quote");
ok(rel.tickTime === "24-Aug-2026 11:04:31", "the exchange's own strike time is carried");
ok(body.quotes.find((q) => q.symbol === "NOSUCH").error === "no live price",
   "an unpriced symbol errors rather than inventing a price");
ok(!body.quotes.some((q) => q.symbol === "NIFTY 50"), "the index header row is not a stock");
ok(body.indices[0].symbol === "NIFTY50" && body.indices[0].ltp === 24810.2,
   "index level served for the desk note");
ok(Array.isArray(body.diagnostics) && body.diagnostics.some((d) => d.includes("NOSUCH")),
   "every failed source is reported, not swallowed");

/* ---------- 3. the tape writing into the page ---------- */
function el(tag) {
  const n = { tagName: tag, attrs: {}, _t: "", _c: new Set(), children: [],
    classList: { add: (c) => n._c.add(c), remove: (c) => n._c.delete(c),
      toggle: (c, f) => (f ? n._c.add(c) : n._c.delete(c)), contains: (c) => n._c.has(c) },
    set textContent(v) { n._t = String(v); }, get textContent() { return n._t; },
    set innerHTML(v) { n._t = String(v); }, get innerHTML() { return n._t; },
    setAttribute: (k, v) => { n.attrs[k] = v; }, getAttribute: (k) => n.attrs[k] ?? null,
    addEventListener: () => {}, get offsetWidth() { return 1; },
    set className(v) { n.attrs.class = v; }, get className() { return n.attrs.class || ""; } };
  return n;
}
const price = el("td"); price.setAttribute("data-live-ltp", "RELIANCE");
const chg = el("td");   chg.setAttribute("data-live-chg", "RELIANCE");
const stamp = el("div"); stamp.setAttribute("data-live-at", "RELIANCE");
const tape = el("div");
const dom = { "[data-live-ltp]": [price], "[data-live-chg]": [chg], "[data-live-at]": [stamp] };

global.document = {
  querySelectorAll: (sel) => dom[sel] || [],
  getElementById: (id) => (id === "tape" ? tape : null),
  addEventListener: () => {},
  hidden: false,
};
global.window = { ADV_COMPANY: { num: (n) => n == null ? "—" : n.toFixed(2) } };
global.fetch = async () => ({ json: async () => body });
global.setTimeout = () => 0;            // no real scheduling inside the test
global.clearTimeout = () => {};

new Function(fs.readFileSync("./public/live.js", "utf8"))();
const L = global.window.ADV_LIVE;
L.track(["RELIANCE"]);
await new Promise((r) => setImmediate(r));   // let the poll settle

ok(price.textContent === "1412.60", "the price cell was written by the tape");
ok(chg.textContent === "+1.04%", "the change cell was written and signed");
ok(chg._c.has("pos"), "a rising change is marked positive");
ok(stamp.textContent.includes("24-Aug-2026 11:04:31") && stamp.textContent.includes("NSE"),
   "every live price carries its strike time and source");

// A second poll at the same price must not flash — a flash means it moved.
price._c.clear();
await L.pause(false);
ok(!price._c.has("tick-up") && !price._c.has("tick-down"),
   "an unchanged price does not flash");

// Now move it, and the flash must appear.
body.quotes[0].ltp = 1420.00;
await new Promise((r) => setImmediate(r));
global.fetch = async () => ({ json: async () => body });
L.pause(true); L.pause(false);
await new Promise((r) => setImmediate(r));
ok(price.textContent === "1420.00" && price._c.has("tick-up"),
   "a price that moved up is repainted and flashed green");

// The status line must never say "Live" outside market hours.
const closedBody = { ...body, market: { ...body.market, state: "closed", live: false,
                                        label: "Market closed", feed: "closed" } };
global.fetch = async () => ({ json: async () => closedBody });
L.pause(true); L.pause(false);
await new Promise((r) => setImmediate(r));
ok(!/Live/.test(tape.innerHTML), "a closed market is never labelled Live");
ok(/close/i.test(tape.innerHTML), "a closed market says it is showing the last close");

globalThis.fetch = realFetch;
console.log("\n" + (fail ? fail + " FAILED" : "all checks passed") + " (" + pass + " passed)");
process.exit(fail ? 1 : 0);
