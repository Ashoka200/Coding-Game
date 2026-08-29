// GET /api/us-live?symbols=AAPL,MSFT&index=1
//
// Live US prices, with the same contract as the Indian /api/live: name the
// source, carry the strike time, never cache, and never call anything live that
// is not. Two sources, in order:
//   1. Yahoo v7 batch quote — one request for every symbol asked for, which is
//      what makes polling affordable, behind a cookie+crumb handshake.
//   2. Stooq CSV — keyless, per symbol, and explicitly labelled delayed.
//
// US sessions differ from India's in a way the UI must respect: pre-market and
// after-hours are real trades but thin, and a price struck there is a poor
// guide to the open. Those quotes are returned flagged, never as "the price".

import { browserHeaders, harvestCookies, toNum } from "./_lib.mjs";
import { istFor, usMarketState, usSecondsToNextChange } from "./_us_market.mjs";

const MICRO_CACHE_MS = 2500;
let yauth = { cookie: null, crumb: null, at: 0 };
let cache = { at: 0, bySymbol: null };

const INDEX_ALIAS = {
  "^GSPC": "S&P 500", "^NDX": "Nasdaq 100", "^DJI": "Dow Jones", "^VIX": "VIX",
};

async function yahooCrumb() {
  if (yauth.crumb && Date.now() - yauth.at < 20 * 60 * 1000) return yauth;
  let cookie = "";
  for (const u of ["https://finance.yahoo.com/quote/AAPL/", "https://fc.yahoo.com/"]) {
    try {
      const r = await fetch(u, { headers: browserHeaders(), redirect: "follow" });
      cookie = harvestCookies(r, cookie);
      if (/A1=|A3=/.test(cookie)) break;
    } catch { /* try the next */ }
  }
  if (!cookie) throw new Error("no cookies from Yahoo");
  const cr = await fetch("https://query1.finance.yahoo.com/v1/test/getcrumb",
    { headers: browserHeaders({ cookie, Accept: "text/plain",
                                Referer: "https://finance.yahoo.com/" }) });
  const crumb = (await cr.text()).trim();
  if (!crumb || crumb.length > 24 || crumb.includes("<")) throw new Error("crumb refused");
  yauth = { cookie, crumb, at: Date.now() };
  return yauth;
}

/** One request, every symbol. */
async function yahooBatch(symbols) {
  const { cookie, crumb } = await yahooCrumb();
  const url = "https://query1.finance.yahoo.com/v7/finance/quote" +
    `?symbols=${encodeURIComponent(symbols.join(","))}&crumb=${encodeURIComponent(crumb)}`;
  const r = await fetch(url, { headers: browserHeaders({ cookie,
    Accept: "application/json", Referer: "https://finance.yahoo.com/" }) });
  if (!r.ok) throw new Error(`http ${r.status}`);
  const rows = (await r.json())?.quoteResponse?.result;
  if (!Array.isArray(rows)) throw new Error("unrecognised payload");

  return rows.map((q) => {
    const state = q.marketState;             // PRE | REGULAR | POST | CLOSED
    const extended = state === "PRE" || state === "POST";
    // In extended hours Yahoo keeps regularMarketPrice at the last regular
    // close and puts the live number in a separate field. Taking the wrong one
    // shows a stale price during exactly the hours a price is moving most.
    const ltp = extended
      ? (state === "PRE" ? q.preMarketPrice : q.postMarketPrice) ?? q.regularMarketPrice
      : q.regularMarketPrice;
    const prev = q.regularMarketPreviousClose ?? null;
    const stamp = extended
      ? (state === "PRE" ? q.preMarketTime : q.postMarketTime) ?? q.regularMarketTime
      : q.regularMarketTime;
    return {
      symbol: q.symbol,
      name: q.shortName || q.longName || INDEX_ALIAS[q.symbol] || q.symbol,
      ltp: toNum(ltp),
      prevClose: toNum(prev),
      open: toNum(q.regularMarketOpen),
      dayHigh: toNum(q.regularMarketDayHigh),
      dayLow: toNum(q.regularMarketDayLow),
      change: ltp != null && prev != null ? ltp - prev : null,
      pChange: ltp != null && prev ? ltp / prev - 1 : null,
      volume: toNum(q.regularMarketVolume),
      yearHigh: toNum(q.fiftyTwoWeekHigh),
      yearLow: toNum(q.fiftyTwoWeekLow),
      currency: q.currency || "USD",
      exchange: "Yahoo",
      session: extended ? (state === "PRE" ? "pre-market" : "after hours") : "regular",
      extended,
      tickTime: stamp ? new Date(stamp * 1000).toISOString() : null,
    };
  });
}

