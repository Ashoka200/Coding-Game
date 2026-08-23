// GET /api/ownership?symbol=RELIANCE
// Who owns this, and who has been buying or selling.
//
// Shareholding patterns come from the company page (quarterly disclosures).
// Bulk and block deals are attempted from NSE, which frequently refuses cloud
// IPs — that failure is reported, never filled in.

import { browserHeaders, jsonResponse, parseTable, section, stripTags } from "./_lib.mjs";

async function shareholding(symbol) {
  let html = null;
  for (const p of [`${symbol}/consolidated/`, `${symbol}/`]) {
    const r = await fetch(`https://www.screener.in/company/${p}`,
      { headers: browserHeaders({ Referer: "https://www.screener.in/" }) });
    if (r.ok) { html = await r.text(); break; }
  }
  if (!html) throw new Error("company page unavailable");
  const table = parseTable(section(html, "shareholding") || "");
  if (!table) throw new Error("no shareholding table on the page");
  const rows = {};
  table.rows.forEach((r) => { rows[r.label] = r.values; });
  return { quarters: table.headers.slice(1), rows,
           name: stripTags((html.match(/<h1[^>]*>([\s\S]*?)<\/h1>/i) || [, symbol])[1]) };
}

async function nseDeals(symbol) {
  // NSE serves this only to sessions that have loaded its pages first.
  let cookie = "";
  for (const u of ["https://www.nseindia.com/", "https://www.nseindia.com/companies-listing/corporate-filings-bulk-deals"]) {
    const r = await fetch(u, { headers: browserHeaders(cookie ? { cookie } : {}) });
    const raw = typeof r.headers.getSetCookie === "function"
      ? r.headers.getSetCookie() : [r.headers.get("set-cookie") || ""];
    cookie = raw.filter(Boolean).map((l) => l.split(";")[0]).join("; ") || cookie;
  }
  const to = new Date();
  const from = new Date(to.getTime() - 30 * 86400000);
  const fmt = (d) => `${String(d.getDate()).padStart(2, "0")}-` +
    `${String(d.getMonth() + 1).padStart(2, "0")}-${d.getFullYear()}`;
  const url = `https://www.nseindia.com/api/historical/bulk-deals` +
    `?symbol=${encodeURIComponent(symbol)}&from=${fmt(from)}&to=${fmt(to)}`;
  const r = await fetch(url, {
    headers: { ...browserHeaders({ cookie }), Accept: "application/json",
               Referer: "https://www.nseindia.com/companies-listing/corporate-filings-bulk-deals",
               "X-Requested-With": "XMLHttpRequest" },
  });
  if (!r.ok) throw new Error(`http ${r.status}`);
  const j = await r.json();
  return (j?.data || []).map((d) => ({
    date: d.BD_DT_DATE || d.date, client: d.BD_CLIENT_NAME || d.clientName,
    type: d.BD_BUY_SELL || d.buySell,
    quantity: Number(String(d.BD_QTY_TRD || d.quantity || 0).replace(/,/g, "")),
    price: Number(String(d.BD_TP_WATP || d.price || 0).replace(/,/g, "")),
  }));
}

export default async (req) => {
  const url = new URL(req.url);
  const symbol = (url.searchParams.get("symbol") || "").toUpperCase().trim();
  if (!/^[A-Z0-9&.-]{1,20}$/.test(symbol)) {
    return jsonResponse({ error: "bad symbol" }, { status: 400, maxAge: 60 });
  }

  const out = { symbol, shareholding: null, deals: null, diagnostics: [] };
  try {
    const sh = await shareholding(symbol);
    out.shareholding = sh;
    out.name = sh.name;
  } catch (err) {
    out.diagnostics.push(`shareholding: ${err.message}`);
  }
  try {
    out.deals = await nseDeals(symbol);
  } catch (err) {
    out.diagnostics.push(`bulk deals: ${err.message}`);
  }

  if (!out.shareholding && !out.deals) {
    out.error = "no ownership source answered";
    out.hint = "Shareholding is disclosed quarterly on the exchanges; NSE blocks most " +
               "datacentre IPs for its deals API. Nothing here is estimated.";
  }
  return jsonResponse(out, { maxAge: out.shareholding ? 21600 : 300 });
};

export const config = { path: "/api/ownership" };
