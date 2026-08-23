// GET /api/fundamentals?symbols=RELIANCE,TCS
// Fundamentals with source fallback, because no single free source is reliable
// from a cloud IP:
//   1. screener.in company page (rich, Indian-market native)
//   2. Yahoo quoteSummary (needs a cookie+crumb handshake)
// Every response says which source answered. A symbol that neither source can
// supply comes back with error set — the UI shows a gap, never a guess.

import { browserHeaders, findRow, harvestCookies, jsonResponse, parseTable,
         pctChange, section, stripTags, toNum } from "./_lib.mjs";

const MODULES = "defaultKeyStatistics,financialData,summaryDetail,price";
let yahooAuth = { cookie: null, crumb: null, at: 0 };

/* ---------------- source 1: screener.in ---------------- */

async function screener(symbol) {
  const paths = [
    `https://www.screener.in/company/${symbol}/consolidated/`,
    `https://www.screener.in/company/${symbol}/`,
  ];
  let html = null;
  for (const url of paths) {
    const resp = await fetch(url, { headers: browserHeaders({ Referer: "https://www.screener.in/" }) });
    if (resp.ok) { html = await resp.text(); break; }
  }
  if (!html) throw new Error("screener unreachable");

  const pl = parseTable(section(html, "profit-loss") || "");
  const bs = parseTable(section(html, "balance-sheet") || "");
  const ratios = parseTable(section(html, "ratios") || "");
  if (!pl) throw new Error("no profit-loss table");

  // top ratio strip: "Market Cap ₹ 1,23,456 Cr." / "Stock P/E 24.3" / "ROCE 18%"
  const topText = stripTags((html.match(/<ul[^>]*id=["']top-ratios["'][\s\S]*?<\/ul>/i) || [""])[0]);
  const topVal = (name) => {
    const m = topText.match(new RegExp(name + "\\s*₹?\\s*([0-9.,\\-]+)", "i"));
    return m ? toNum(m[1]) : null;
  };

  const sales = findRow(pl, ["sales", "revenue"]);
  const opProfit = findRow(pl, ["operating profit"]);
  const netProfit = findRow(pl, ["net profit"]);
  const opm = findRow(pl, ["opm %", "opm"]);
  const interest = findRow(pl, ["interest"]);
  const borrowings = findRow(bs, ["borrowings"]);
  const equityCap = findRow(bs, ["equity capital"]);
  const reserves = findRow(bs, ["reserves"]);
  const roeRow = findRow(ratios, ["return on equity", "roe"]);

  const last = (row) => {
    if (!row) return null;
    const v = row.values.filter((x) => x != null);
    return v.length ? v[v.length - 1] : null;
  };

  const netWorth = (last(equityCap) || 0) + (last(reserves) || 0);
  const debt = last(borrowings);
  const pat = last(netProfit);

  return {
    symbol,
    source: "screener.in",
    name: stripTags((html.match(/<h1[^>]*>([\s\S]*?)<\/h1>/i) || [, symbol])[1]),
    marketCap: topVal("Market Cap") ? topVal("Market Cap") * 1e7 : null,   // ₹ Cr → ₹
    pe: topVal("Stock P/E"),
    pb: null,
    roe: roeRow ? last(roeRow) / 100 : (netWorth && pat ? pat / netWorth : null),
    roce: topVal("ROCE") != null ? topVal("ROCE") / 100 : null,
    opMargin: opm ? last(opm) / 100 : null,
    netMargin: pat && last(sales) ? pat / last(sales) : null,
    debtToEquity: netWorth > 0 && debt != null ? debt / netWorth : null,
    interestCover: last(interest) ? (last(opProfit) || 0) / last(interest) : null,
    revenueGrowth: pctChange((sales?.values || []).slice(-4)),
    earningsGrowth: pctChange((netProfit?.values || []).slice(-4)),
    dividendYield: topVal("Dividend Yield") != null ? topVal("Dividend Yield") / 100 : null,
    bookValue: topVal("Book Value"),
    faceValue: topVal("Face Value"),
    highLow: null,
    evEbitda: null,
    currentRatio: null,
    beta: null,
  };
}

/* ---------------- source 2: Yahoo ---------------- */

async function yahooCrumb() {
  if (yahooAuth.crumb && Date.now() - yahooAuth.at < 20 * 60 * 1000) return yahooAuth;
  // Yahoo hands out its consent cookies on the quote page; fc.yahoo.com alone
  // stopped being enough.
  let cookie = "";
  for (const url of ["https://finance.yahoo.com/quote/RELIANCE.NS/",
                     "https://fc.yahoo.com/"]) {
    try {
      const r = await fetch(url, { headers: browserHeaders(), redirect: "follow" });
      cookie = harvestCookies(r, cookie);
      if (cookie.includes("A1") || cookie.includes("A3")) break;
    } catch { /* try the next */ }
  }
  if (!cookie) throw new Error("no yahoo cookies");
  const cr = await fetch("https://query1.finance.yahoo.com/v1/test/getcrumb", {
    headers: browserHeaders({ cookie, Accept: "text/plain", Referer: "https://finance.yahoo.com/" }),
  });
  const crumb = (await cr.text()).trim();
  if (!crumb || crumb.length > 24 || crumb.includes("<")) throw new Error("crumb refused");
  yahooAuth = { cookie, crumb, at: Date.now() };
  return yahooAuth;
}

const pick = (v) => (v == null ? null
  : typeof v === "number" ? v
  : typeof v === "object" && typeof v.raw === "number" ? v.raw : null);

async function yahoo(symbol, auth) {
  const t = symbol.includes(".") ? symbol : symbol + ".NS";
  const url = `https://query2.finance.yahoo.com/v10/finance/quoteSummary/${encodeURIComponent(t)}` +
    `?modules=${MODULES}&crumb=${encodeURIComponent(auth.crumb)}`;
  const resp = await fetch(url, {
    headers: browserHeaders({ cookie: auth.cookie, Accept: "application/json",
                              Referer: "https://finance.yahoo.com/" }),
  });
  if (!resp.ok) throw new Error(`yahoo ${resp.status}`);
  const r = (await resp.json())?.quoteSummary?.result?.[0];
  if (!r) throw new Error("yahoo empty");
  const ks = r.defaultKeyStatistics || {}, fd = r.financialData || {},
        sd = r.summaryDetail || {}, px = r.price || {};
  const de = pick(fd.debtToEquity);
  return {
    symbol, source: "yahoo",
    name: px.longName || px.shortName || symbol,
    marketCap: pick(px.marketCap) ?? pick(sd.marketCap),
    pe: pick(sd.trailingPE), pb: pick(ks.priceToBook),
    evEbitda: pick(ks.enterpriseToEbitda),
    roe: pick(fd.returnOnEquity), roce: null,
    opMargin: pick(fd.operatingMargins), netMargin: pick(fd.profitMargins),
    debtToEquity: de == null ? null : (de > 5 ? de / 100 : de),
    interestCover: null,
    revenueGrowth: pick(fd.revenueGrowth), earningsGrowth: pick(fd.earningsGrowth),
    dividendYield: pick(sd.dividendYield), currentRatio: pick(fd.currentRatio),
    beta: pick(ks.beta) ?? pick(sd.beta), bookValue: pick(ks.bookValue),
    freeCashflow: pick(fd.freeCashflow), operatingCashflow: pick(fd.operatingCashflow),
  };
}

/* ---------------- handler ---------------- */

export default async (req) => {
  const url = new URL(req.url);
  const symbols = (url.searchParams.get("symbols") || "").toUpperCase()
    .split(",").map((s) => s.trim()).filter(Boolean).slice(0, 15);
  if (!symbols.length) return jsonResponse({ error: "no symbols" }, { status: 400, maxAge: 60 });
  if (!symbols.every((s) => /^[A-Z0-9&.-]{1,20}$/.test(s))) {
    return jsonResponse({ error: "bad symbol" }, { status: 400, maxAge: 60 });
  }

  // Yahoo needs one handshake for the whole batch; failure there is not fatal.
  let auth = null;
  try { auth = await yahooCrumb(); } catch { /* screener may still answer */ }

  const out = await Promise.all(symbols.map(async (s) => {
    try { return await screener(s); }
    catch (e1) {
      if (auth) {
        try { return await yahoo(s, auth); }
        catch (e2) { return { symbol: s, error: `screener: ${e1.message}; yahoo: ${e2.message}` }; }
      }
      return { symbol: s, error: `screener: ${e1.message}; yahoo: no handshake` };
    }
  }));

  const ok = out.filter((f) => !f.error);
  return jsonResponse({
    fundamentals: out,
    sources: [...new Set(ok.map((f) => f.source))],
    note: ok.length ? undefined
      : "No fundamental source answered from this server. Prices and trend analysis are unaffected.",
  }, { maxAge: ok.length ? 3600 : 120 });
};

export const config = { path: "/api/fundamentals" };
