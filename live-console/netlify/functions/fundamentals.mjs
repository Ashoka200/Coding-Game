// GET /api/fundamentals?symbols=RELIANCE,TCS
// Three sources tried in order of usefulness. Cloud IPs get blocked by different
// sources on different days, so every attempt is recorded and returned in
// `diagnostics` — a failure you can see is a failure you can fix.
//   1. screener.in   — richest (10y statements behind it)
//   2. BSE API       — exchange source, usually the most permissive
//   3. Yahoo         — cookie+crumb handshake, last resort

import { browserHeaders, findRow, harvestCookies, jsonResponse, parseTable,
         pctChange, section, stripTags, toNum } from "./_lib.mjs";

const diag = [];
const note = (src, sym, msg) => diag.push(`${src}/${sym}: ${msg}`);

/* ---------------- BSE ---------------- */
// BSE keys companies by numeric scrip code, not symbol.
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

const bseHeaders = () => ({
  "User-Agent": browserHeaders()["User-Agent"],
  "Accept": "application/json, text/plain, */*",
  "Accept-Language": "en-US,en;q=0.9",
  "Origin": "https://www.bseindia.com",
  "Referer": "https://www.bseindia.com/",
  "Sec-Fetch-Dest": "empty", "Sec-Fetch-Mode": "cors", "Sec-Fetch-Site": "same-site",
});

// BSE returns numbers as strings, sometimes with commas, sometimes as "-"
const bnum = (v) => (v == null ? null : toNum(String(v)));
const firstOf = (obj, keys) => {
  for (const k of keys) {
    if (obj && obj[k] != null && obj[k] !== "" && obj[k] !== "-") return obj[k];
  }
  return null;
};

async function bse(symbol) {
  const code = BSE_CODE[symbol];
  if (!code) throw new Error("no BSE scrip code mapped");
  const url = `https://api.bseindia.com/BseIndiaAPI/api/ComHeadernew/w` +
    `?quotetype=EQ&scripcode=${code}&seriesid=`;
  const r = await fetch(url, { headers: bseHeaders() });
  if (!r.ok) throw new Error(`http ${r.status}`);
  const j = await r.json();
  const h = Array.isArray(j) ? j[0] : (j.Header ? (Array.isArray(j.Header) ? j.Header[0] : j.Header) : j);
  if (!h || typeof h !== "object") throw new Error("unrecognised payload");

  const pe = bnum(firstOf(h, ["PE", "pe", "PERatio", "Pe"]));
  const pb = bnum(firstOf(h, ["PB", "pb", "PBRatio"]));
  const mcapCr = bnum(firstOf(h, ["MktCapFull", "MarketCapFull", "Mcap", "MktCap"]));
  const eps = bnum(firstOf(h, ["EPS", "eps", "TTMEPS"]));
  const face = bnum(firstOf(h, ["FaceValue", "Face_Value"]));
  const industry = firstOf(h, ["Industry", "IndustryName", "Scrip_Industry"]);
  const name = firstOf(h, ["Comp_Name", "CompanyName", "scrip_name", "Scrip_Name"]) || symbol;
  if (pe == null && pb == null && mcapCr == null) throw new Error("payload had no ratios");

  return {
    symbol, source: "BSE", name: String(name).trim(), sector: industry || null,
    marketCap: mcapCr != null ? mcapCr * 1e7 : null,
    pe, pb, eps, faceValue: face,
    roe: null, roce: null, opMargin: null, netMargin: null, debtToEquity: null,
    interestCover: null, revenueGrowth: null, earningsGrowth: null,
    dividendYield: bnum(firstOf(h, ["DivYield", "DividendYield"])),
    currentRatio: null, beta: null,
  };
}

