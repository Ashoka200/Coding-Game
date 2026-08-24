// GET /api/live?symbols=RELIANCE,TCS&index=1
//
// Live last-traded prices during market hours. Three sources, tried in order,
// and the answer always names which one spoke and how old the tick is.
//
// The design point that makes second-by-second affordable: NSE's
// `equity-stockIndices` endpoint returns EVERY constituent of an index in ONE
// response — around fifty live prices per upstream request. So a page watching
// fifty names costs one call, not fifty. Responses are held in the function
// instance for a couple of seconds so a burst of pollers collapses into a
// single upstream hit.
//
// This endpoint is never edge-cached. A cached live price is a lie with a
// timestamp on it.

import { browserHeaders, harvestCookies, toNum } from "./_lib.mjs";
import { marketState, secondsToNextChange } from "./_market.mjs";

const BUCKETS = [
  "NIFTY 50", "NIFTY NEXT 50", "NIFTY MIDCAP 100", "SECURITIES IN F&O",
];
const MICRO_CACHE_MS = 2500;      // collapse concurrent pollers
const SESSION_TTL_MS = 8 * 60000; // NSE cookies go stale quickly

let session = { cookie: null, at: 0 };
let cache = { at: 0, bySymbol: new Map(), buckets: [], source: null };

/* ---------------- NSE ---------------- */
async function nseSession() {
  if (session.cookie && Date.now() - session.at < SESSION_TTL_MS) return session.cookie;
  let cookie = "";
  for (const url of ["https://www.nseindia.com/",
                     "https://www.nseindia.com/market-data/live-equity-market"]) {
    const r = await fetch(url, {
      headers: browserHeaders(cookie ? { cookie, Referer: "https://www.nseindia.com/" } : {}),
      redirect: "follow",
    });
    cookie = harvestCookies(r, cookie);
  }
  if (!cookie) throw new Error("nseindia.com issued no cookies");
  session = { cookie, at: Date.now() };
  return cookie;
}

const nseApiHeaders = (cookie) => ({
  "User-Agent": browserHeaders()["User-Agent"],
  "Accept": "application/json, text/plain, */*",
  "Accept-Language": "en-IN,en;q=0.9",
  "Referer": "https://www.nseindia.com/market-data/live-equity-market",
  "X-Requested-With": "XMLHttpRequest",
  "Sec-Fetch-Dest": "empty", "Sec-Fetch-Mode": "cors", "Sec-Fetch-Site": "same-origin",
  cookie,
});

/** One request → every constituent of one index bucket. */
async function nseBucket(bucket, cookie) {
  const url = "https://www.nseindia.com/api/equity-stockIndices?index=" +
    encodeURIComponent(bucket);
  const r = await fetch(url, { headers: nseApiHeaders(cookie) });
  if (!r.ok) throw new Error(`http ${r.status}`);
  const j = await r.json();
  if (!Array.isArray(j?.data)) throw new Error("unrecognised payload");

  const out = [];
  for (const row of j.data) {
    const sym = String(row.symbol || "").toUpperCase();
    if (!sym || sym.includes(" ")) continue;         // the index row itself
    const ltp = toNum(row.lastPrice);
    if (ltp == null) continue;
    out.push([sym, {
      symbol: sym,
      ltp,
      prevClose: toNum(row.previousClose),
      open: toNum(row.open),
      dayHigh: toNum(row.dayHigh),
      dayLow: toNum(row.dayLow),
      change: toNum(row.change),
      pChange: toNum(row.pChange) != null ? toNum(row.pChange) / 100 : null,
      volume: toNum(row.totalTradedVolume),
      valueCr: toNum(row.totalTradedValue),
      yearHigh: toNum(row.yearHigh),
      yearLow: toNum(row.yearLow),
      exchange: "NSE",
      tickTime: row.lastUpdateTime || j.timestamp || null,
    }]);
  }
  if (!out.length) throw new Error("payload had no priced rows");
  return { rows: out, stamp: j.timestamp || null };
}

