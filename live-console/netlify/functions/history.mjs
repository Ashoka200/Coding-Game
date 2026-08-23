// GET /api/history?symbol=RELIANCE&range=1y
// Server-side proxy to Yahoo Finance chart API for NSE symbols (.NS) and
// indices (^NSEI). Runs on Netlify's network, so no browser CORS and no
// sandbox restrictions. Response is trimmed to what the console needs.

const ALLOWED_RANGES = new Set(["3mo", "6mo", "1y", "2y", "5y"]);

export default async (req) => {
  const url = new URL(req.url);
  const raw = (url.searchParams.get("symbol") || "").toUpperCase();
  const range = ALLOWED_RANGES.has(url.searchParams.get("range"))
    ? url.searchParams.get("range") : "1y";

  // symbol hygiene: NSE tickers are alphanumeric with & and -, indices start with ^
  if (!/^[\^A-Z0-9&.-]{1,20}$/.test(raw)) {
    return Response.json({ error: "bad symbol" }, { status: 400 });
  }
  const yahooSymbol = raw.startsWith("^") || raw.includes(".") ? raw : raw + ".NS";

  const upstream =
    `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(yahooSymbol)}` +
    `?range=${range}&interval=1d&events=div%2Csplit`;

  try {
    const resp = await fetch(upstream, {
      headers: { "User-Agent": "Mozilla/5.0 (advisor-360 personal console)" },
    });
    if (!resp.ok) {
      return Response.json({ error: `upstream ${resp.status}` }, { status: 502 });
    }
    const data = await resp.json();
    const result = data?.chart?.result?.[0];
    if (!result) {
      return Response.json({ error: "no data for symbol" }, { status: 404 });
    }
    const q = result.indicators?.quote?.[0] ?? {};
    const body = {
      symbol: raw,
      currency: result.meta?.currency,
      last: result.meta?.regularMarketPrice,
      prevClose: result.meta?.chartPreviousClose,
      timestamps: result.timestamp ?? [],
      close: q.close ?? [],
      high: q.high ?? [],
      low: q.low ?? [],
      volume: q.volume ?? [],
    };
    return Response.json(body, {
      headers: {
        // EOD analysis: cache at the edge for 10 min, serve stale while refreshing
        "Cache-Control": "public, max-age=600, stale-while-revalidate=3600",
        "Access-Control-Allow-Origin": "*",
      },
    });
  } catch (e) {
    return Response.json({ error: "fetch failed: " + e.message }, { status: 502 });
  }
};

export const config = { path: "/api/history" };
