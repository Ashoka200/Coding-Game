// GET /api/optionchain?symbol=NIFTY
// NSE option chain, server-side (NSE needs a cookie handshake and blocks browsers
// by CORS). Returns the near-expiry chain trimmed to strikes around spot, plus
// aggregate positioning. Degrades honestly: on failure the UI falls back to
// volatility-based analysis of the underlying instead of inventing a chain.

const INDICES = new Set(["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY"]);
const UA = {
  "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 " +
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
  "Accept": "application/json, text/plain, */*",
  "Accept-Language": "en-IN,en;q=0.9",
  "Referer": "https://www.nseindia.com/option-chain",
};

async function nseCookie() {
  const r = await fetch("https://www.nseindia.com/option-chain", { headers: UA });
  const sc = r.headers.get("set-cookie") || "";
  return sc.split(",").map((c) => c.split(";")[0].trim()).filter(Boolean).join("; ");
}

export default async (req) => {
  const url = new URL(req.url);
  const symbol = (url.searchParams.get("symbol") || "NIFTY").toUpperCase();
  if (!/^[A-Z&-]{1,20}$/.test(symbol)) {
    return Response.json({ error: "bad symbol" }, { status: 400 });
  }
  const path = INDICES.has(symbol)
    ? `option-chain-indices?symbol=${symbol}`
    : `option-chain-equities?symbol=${encodeURIComponent(symbol)}`;

  try {
    const cookie = await nseCookie();
    const resp = await fetch(`https://www.nseindia.com/api/${path}`,
                             { headers: { ...UA, cookie } });
    if (!resp.ok) throw new Error(`upstream ${resp.status}`);
    const j = await resp.json();
    const records = j?.records;
    const spot = records?.underlyingValue;
    const expiries = records?.expiryDates || [];
    const near = expiries[0];
    if (!spot || !near) throw new Error("empty chain");

    const rows = (records.data || []).filter((d) => d.expiryDate === near);
    // keep strikes within ~10% of spot — the tradeable window
    const band = spot * 0.10;
    const trimmed = rows
      .filter((d) => Math.abs(d.strikePrice - spot) <= band)
      .map((d) => ({
        strike: d.strikePrice,
        callOI: d.CE?.openInterest ?? null,
        callChgOI: d.CE?.changeinOpenInterest ?? null,
        callIV: d.CE?.impliedVolatility ?? null,
        callLtp: d.CE?.lastPrice ?? null,
        putOI: d.PE?.openInterest ?? null,
        putChgOI: d.PE?.changeinOpenInterest ?? null,
        putIV: d.PE?.impliedVolatility ?? null,
        putLtp: d.PE?.lastPrice ?? null,
      }))
      .sort((a, b) => a.strike - b.strike);

    const totCallOI = trimmed.reduce((s, r) => s + (r.callOI || 0), 0);
    const totPutOI = trimmed.reduce((s, r) => s + (r.putOI || 0), 0);
    // max pain: strike where total option writer payout is smallest
    let maxPain = null, best = Infinity;
    trimmed.forEach((cand) => {
      let pain = 0;
      trimmed.forEach((r) => {
        if (r.strike < cand.strike) pain += (r.callOI || 0) * (cand.strike - r.strike);
        if (r.strike > cand.strike) pain += (r.putOI || 0) * (r.strike - cand.strike);
      });
      if (pain < best) { best = pain; maxPain = cand.strike; }
    });
    const atm = trimmed.reduce((a, r) =>
      Math.abs(r.strike - spot) < Math.abs(a.strike - spot) ? r : a, trimmed[0]);

    return Response.json({
      symbol, spot, expiry: near, expiries: expiries.slice(0, 4),
      isIndex: INDICES.has(symbol),
      atmIV: atm ? ((atm.callIV || 0) + (atm.putIV || 0)) / 2 || null : null,
      pcr: totCallOI ? +(totPutOI / totCallOI).toFixed(2) : null,
      maxPain, strikes: trimmed,
    }, {
      headers: {
        "Cache-Control": "public, max-age=300, stale-while-revalidate=1800",
        "Access-Control-Allow-Origin": "*",
      },
    });
  } catch (e) {
    return Response.json(
      { symbol, error: "chain unavailable: " + e.message },
      { status: 200, headers: { "Cache-Control": "public, max-age=120" } });
  }
};

export const config = { path: "/api/optionchain" };