/* ---------------- BSE (per symbol, the fallback) ---------------- */
const BSE_CODE = {
  RELIANCE:500325, TCS:532540, HDFCBANK:500180, ICICIBANK:532174, INFY:500209,
  LT:500510, BHARTIARTL:532454, ITC:500875, SBIN:500112, TITAN:500114,
  SUNPHARMA:524715, AXISBANK:532215, MARUTI:532500, ASIANPAINT:500820,
  BAJFINANCE:500034, HCLTECH:532281, ULTRACEMCO:532538, NESTLEIND:500790,
  KOTAKBANK:500247, TATAMOTORS:500570, TATASTEEL:500470, JSWSTEEL:500228,
  WIPRO:507685, DRREDDY:500124, CIPLA:500087, HINDUNILVR:500696, ONGC:500312,
  NTPC:532555, POWERGRID:532898, COALINDIA:533278, ADANIPORTS:532921,
  GRASIM:500300, HINDALCO:500440, BRITANNIA:500825, DIVISLAB:532488,
  EICHERMOT:505200, HEROMOTOCO:500182, TECHM:532755, INDUSINDBK:532187,
  SHREECEM:500387, BPCL:500547, IOC:530965, GAIL:532155, VEDL:500295,
  UPL:512070, SRF:503806, PIDILITIND:500331, DABUR:500096, SIEMENS:500550,
  ABB:500002, BEL:500049, LUPIN:500257, AMBUJACEM:500425, TATACHEM:500770,
  BAJAJFINSV:532978, NIFTYBEES:590103, JUNIORBEES:590104,
};

async function bseQuote(symbol) {
  const code = BSE_CODE[symbol];
  if (!code) throw new Error("no BSE scrip code mapped");
  const r = await fetch(
    `https://api.bseindia.com/BseIndiaAPI/api/getScripHeaderData/w` +
    `?Debtflag=&scripcode=${code}&seriesid=`,
    { headers: {
        "User-Agent": browserHeaders()["User-Agent"],
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://www.bseindia.com", "Referer": "https://www.bseindia.com/",
        "Sec-Fetch-Dest": "empty", "Sec-Fetch-Mode": "cors", "Sec-Fetch-Site": "same-site",
      } });
  if (!r.ok) throw new Error(`http ${r.status}`);
  const j = await r.json();
  const c = j?.CurrRate || {};
  const ltp = toNum(c.LTP ?? c.Ltp);
  if (ltp == null) throw new Error("no LTP in payload");
  const prev = toNum(j?.Header?.PrevClose ?? j?.PrevClose);
  return {
    symbol, ltp, prevClose: prev,
    open: toNum(j?.Header?.Open), dayHigh: toNum(j?.Header?.High),
    dayLow: toNum(j?.Header?.Low),
    change: toNum(c.Chg), pChange: toNum(c.PcChg) != null ? toNum(c.PcChg) / 100 : null,
    volume: null, exchange: "BSE", tickTime: c.UpdatedOn || j?.Header?.UpdatedOn || null,
  };
}

/* ---------------- Yahoo (last resort, ~15 min delayed) ---------------- */
async function yahooQuote(symbol) {
  const y = symbol.startsWith("^") || symbol.includes(".") ? symbol : symbol + ".NS";
  const r = await fetch(
    `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(y)}` +
    `?range=1d&interval=1m`,
    { headers: { "User-Agent": browserHeaders()["User-Agent"] } });
  if (!r.ok) throw new Error(`http ${r.status}`);
  const m = (await r.json())?.chart?.result?.[0]?.meta;
  if (!m?.regularMarketPrice) throw new Error("no price in payload");
  const prev = m.chartPreviousClose ?? m.previousClose ?? null;
  return {
    symbol, ltp: m.regularMarketPrice, prevClose: prev,
    open: null, dayHigh: m.regularMarketDayHigh ?? null,
    dayLow: m.regularMarketDayLow ?? null,
    change: prev != null ? m.regularMarketPrice - prev : null,
    pChange: prev ? m.regularMarketPrice / prev - 1 : null,
    volume: m.regularMarketVolume ?? null,
    exchange: "Yahoo (delayed)",
    tickTime: m.regularMarketTime ? new Date(m.regularMarketTime * 1000).toISOString() : null,
    delayed: true,
  };
}

