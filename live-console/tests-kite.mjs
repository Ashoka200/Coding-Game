// The Kite binary protocol, exercised against packets built to spec.
//
// This is the highest-stakes parser in the codebase: a wrong offset does not
// crash, it silently shows a price that is off by a factor of a hundred or
// reads a volume as a price. So every packet shape Kite emits is constructed
// here byte by byte and checked field by field.
import fs from "fs";

let pass = 0, fail = 0;
const ok = (c, m) => { console.log((c ? "PASS " : "FAIL ") + m); c ? pass++ : fail++; };
const near = (a, b) => a != null && Math.abs(a - b) < 1e-6;

/* ---------- load kite.js against a minimal DOM ---------- */
const listeners = {};
global.document = {
  addEventListener: (e, fn) => { listeners[e] = fn; },
  getElementById: () => null,
};
global.sessionStorage = {
  _m: {}, getItem(k) { return this._m[k] ?? null; },
  setItem(k, v) { this._m[k] = String(v); }, removeItem(k) { delete this._m[k]; },
};
global.history = { replaceState: () => {} };
global.window = { location: { hash: "", pathname: "/", search: "" } };
global.WebSocket = function () {};
new Function(fs.readFileSync("./public/kite.js", "utf8")).call(global);
const K = global.window.ADV_KITE;

/* ---------- packet builders, straight from the Kite v3 spec ---------- */
function message(packets) {
  const total = 2 + packets.reduce((n, p) => n + 2 + p.byteLength, 0);
  const buf = new ArrayBuffer(total);
  const dv = new DataView(buf);
  dv.setInt16(0, packets.length);
  let o = 2;
  for (const p of packets) {
    dv.setInt16(o, p.byteLength); o += 2;
    new Uint8Array(buf).set(new Uint8Array(p), o); o += p.byteLength;
  }
  return buf;
}
function packet(len, fields) {
  const b = new ArrayBuffer(len), dv = new DataView(b);
  for (const [off, val] of fields) dv.setInt32(off, val);
  return b;
}

const RELIANCE = 738561;          // segment 1 (NSE) → prices in paise
const NIFTY50  = 256265;          // segment 9 (indices) → not tradable

/* ---------- 1. LTP-mode packet (8 bytes) ---------- */
let t = K._parseMessage(message([packet(8, [[0, RELIANCE], [4, 141260]])]))[0];
ok(t.token === RELIANCE, "LTP packet: token read");
ok(near(t.ltp, 1412.60), "LTP packet: paise scaled to rupees");
ok(t.tradable === true, "an NSE equity is tradable");

/* ---------- 2. index quote packet (28 bytes) ---------- */
t = K._parseMessage(message([packet(28, [
  [0, NIFTY50], [4, 2481020], [8, 2489000], [12, 2470000],
  [16, 2475000], [20, 2460000], [24, 999],
])]))[0];
ok(t.tradable === false, "an index is marked untradable");
ok(near(t.ltp, 24810.20), "index: last level");
ok(near(t.dayHigh, 24890.00) && near(t.dayLow, 24700.00), "index: high and low");
ok(near(t.open, 24750.00) && near(t.prevClose, 24600.00), "index: open and previous close");

/* ---------- 3. index full packet (32 bytes) carries the exchange clock ---------- */
t = K._parseMessage(message([packet(32, [
  [0, NIFTY50], [4, 2481020], [8, 2489000], [12, 2470000],
  [16, 2475000], [20, 2460000], [24, 0], [28, 1787000000],
])]))[0];
ok(t.exchangeTime === 1787000000, "index full: exchange timestamp read");

/* ---------- 4. quote packet (44 bytes) — the field-order trap ---------- */
t = K._parseMessage(message([packet(44, [
  [0, RELIANCE], [4, 141260], [8, 12], [12, 141100], [16, 8412003],
  [20, 5000], [24, 6000], [28, 140000], [32, 142000], [36, 139510], [40, 139800],
])]))[0];
ok(near(t.ltp, 1412.60), "quote: last price");
ok(t.lastQty === 12, "quote: last quantity is a count, NOT divided by 100");
ok(near(t.avgPrice, 1411.00), "quote: average traded price");
ok(t.volume === 8412003, "quote: volume is a count, NOT divided by 100");
ok(t.buyQty === 5000 && t.sellQty === 6000, "quote: buy and sell depth totals");
ok(near(t.open, 1400.00), "quote: open");
ok(near(t.dayHigh, 1420.00), "quote: high");
ok(near(t.dayLow, 1395.10), "quote: low");
ok(near(t.prevClose, 1398.00), "quote: previous close");

