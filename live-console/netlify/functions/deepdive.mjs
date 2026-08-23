// GET /api/deepdive?symbol=RELIANCE
// Full financial history for one company: profit & loss, balance sheet, cash
// flow, ratios and shareholding, as year-by-year series — the raw material for
// the 360° analysis. Source is the company's public screener.in page.

import { browserHeaders, jsonResponse, parseTable, section, stripTags } from "./_lib.mjs";

function tableToSeries(table, wanted) {
  if (!table) return null;
  const out = { periods: table.headers.slice(1), rows: {} };
  table.rows.forEach((r) => {
    const key = r.label.replace(/\s+/g, " ").trim();
    out.rows[key] = r.values;
  });
  if (wanted) {
    const filtered = {};
    Object.keys(out.rows).forEach((k) => {
      if (wanted.some((w) => k.toLowerCase().includes(w))) filtered[k] = out.rows[k];
    });
    out.rows = Object.keys(filtered).length ? filtered : out.rows;
  }
  return out;
}

function bullets(html, cls) {
  const block = html.match(new RegExp(`<div[^>]*class=["'][^"']*${cls}[^"']*["'][\\s\\S]*?<\\/div>`, "i"));
  if (!block) return [];
  return [...block[0].matchAll(/<li[^>]*>([\s\S]*?)<\/li>/gi)]
    .map((m) => stripTags(m[1])).filter(Boolean).slice(0, 8);
}

export default async (req) => {
  const url = new URL(req.url);
  const symbol = (url.searchParams.get("symbol") || "").toUpperCase().trim();
  if (!/^[A-Z0-9&.-]{1,20}$/.test(symbol)) {
    return jsonResponse({ error: "bad symbol" }, { status: 400, maxAge: 60 });
  }

  let html = null, used = null;
  for (const path of [`${symbol}/consolidated/`, `${symbol}/`]) {
    try {
      const r = await fetch(`https://www.screener.in/company/${path}`, {
        headers: browserHeaders({ Referer: "https://www.screener.in/" }),
      });
      if (r.ok) { html = await r.text(); used = path; break; }
    } catch { /* next */ }
  }
  if (!html) {
    return jsonResponse({
      symbol, error: "financials unavailable",
      hint: "The financial source did not answer from this server. Ratios from the " +
            "Fundamentals tab may still be present.",
    }, { maxAge: 120 });
  }

  const pl = parseTable(section(html, "profit-loss") || "");
  const bs = parseTable(section(html, "balance-sheet") || "");
  const cf = parseTable(section(html, "cash-flow") || "");
  const ratios = parseTable(section(html, "ratios") || "");
  const shp = parseTable(section(html, "shareholding") || "");
  const quarters = parseTable(section(html, "quarters") || "");

  const about = stripTags((html.match(
    /<div[^>]*class=["'][^"']*company-profile[^"']*["'][\s\S]*?<\/div>/i) || [""])[0]).slice(0, 900);

  // Business description often sits in a "About" paragraph block
  const aboutAlt = stripTags((html.match(
    /<h2[^>]*>\s*About\s*<\/h2>([\s\S]*?)<\/(?:div|section)>/i) || [, ""])[1]).slice(0, 900);

  return jsonResponse({
    symbol,
    name: stripTags((html.match(/<h1[^>]*>([\s\S]*?)<\/h1>/i) || [, symbol])[1]),
    basis: used && used.includes("consolidated") ? "consolidated" : "standalone",
    about: (about || aboutAlt || "").trim() || null,
    pros: bullets(html, "pros"),
    cons: bullets(html, "cons"),
    profitLoss: tableToSeries(pl),
    balanceSheet: tableToSeries(bs),
    cashFlow: tableToSeries(cf),
    ratios: tableToSeries(ratios),
    shareholding: tableToSeries(shp),
    quarters: tableToSeries(quarters),
    documentsUrl: `https://www.screener.in/company/${symbol}/`,
  }, { maxAge: 21600 });
};

export const config = { path: "/api/deepdive" };