/* ---------------- index level, one call for all indices ---------------- */
async function nseIndices(cookie) {
  const r = await fetch("https://www.nseindia.com/api/allIndices",
    { headers: nseApiHeaders(cookie) });
  if (!r.ok) throw new Error(`http ${r.status}`);
  const j = await r.json();
  const want = { "NIFTY 50": "NIFTY50", "NIFTY BANK": "BANKNIFTY",
                 "NIFTY NEXT 50": "NIFTYNEXT50" };
  const out = [];
  for (const row of j?.data || []) {
    const key = want[String(row.index || "").toUpperCase()];
    if (!key) continue;
    out.push({
      symbol: key, name: row.index,
      ltp: toNum(row.last), prevClose: toNum(row.previousClose),
      change: toNum(row.variation),
      pChange: toNum(row.percentChange) != null ? toNum(row.percentChange) / 100 : null,
      dayHigh: toNum(row.high), dayLow: toNum(row.low),
      exchange: "NSE", tickTime: j.timestamp || null,
    });
  }
  return out;
}

/* ---------------- the handler ---------------- */
export default async (req) => {
  const url = new URL(req.url);
  const wanted = (url.searchParams.get("symbols") || "").toUpperCase()
    .split(",").map((s) => s.trim()).filter(Boolean).slice(0, 60);
  const wantIndex = url.searchParams.get("index") === "1";
  const market = marketState();
  const diagnostics = [];

  // Serve from the micro-cache when it is fresh enough to be indistinguishable
  // from a new fetch. This is the only caching allowed on this path.
  const fresh = Date.now() - cache.at < MICRO_CACHE_MS;
  let bySymbol = fresh ? cache.bySymbol : new Map();
  let indices = fresh ? cache.indices : null;

  if (!fresh) {
    try {
      const cookie = await nseSession();
      // Buckets in order of how much they cover, and stop as soon as everything
      // asked for is priced. For a page watching large caps that is one upstream
      // request for fifty names — which is what makes frequent polling viable at
      // all, and keeps us well inside NSE's tolerance for a single client.
      for (const bucket of BUCKETS) {
        if (wanted.length && wanted.every((s) => bySymbol.has(s))) break;
        try {
          const { rows } = await nseBucket(bucket, cookie);
          for (const [sym, row] of rows) if (!bySymbol.has(sym)) bySymbol.set(sym, row);
        } catch (e) {
          diagnostics.push(`NSE/${bucket}: ${e.message}`);
          if (/http 4|http 5/.test(e.message)) break;   // throttled: stop asking
        }
        if (!wanted.length) break;                      // index-only caller
      }
      if (wantIndex) {
        try { indices = await nseIndices(cookie); }
        catch (e) { diagnostics.push(`NSE/indices: ${e.message}`); }
      }
    } catch (e) {
      diagnostics.push(`NSE/session: ${e.message}`);
    }
    if (bySymbol.size) cache = { at: Date.now(), bySymbol, indices, source: "NSE" };
  }

  // Anything NSE could not supply, ask BSE then Yahoo for — one by one, but
  // only for the gaps, so the common case stays a single upstream request.
  const missing = wanted.filter((s) => !bySymbol.has(s));
  if (missing.length) {
    const filled = await Promise.allSettled(missing.slice(0, 12).map(async (sym) => {
      try { return await bseQuote(sym); }
      catch (e) {
        diagnostics.push(`BSE/${sym}: ${e.message}`);
        try { return await yahooQuote(sym); }
        catch (e2) { diagnostics.push(`Yahoo/${sym}: ${e2.message}`); throw e2; }
      }
    }));
    filled.forEach((f) => { if (f.status === "fulfilled") bySymbol.set(f.value.symbol, f.value); });
  }

  const quotes = wanted.map((s) => bySymbol.get(s) || { symbol: s, error: "no live price" });

  // If the exchange says it is open but its own clock has not moved for a
  // while, the feed is stalled — a holiday, a halt, or an outage. Say so
  // rather than presenting a frozen number as a live one.
  let feed = market.live ? "live" : "closed";
  const stamps = quotes.map((q) => q.tickTime).filter(Boolean);
  if (market.live && !bySymbol.size) feed = "unavailable";

  return new Response(JSON.stringify({
    quotes,
    indices: wantIndex ? (indices || []) : undefined,
    market: { ...market, feed, secondsToNextChange: secondsToNextChange() },
    servedAt: new Date().toISOString(),
    exchangeStamp: stamps[0] || null,
    sources: [...new Set(quotes.map((q) => q.exchange).filter(Boolean))],
    diagnostics: diagnostics.length ? diagnostics : undefined,
  }), {
    headers: {
      "Content-Type": "application/json",
      // never cached: a stored live price is a lie with a timestamp on it
      "Cache-Control": "no-store, no-cache, must-revalidate",
      "Access-Control-Allow-Origin": "*",
    },
  });
};
