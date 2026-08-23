// GET /api/fundamentals?symbols=RELIANCE,TCS
// Server-side fundamentals via Yahoo quoteSummary. Yahoo now gates this behind a
// cookie+crumb handshake, so we do that here (impossible from a browser). Any
// symbol whose data can't be had comes back with error set — the UI must show a
// gap, never a guess.

const MODULES = "defaultKeyStatistics,financialData,summaryDetail,price";
let cached = { cookie: null, crumb: null, at: 0 };

async function getCrumb() {
  if (cached.crumb && Date.now() - cached.at < 30 * 60 * 1000) return cached;
  const ua = { "User-Agent": "Mozilla/5.0 (advisor-360 personal console)" };
  const seed = await fetch("https://fc.yahoo.com", { headers: ua, redirect: "manual" });
  const setCookie = seed.headers.get("set-cookie") || "";
  const cookie = setCookie.split(",").map((c) => c.split(";")[0].trim())
    .filter(Boolean).join("; ");
  const cr = await fetch("https://query1.finance.yahoo.com/v1/test/getcrumb",
                         { headers: { ...ua, cookie } });
  const crumb = (await cr.text()).trim();
  if (!crumb || crumb.includes("<")) throw new Error("crumb unavailable");
  cached = { cookie, crumb, at: Date.now() };
  return cached;
}

function pick(v) {
  if (v == null) return null;
  if (typeof v === "number") return v;
  if (typeof v === "object" && typeof v.raw === "number") return v.raw;
  return null;
}

async function fetchOne(symbol, auth) {
  const yahoo = symbol.includes(".") ? symbol : symbol + ".NS";
  const url = `https://query2.finance.yahoo.com/v10/finance/quoteSummary/` +
    `${encodeURIComponent(yahoo)}?modules=${MODULES}&crumb=${encodeURIComponent(auth.crumb)}`;
  const resp = await fetch(url, {
    headers: {
      "User-Agent": "Mozilla/5.0 (advisor-360 personal console)",
      cookie: auth.cookie,
    },
  });
  if (!resp.ok) return { symbol, error: `upstream ${resp.status}` };
  const j = await resp.json();
  const r = j?.quoteSummary?.result?.[0];
  if (!r) return { symbol, error: "no fundamentals" };

  const ks = r.defaultKeyStatistics || {};
  const fd = r.financialData || {};
  const sd = r.summaryDetail || {};
  const px = r.price || {};

  return {
    symbol,
    name: px.longName || px.shortName || symbol,
    sector: null,
    marketCap: pick(px.marketCap) ?? pick(sd.marketCap),
    pe: pick(sd.trailingPE),
    forwardPe: pick(sd.forwardPE),
    pb: pick(ks.priceToBook),
    evEbitda: pick(ks.enterpriseToEbitda),
    roe: pick(fd.returnOnEquity),
    roa: pick(fd.returnOnAssets),
    debtToEquity: pick(fd.debtToEquity),
    currentRatio: pick(fd.currentRatio),
    opMargin: pick(fd.operatingMargins),
    netMargin: pick(fd.profitMargins),
    grossMargin: pick(fd.grossMargins),
    revenueGrowth: pick(fd.revenueGrowth),
    earningsGrowth: pick(fd.earningsGrowth),
    freeCashflow: pick(fd.freeCashflow),
    operatingCashflow: pick(fd.operatingCashflow),
    totalDebt: pick(fd.totalDebt),
    totalCash: pick(fd.totalCash),
    dividendYield: pick(sd.dividendYield),
    beta: pick(ks.beta) ?? pick(sd.beta),
    heldByInsiders: pick(ks.heldPercentInsiders),
    heldByInstitutions: pick(ks.heldPercentInstitutions),
  };
}

export default async (req) => {
  const url = new URL(req.url);
  const raw = (url.searchParams.get("symbols") || "").toUpperCase();
  const symbols = raw.split(",").map((s) => s.trim()).filter(Boolean).slice(0, 15);
  if (!symbols.length) return Response.json({ error: "no symbols" }, { status: 400 });
  if (!symbols.every((s) => /^[A-Z0-9&.-]{1,20}$/.test(s))) {
    return Response.json({ error: "bad symbol" }, { status: 400 });
  }
  try {
    const auth = await getCrumb();
    const data = await Promise.all(symbols.map((s) =>
      fetchOne(s, auth).catch((e) => ({ symbol: s, error: e.message }))));
    return Response.json({ fundamentals: data }, {
      headers: {
        "Cache-Control": "public, max-age=3600, stale-while-revalidate=21600",
        "Access-Control-Allow-Origin": "*",
      },
    });
  } catch (e) {
    // Handshake itself failed — report it plainly so the UI shows a gap.
    return Response.json({
      fundamentals: symbols.map((s) => ({ symbol: s, error: "source unavailable" })),
      note: "fundamental source unavailable: " + e.message,
    }, { status: 200, headers: { "Cache-Control": "public, max-age=300" } });
  }
};

export const config = { path: "/api/fundamentals" };