/* ---------- 5. full packet (184 bytes) ---------- */
t = K._parseMessage(message([packet(184, [
  [0, RELIANCE], [4, 141260], [8, 12], [12, 141100], [16, 8412003],
  [20, 5000], [24, 6000], [28, 140000], [32, 142000], [36, 139510], [40, 139800],
  [44, 1786999990], [48, 0], [60, 1787000000],
])]))[0];
ok(near(t.ltp, 1412.60) && t.volume === 8412003, "full: the quote fields still line up");
ok(t.lastTradeTime === 1786999990, "full: last trade time");
ok(t.exchangeTime === 1787000000, "full: exchange timestamp at offset 60");

/* ---------- 6. currency segments use a different divisor ---------- */
const CDS = (100 << 8) | 3;                    // segment 3 → divide by 10,000,000
t = K._parseMessage(message([packet(8, [[0, CDS], [4, 873456789]])]))[0];
ok(near(t.ltp, 87.3456789), "currency derivatives scale by 10^7, not 100");

/* ---------- 7. framing ---------- */
const many = K._parseMessage(message([
  packet(8, [[0, RELIANCE], [4, 141260]]),
  packet(28, [[0, NIFTY50], [4, 2481020], [8, 0], [12, 0], [16, 0], [20, 2460000], [24, 0]]),
]));
ok(many.length === 2, "several packets in one message are all read");
ok(many[0].token === RELIANCE && many[1].token === NIFTY50, "packets stay in order");
ok(K._parseMessage(new ArrayBuffer(1)).length === 0, "a 1-byte heartbeat yields no ticks");
ok(K._parseMessage(new ArrayBuffer(0)).length === 0, "an empty frame yields no ticks");

// A truncated frame must stop, not read past the end into garbage.
const good = message([packet(44, [[0, RELIANCE], [4, 141260], [40, 139800]])]);
const cut = good.slice(0, 20);
ok(K._parseMessage(cut).length === 0, "a truncated frame is dropped, not misread");

// An unknown packet length is skipped without derailing the packets after it.
const mixed = message([packet(12, [[0, RELIANCE]]), packet(8, [[0, RELIANCE], [4, 141260]])]);
const got = K._parseMessage(mixed);
ok(got.length === 1 && near(got[0].ltp, 1412.60),
   "an unrecognised packet shape is skipped, the next one still parses");

/* ---------- 8. tick → quote, as the tape consumes it ---------- */
K.symbolByToken[RELIANCE] = "RELIANCE";
const q = K._toQuote({ token: RELIANCE, ltp: 1412.60, prevClose: 1398, open: 1400,
                       dayHigh: 1420, dayLow: 1395.1, volume: 8412003,
                       exchangeTime: 1787000000 });
ok(q.symbol === "RELIANCE", "the tick is mapped back to its symbol");
ok(near(q.change, 14.6), "change computed against the previous close");
ok(near(q.pChange, 14.6 / 1398), "percent change is a fraction, matching the HTTP feed");
ok(q.exchange === "Zerodha", "the source is named on every streamed quote");
ok(/IST/.test(q.tickTime), "the exchange timestamp is rendered in IST");

// A close of zero (a freshly listed or halted instrument) must not divide by it.
const q0 = K._toQuote({ token: RELIANCE, ltp: 100, prevClose: 0 });
ok(q0.pChange === null && q0.change === null,
   "a zero previous close yields no change rather than Infinity");
ok(K._toQuote({ token: 999999, ltp: 1 }) === null, "an unmapped token is dropped");

/* ---------- 9. the credential never goes anywhere it should not ---------- */
const src = fs.readFileSync("./public/kite.js", "utf8");
ok(!/localStorage/.test(src), "the access token is never put in localStorage");
ok(/sessionStorage/.test(src), "the access token lives in sessionStorage only");
ok(!/api_secret|API_SECRET/.test(src), "the API secret appears nowhere in browser code");
ok(!/place_order|placeOrder|\/orders/.test(src), "the streaming client cannot place orders");
const cb = fs.readFileSync("./netlify/functions/kite-callback.mjs", "utf8");
ok(/#kite=/.test(cb), "the token is returned in the URL fragment, not a query string");
ok(!/setItem|blob|getStore/.test(cb), "the server persists no broker token");

console.log("\n" + (fail ? fail + " FAILED" : "all checks passed") + " (" + pass + " passed)");
process.exit(fail ? 1 : 0);