/** Keyless, delayed, and honest about it. */
async function stooq(symbol) {
  const s = symbol.replace(/^\^/, "").toLowerCase() + ".us";
  const r = await fetch(`https://stooq.com/q/l/?s=${encodeURIComponent(s)}&f=sd2t2ohlcv&h&e=csv`);
  if (!r.ok) throw new Error(`http ${r.status}`);
  const lines = (await r.text()).trim().split("\n");
  if (lines.length < 2) throw new Error("empty csv");
  const [, sym, date, time, open, high, low, close, vol] = [null, ...lines[1].split(",")];
  const ltp = toNum(close);
  if (ltp == null || String(close).toUpperCase() === "N/D") throw new Error("no price");
  return {
    symbol, ltp, prevClose: null, open: toNum(open),
    dayHigh: toNum(high), dayLow: toNum(low), change: null, pChange: null,
    volume: toNum(vol), currency: "USD", exchange: "Stooq (delayed)", delayed: true,
    session: "regular", extended: false,
    tickTime: date && time ? `${date} ${time} UTC` : null,
  };
}

export default async (req) => {
  const url = new URL(req.url);
  const wanted = (url.searchParams.get("symbols") || "").toUpperCase()
    .split(",").map((s) => s.trim()).filter(Boolean).slice(0, 60);
  const wantIndex = url.searchParams.get("index") === "1";
  const market = usMarketState();
  const diagnostics = [];

  const indexSymbols = wantIndex ? Object.keys(INDEX_ALIAS) : [];
  const ask = [...new Set([...wanted, ...indexSymbols])];
  if (!ask.length) return Response.json({ error: "no symbols" }, { status: 400 });

  let bySymbol = new Map();
  if (Date.now() - cache.at < MICRO_CACHE_MS && cache.bySymbol) {
    bySymbol = cache.bySymbol;
  } else {
    try {
      for (const q of await yahooBatch(ask)) if (q.ltp != null) bySymbol.set(q.symbol, q);
      if (bySymbol.size) cache = { at: Date.now(), bySymbol };
    } catch (e) { diagnostics.push(`Yahoo/batch: ${e.message}`); }
  }

  const missing = wanted.filter((s) => !bySymbol.has(s));
  if (missing.length) {
    const filled = await Promise.allSettled(missing.slice(0, 12).map(stooq));
    filled.forEach((f, i) => {
      if (f.status === "fulfilled") bySymbol.set(f.value.symbol, f.value);
      else diagnostics.push(`Stooq/${missing[i]}: ${f.reason.message}`);
    });
  }

  const quotes = wanted.map((s) => bySymbol.get(s) || { symbol: s, error: "no live price" });
  const indices = indexSymbols.map((s) => {
    const q = bySymbol.get(s);
    return q ? { ...q, symbol: s, name: INDEX_ALIAS[s] } : null;
  }).filter(Boolean);

  return new Response(JSON.stringify({
    quotes,
    indices: wantIndex ? indices : undefined,
    market: {
      ...market,
      feed: market.live ? (bySymbol.size ? "live" : "unavailable") : "closed",
      secondsToNextChange: usSecondsToNextChange(),
      // The owner is in India. A US session time means little without the
      // local time beside it.
      istNow: istFor(),
    },
    servedAt: new Date().toISOString(),
    sources: [...new Set(quotes.map((q) => q.exchange).filter(Boolean))],
    diagnostics: diagnostics.length ? diagnostics : undefined,
  }), {
    headers: {
      "Content-Type": "application/json",
      "Cache-Control": "no-store, no-cache, must-revalidate",
      "Access-Control-Allow-Origin": "*",
    },
  });
};
