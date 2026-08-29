// GET /api/us-fundamentals?symbols=AAPL,MSFT[&price=AAPL:229.35]
//
// Financial statements from SEC EDGAR, shaped into the same object the India
// side produces so the verdict engine, the scorecard and the charts need no
// idea which market they are looking at.
//
// Two things this returns that the India side cannot: the filing each number
// came from, and the date it was filed. Every figure on the US company page can
// therefore be traced to a specific 10-K — and a figure whose filing is stale
// is reported as stale rather than presented as current.

import { annualSeries, cagr, cikFor, latest, priorTo, secHeaders, TAGS } from "./_sec.mjs";

const num = (x) => (typeof x === "number" && Number.isFinite(x) ? x : null);
const div = (a, b) => (num(a) != null && num(b) != null && b !== 0 ? a / b : null);

async function companyFacts(cik) {
  const r = await fetch(`https://data.sec.gov/api/xbrl/companyfacts/CIK${cik}.json`,
    { headers: secHeaders() });
  if (r.status === 403) throw new Error("SEC refused the request (User-Agent or rate limit)");
  if (r.status === 404) throw new Error("no XBRL facts filed for this company");
  if (!r.ok) throw new Error(`companyfacts http ${r.status}`);
  return r.json();
}

function build(symbol, meta, facts, price) {
  const S = {};
  for (const key of Object.keys(TAGS)) S[key] = annualSeries(facts, TAGS[key]);

  const rev = latest(S.revenue), revPrev = priorTo(S.revenue);
  const ni = latest(S.netIncome), niPrev = priorTo(S.netIncome);
  const op = latest(S.operatingIncome);
  const eq = latest(S.equity);
  const ca = latest(S.currentAssets), cl = latest(S.currentLiabilities);
  const dl = latest(S.debtLong), ds = latest(S.debtShort);
  const int = latest(S.interest);
  const eps = latest(S.eps);
  const sh = latest(S.shares);
  const ocf = latest(S.operatingCash), capex = latest(S.capex);
  const divPaid = latest(S.dividendsPaid);

  const debt = (dl ? dl.value : 0) + (ds ? ds.value : 0);
  const equity = eq ? eq.value : null;
  const shares = sh ? sh.value : null;
  const bookPerShare = div(equity, shares);
  const freeCash = ocf && capex ? ocf.value - Math.abs(capex.value) : null;

  // The most recent filing behind any of these numbers. If it is old, the whole
  // picture is old, and the page should say so rather than imply freshness.
  const filedDates = [rev, ni, eq, ocf].filter(Boolean).map((x) => x.filed).sort();
  const asOfFiled = filedDates.length ? filedDates[filedDates.length - 1] : null;
  const fiscalYear = rev ? rev.year : ni ? ni.year : null;

  const out = {
    symbol,
    source: "SEC EDGAR (XBRL)",
    name: meta.name,
    cik: meta.cik,
    market: "US",
    currency: "USD",

    // the shape the rest of the app already understands
    roe: div(ni?.value, equity),
    roce: div(op?.value, equity != null ? equity + debt : null),
    opMargin: div(op?.value, rev?.value),
    netMargin: div(ni?.value, rev?.value),
    debtToEquity: div(debt, equity),
    interestCover: int && int.value > 0 ? div(op?.value, int.value) : null,
    currentRatio: div(ca?.value, cl?.value),
    revenueGrowth: revPrev && revPrev.value > 0 && rev
      ? rev.value / revPrev.value - 1 : null,
    earningsGrowth: niPrev && niPrev.value > 0 && ni
      ? ni.value / niPrev.value - 1 : null,
    revenueCagr3y: cagr(S.revenue, 3),
    earningsCagr3y: cagr(S.netIncome, 3),

    eps: eps ? eps.value : null,
    bookValue: bookPerShare,
    sharesOutstanding: shares,
    freeCashFlow: freeCash,
    fcfMargin: div(freeCash, rev?.value),
    // Cash conversion is the lie-detector on reported profit: earnings that
    // never become cash are the single most common prelude to a restatement.
    cashConversion: div(ocf?.value, ni?.value),

    // point-in-time provenance — the whole reason for using EDGAR
    fiscalYear,
    asOfFiled,
    filedForm: rev ? rev.form : ni ? ni.form : null,
    filingAgeDays: asOfFiled
      ? Math.round((Date.now() - new Date(asOfFiled)) / 86400000) : null,

    history: buildHistory(S),
  };

  // Price-dependent ratios only when a live price was supplied. Computing them
  // from a stale close is how a P/E quietly goes wrong.
  if (price != null) {
    out.price = price;
    out.marketCap = shares != null ? shares * price : null;
    out.pe = eps && eps.value > 0 ? price / eps.value : null;
    out.pb = bookPerShare && bookPerShare > 0 ? price / bookPerShare : null;
    out.fcfYield = out.marketCap && freeCash != null ? freeCash / out.marketCap : null;
    out.dividendYield = divPaid && out.marketCap
      ? Math.abs(divPaid.value) / out.marketCap : null;
  }
  return out;
}

/** Revenue, profit and cash flow by year — what the bar charts draw. */
function buildHistory(S) {
  const years = new Set();
  ["revenue", "netIncome", "operatingCash"].forEach((k) => {
    (S[k]?.series || []).forEach((r) => years.add(r.year));
  });
  const pick = (k, y) => {
    const hit = (S[k]?.series || []).find((r) => r.year === y);
    return hit ? hit.value : null;
  };
  return [...years].sort((a, b) => a - b).slice(-8).map((y) => ({
    year: y,
    revenue: pick("revenue", y),
    netIncome: pick("netIncome", y),
    operatingCashFlow: pick("operatingCash", y),
  }));
}

export default async (req) => {
  const url = new URL(req.url);
  const symbols = (url.searchParams.get("symbols") || "").toUpperCase()
    .split(",").map((s) => s.trim()).filter(Boolean).slice(0, 8);
  if (!symbols.length) return Response.json({ error: "no symbols" }, { status: 400 });

  // Optional "AAPL:229.35,MSFT:410" so price-dependent ratios use the live price.
  const prices = {};
  (url.searchParams.get("price") || "").split(",").filter(Boolean).forEach((pair) => {
    const [s, p] = pair.split(":");
    const v = Number(p);
    if (s && Number.isFinite(v)) prices[s.trim().toUpperCase()] = v;
  });

  const diagnostics = [];
  const fundamentals = [];
  // Sequential, not parallel: the SEC asks for under 10 requests a second and
  // being a good citizen of a free public API costs nothing here.
  for (const symbol of symbols) {
    try {
      const meta = await cikFor(symbol);
      const facts = await companyFacts(meta.cik);
      fundamentals.push(build(symbol, meta, facts, prices[symbol] ?? null));
    } catch (e) {
      diagnostics.push(`${symbol}: ${e.message}`);
      fundamentals.push({ symbol, error: e.message });
    }
  }

  return Response.json({ fundamentals, diagnostics: diagnostics.length ? diagnostics : undefined }, {
    headers: {
      // Statements change quarterly at most; caching hard is correct and keeps
      // us well inside the SEC's rate limit.
      "Cache-Control": "public, max-age=21600, stale-while-revalidate=86400",
      "Access-Control-Allow-Origin": "*",
    },
  });
};
