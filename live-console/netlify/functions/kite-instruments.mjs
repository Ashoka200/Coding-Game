// GET /api/kite-instruments?symbols=RELIANCE,TCS,NIFTY50
//
// Kite subscribes by numeric instrument token, not by symbol, so something has
// to translate. The master list is a ~2MB CSV; fetching it in the browser on
// every load would be worse than the polling it replaces, so the translation
// happens here and only the handful of tokens actually wanted comes back.
//
// This endpoint needs no authentication — Kite publishes the instrument dump
// openly — so it is safe to cache hard. Tokens change only when the exchange
// reissues them, which is a once-in-a-blue-moon event handled by the daily
// cache expiry.

const DUMP = "https://api.kite.trade/instruments/NSE";
const TTL_MS = 12 * 60 * 60 * 1000;

// Our index keys → the tradingsymbol Kite uses. The token values are the
// long-standing published ones and serve only as a fallback if the dump is
// unreachable; the CSV wins whenever it loads.
const INDEX_ALIAS = {
  NIFTY50:      { symbol: "NIFTY 50",      fallback: 256265 },
  BANKNIFTY:    { symbol: "NIFTY BANK",    fallback: 260105 },
  NIFTYNEXT50:  { symbol: "NIFTY NEXT 50", fallback: 270857 },
};

let cache = { at: 0, bySymbol: null };

/** The dump is plain CSV, but names contain commas — so parse fields properly. */
function splitCsvLine(line) {
  const out = []; let cur = "", quoted = false;
  for (let i = 0; i < line.length; i++) {
    const c = line[i];
    if (quoted) {
      if (c === '"' && line[i + 1] === '"') { cur += '"'; i++; }
      else if (c === '"') quoted = false;
      else cur += c;
    } else if (c === '"') quoted = true;
    else if (c === ",") { out.push(cur); cur = ""; }
    else cur += c;
  }
  out.push(cur);
  return out;
}

async function loadDump() {
  if (cache.bySymbol && Date.now() - cache.at < TTL_MS) return cache.bySymbol;
  const r = await fetch(DUMP, { headers: { "User-Agent": "astraveda/1.0" } });
  if (!r.ok) throw new Error(`instrument dump http ${r.status}`);
  const text = await r.text();
  const lines = text.split("\n");
  const head = splitCsvLine(lines[0]);
  const iTok = head.indexOf("instrument_token");
  const iSym = head.indexOf("tradingsymbol");
  const iType = head.indexOf("instrument_type");
  const iSeg = head.indexOf("segment");
  const iName = head.indexOf("name");
  if (iTok < 0 || iSym < 0) throw new Error("dump header changed shape");

  const bySymbol = new Map();
  for (let i = 1; i < lines.length; i++) {
    if (!lines[i]) continue;
    const f = splitCsvLine(lines[i]);
    const seg = f[iSeg], type = f[iType];
    // Cash equities and index levels only. Derivatives are a separate concern
    // and would bloat the map with tens of thousands of expiring contracts.
    if (!(type === "EQ" || seg === "INDICES")) continue;
    const tok = Number(f[iTok]);
    if (!Number.isFinite(tok)) continue;
    bySymbol.set(f[iSym].toUpperCase(), { token: tok, name: f[iName] || f[iSym], segment: seg });
  }
  if (!bySymbol.size) throw new Error("dump parsed to nothing");
  cache = { at: Date.now(), bySymbol };
  return bySymbol;
}

export default async (req) => {
  const url = new URL(req.url);
  const wanted = (url.searchParams.get("symbols") || "").toUpperCase()
    .split(",").map((s) => s.trim()).filter(Boolean).slice(0, 200);
  if (!wanted.length) return Response.json({ error: "no symbols" }, { status: 400 });

  let map = null, warning;
  try { map = await loadDump(); }
  catch (e) { warning = "instrument dump unavailable: " + e.message; }

  const tokens = {}, missing = [];
  for (const s of wanted) {
    const alias = INDEX_ALIAS[s];
    const lookup = alias ? alias.symbol : s;
    const hit = map ? map.get(lookup) : null;
    if (hit) tokens[s] = { token: hit.token, name: hit.name, segment: hit.segment };
    else if (alias) tokens[s] = { token: alias.fallback, name: alias.symbol,
                                  segment: "INDICES", source: "published fallback" };
    else missing.push(s);
  }

  return Response.json({ tokens, missing: missing.length ? missing : undefined, warning }, {
    headers: {
      // public reference data, safe to cache hard
      "Cache-Control": "public, max-age=43200, stale-while-revalidate=86400",
      "Access-Control-Allow-Origin": "*",
    },
  });
};