/* ---------------- screener.in ---------------- */
async function screener(symbol) {
  let html = null;
  for (const p of [`${symbol}/consolidated/`, `${symbol}/`]) {
    const r = await fetch(`https://www.screener.in/company/${p}`,
      { headers: browserHeaders({ Referer: "https://www.screener.in/" }) });
    if (r.ok) { html = await r.text(); break; }
    note("screener", symbol, `http ${r.status}`);
  }
  if (!html) throw new Error("no page");

  const pl = parseTable(section(html, "profit-loss") || "");
  const bs = parseTable(section(html, "balance-sheet") || "");
  const ratios = parseTable(section(html, "ratios") || "");
  if (!pl) throw new Error("no profit-loss table (page shape changed?)");

  const topText = stripTags((html.match(/<ul[^>]*id=["']top-ratios["'][\s\S]*?<\/ul>/i) || [""])[0]);
  const topVal = (n) => {
    const m = topText.match(new RegExp(n + "\\s*₹?\\s*([0-9.,\\-]+)", "i"));
    return m ? toNum(m[1]) : null;
  };
  const last = (row) => {
    if (!row) return null;
    const v = row.values.filter((x) => x != null);
    return v.length ? v[v.length - 1] : null;
  };
  const sales = findRow(pl, ["sales", "revenue"]);
  const opProfit = findRow(pl, ["operating profit"]);
  const netProfit = findRow(pl, ["net profit"]);
  const opm = findRow(pl, ["opm"]);
  const interest = findRow(pl, ["interest"]);
  const borrowings = findRow(bs, ["borrowings"]);
  const equityCap = findRow(bs, ["equity capital"]);
  const reserves = findRow(bs, ["reserves"]);
  const roeRow = findRow(ratios, ["return on equity", "roe"]);
  const netWorth = (last(equityCap) || 0) + (last(reserves) || 0);
  const debt = last(borrowings), pat = last(netProfit);

  return {
    symbol, source: "screener.in",
    name: stripTags((html.match(/<h1[^>]*>([\s\S]*?)<\/h1>/i) || [, symbol])[1]),
    marketCap: topVal("Market Cap") ? topVal("Market Cap") * 1e7 : null,
    pe: topVal("Stock P/E"), pb: null,
    roe: roeRow ? last(roeRow) / 100 : (netWorth && pat ? pat / netWorth : null),
    roce: topVal("ROCE") != null ? topVal("ROCE") / 100 : null,
    opMargin: opm ? last(opm) / 100 : null,
    netMargin: pat && last(sales) ? pat / last(sales) : null,
    debtToEquity: netWorth > 0 && debt != null ? debt / netWorth : null,
    interestCover: last(interest) ? (last(opProfit) || 0) / last(interest) : null,
    revenueGrowth: pctChange((sales?.values || []).slice(-4)),
    earningsGrowth: pctChange((netProfit?.values || []).slice(-4)),
    dividendYield: topVal("Dividend Yield") != null ? topVal("Dividend Yield") / 100 : null,
    bookValue: topVal("Book Value"), evEbitda: null, currentRatio: null, beta: null,
  };
}

/* ---------------- Yahoo ---------------- */
let yauth = { cookie: null, crumb: null, at: 0 };
async function yahooCrumb() {
  if (yauth.crumb && Date.now() - yauth.at < 20 * 60 * 1000) return yauth;
  let cookie = "";
  for (const u of ["https://finance.yahoo.com/quote/RELIANCE.NS/", "https://fc.yahoo.com/"]) {
    try {
      const r = await fetch(u, { headers: browserHeaders(), redirect: "follow" });
      cookie = harvestCookies(r, cookie);
      if (/A1=|A3=/.test(cookie)) break;
    } catch (e) { note("yahoo", "cookie", e.message); }
  }
  if (!cookie) throw new Error("no cookies");
  const cr = await fetch("https://query1.finance.yahoo.com/v1/test/getcrumb",
    { headers: browserHeaders({ cookie, Accept: "text/plain",
                                Referer: "https://finance.yahoo.com/" }) });
  const crumb = (await cr.text()).trim();
  if (!crumb || crumb.length > 24 || crumb.includes("<")) throw new Error("crumb refused");
  yauth = { cookie, crumb, at: Date.now() };
  return yauth;
}
const pick = (v) => (v == null ? null : typeof v === "number" ? v
  : typeof v === "object" && typeof v.raw === "number" ? v.raw : null);

async function yahoo(symbol, auth) {
  const t = symbol.includes(".") ? symbol : symbol + ".NS";
  const r = await fetch(
    `https://query2.finance.yahoo.com/v10/finance/quoteSummary/${encodeURIComponent(t)}` +
    `?modules=defaultKeyStatistics,financialData,summaryDetail,price&crumb=${encodeURIComponent(auth.crumb)}`,
    { headers: browserHeaders({ cookie: auth.cookie, Accept: "application/json",
                                Referer: "https://finance.yahoo.com/" }) });
  if (!r.ok) throw new Error(`http ${r.status}`);
  const res = (await r.json())?.quoteSummary?.result?.[0];
  if (!res) throw new Error("empty result");
  const ks = res.defaultKeyStatistics || {}, fd = res.financialData || {},
        sd = res.summaryDetail || {}, px = res.price || {};
  const de = pick(fd.debtToEquity);
  return {
    symbol, source: "yahoo", name: px.longName || px.shortName || symbol,
    marketCap: pick(px.marketCap) ?? pick(sd.marketCap),
    pe: pick(sd.trailingPE), pb: pick(ks.priceToBook),
    evEbitda: pick(ks.enterpriseToEbitda), roe: pick(fd.returnOnEquity), roce: null,
    opMargin: pick(fd.operatingMargins), netMargin: pick(fd.profitMargins),
    debtToEquity: de == null ? null : (de > 5 ? de / 100 : de), interestCover: null,
    revenueGrowth: pick(fd.revenueGrowth), earningsGrowth: pick(fd.earningsGrowth),
    dividendYield: pick(sd.dividendYield), currentRatio: pick(fd.currentRatio),
    beta: pick(ks.beta) ?? pick(sd.beta),
    freeCashflow: pick(fd.freeCashflow), operatingCashflow: pick(fd.operatingCashflow),
  };
}

/* ---------------- handler ---------------- */
export default async (req) => {
  diag.length = 0;
  const url = new URL(req.url);
  const symbols = (url.searchParams.get("symbols") || "").toUpperCase()
    .split(",").map((s) => s.trim()).filter(Boolean).slice(0, 15);
  if (!symbols.length) return jsonResponse({ error: "no symbols" }, { status: 400, maxAge: 60 });
  if (!symbols.every((s) => /^[A-Z0-9&.-]{1,20}$/.test(s))) {
    return jsonResponse({ error: "bad symbol" }, { status: 400, maxAge: 60 });
  }

  let auth = null;
  try { auth = await yahooCrumb(); }
  catch (e) { note("yahoo", "handshake", e.message); }

  const out = await Promise.all(symbols.map(async (s) => {
    for (const [name, fn] of [["screener", screener], ["bse", bse],
                              ["yahoo", auth ? (x) => yahoo(x, auth) : null]]) {
      if (!fn) continue;
      try {
        const got = await fn(s);
        if (got) return got;
      } catch (e) { note(name, s, e.message); }
    }
    return { symbol: s, error: "no source answered" };
  }));

  const ok = out.filter((f) => !f.error);
  return jsonResponse({
    fundamentals: out,
    sources: [...new Set(ok.map((f) => f.source))],
    diagnostics: diag.slice(0, 30),
    note: ok.length ? undefined
      : "No fundamental source answered from this server. Every attempt and its error " +
        "is listed in diagnostics. Prices, trend and news analysis are unaffected.",
  }, { maxAge: ok.length ? 3600 : 120 });
};

export const config = { path: "/api/fundamentals" };
