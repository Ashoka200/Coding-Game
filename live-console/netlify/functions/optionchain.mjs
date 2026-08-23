// GET /api/optionchain?symbol=NIFTY
// NSE option chain. NSE serves its API only to sessions that have first loaded
// pages (cookie handshake) and it throttles cloud IPs hard, so this walks the
// full browser sequence and tries several endpoint shapes before giving up.
// On failure it says exactly which step failed — the F&O screen then falls back
// to realised-volatility analysis rather than inventing premiums.

import { browserHeaders, harvestCookies, jsonResponse } from "./_lib.mjs";

const INDICES = new Set(["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "NIFTYNXT50"]);

async function nseSession() {
  let cookie = "";
  const steps = [
    "https://www.nseindia.com/",
    "https://www.nseindia.com/option-chain",
  ];
  for (const url of steps) {
    const r = await fetch(url, {
      headers: browserHeaders(cookie ? { cookie, Referer: "https://www.nseindia.com/" } : {}),
      redirect: "follow",
    });
    cookie = harvestCookies(r, cookie);
  }
  if (!cookie) throw new Error("no cookies from nseindia.com");
  return cookie;
}

function apiHeaders(cookie) {
  return {
    "User-Agent": browserHeaders()["User-Agent"],
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-IN,en;q=0.9",
    "Referer": "https://www.nseindia.com/option-chain",
    "X-Requested-With": "XMLHttpRequest",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    cookie,
  };
}

async function tryEndpoints(symbol, cookie) {
  const isIndex = INDICES.has(symbol);
  const urls = isIndex ? [
    `https://www.nseindia.com/api/option-chain-indices?symbol=${symbol}`,
    `https://www.nseindia.com/api/option-chain-v3?type=Indices&symbol=${symbol}`,
  ] : [
    `https://www.nseindia.com/api/option-chain-equities?symbol=${encodeURIComponent(symbol)}`,
    `https://www.nseindia.com/api/option-chain-v3?type=Equity&symbol=${encodeURIComponent(symbol)}`,
  ];
  const errors = [];
  for (const url of urls) {
    try {
      const r = await fetch(url, { headers: apiHeaders(cookie) });
      if (!r.ok) { errors.push(`${r.status} on ${url.split("/api/")[1].split("?")[0]}`); continue; }
      const j = await r.json();
      if (j?.records?.data?.length) return { data: j.records, url };
      if (j?.filtered?.data?.length) return { data: { ...j.records, data: j.filtered.data }, url };
      errors.push("empty payload");
    } catch (e) { errors.push(e.message); }
  }
  throw new Error(errors.join("; "));
}

function summarise(symbol, records, isIndex) {
  const spot = records.underlyingValue;
  const expiries = records.expiryDates || [];
  const near = expiries[0];
  if (!spot || !near) throw new Error("chain missing spot or expiry");

  const rows = (records.data || []).filter((d) => d.expiryDate === near);
  const band = spot * 0.10;
  const strikes = rows
    .filter((d) => Math.abs(d.strikePrice - spot) <= band)
    .map((d) => ({
      strike: d.strikePrice,
      callOI: d.CE?.openInterest ?? null, callChgOI: d.CE?.changeinOpenInterest ?? null,
      callIV: d.CE?.impliedVolatility || null, callLtp: d.CE?.lastPrice ?? null,
      putOI: d.PE?.openInterest ?? null, putChgOI: d.PE?.changeinOpenInterest ?? null,
      putIV: d.PE?.impliedVolatility || null, putLtp: d.PE?.lastPrice ?? null,
    }))
    .sort((a, b) => a.strike - b.strike);
  if (!strikes.length) throw new Error("no strikes near spot");

  const totCall = strikes.reduce((s, r) => s + (r.callOI || 0), 0);
  const totPut = strikes.reduce((s, r) => s + (r.putOI || 0), 0);

  let maxPain = null, best = Infinity;
  strikes.forEach((cand) => {
    let pain = 0;
    strikes.forEach((r) => {
      if (r.strike < cand.strike) pain += (r.callOI || 0) * (cand.strike - r.strike);
      if (r.strike > cand.strike) pain += (r.putOI || 0) * (r.strike - cand.strike);
    });
    if (pain < best) { best = pain; maxPain = cand.strike; }
  });

  const atm = strikes.reduce((a, r) =>
    Math.abs(r.strike - spot) < Math.abs(a.strike - spot) ? r : a, strikes[0]);
  const ivs = [atm.callIV, atm.putIV].filter((v) => v && v > 0);

  // where new positions were added today — the crowd's fresh bet
  const topCallAdd = [...strikes].sort((a, b) => (b.callChgOI || 0) - (a.callChgOI || 0))[0];
  const topPutAdd = [...strikes].sort((a, b) => (b.putChgOI || 0) - (a.putChgOI || 0))[0];

  return {
    symbol, spot, expiry: near, expiries: expiries.slice(0, 4), isIndex,
    atmStrike: atm.strike,
    atmIV: ivs.length ? ivs.reduce((a, b) => a + b, 0) / ivs.length : null,
    pcr: totCall ? +(totPut / totCall).toFixed(2) : null,
    maxPain,
    resistanceStrike: [...strikes].sort((a, b) => (b.callOI || 0) - (a.callOI || 0))[0]?.strike ?? null,
    supportStrike: [...strikes].sort((a, b) => (b.putOI || 0) - (a.putOI || 0))[0]?.strike ?? null,
    callBuildup: topCallAdd ? { strike: topCallAdd.strike, added: topCallAdd.callChgOI } : null,
    putBuildup: topPutAdd ? { strike: topPutAdd.strike, added: topPutAdd.putChgOI } : null,
    strikes,
  };
}

export default async (req) => {
  const url = new URL(req.url);
  const symbol = (url.searchParams.get("symbol") || "NIFTY").toUpperCase();
  if (!/^[A-Z&-]{1,20}$/.test(symbol)) {
    return jsonResponse({ error: "bad symbol" }, { status: 400, maxAge: 60 });
  }
  try {
    const cookie = await nseSession();
    const { data } = await tryEndpoints(symbol, cookie);
    return jsonResponse(summarise(symbol, data, INDICES.has(symbol)), { maxAge: 300 });
  } catch (e) {
    return jsonResponse({
      symbol,
      error: "chain unavailable",
      detail: e.message,
      hint: "NSE blocks most datacentre IPs. Option premiums and IV must be read " +
            "from your broker terminal; the volatility analysis below still holds.",
    }, { maxAge: 120 });
  }
};

export const config = { path: "/api/optionchain" };
