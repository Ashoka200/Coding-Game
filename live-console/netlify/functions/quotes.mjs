// GET /api/quotes?symbols=RELIANCE,TCS,NIFTYBEES
// Batch last-price + 1y history summary for the planner, in one round trip.
// Server-side (no CORS, no sandbox limits), edge-cached.

const MAX_SYMBOLS = 25;

async function fetchOne(symbol) {
  const yahoo = symbol.startsWith("^") || symbol.includes(".") ? symbol : symbol + ".NS";
  const url =
    `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(yahoo)}` +
    `?range=1y&interval=1d`;
  const resp = await fetch(url, {
    headers: { "User-Agent": "Mozilla/5.0 (advisor-360 personal console)" },
  });
  if (!resp.ok) return { symbol, error: `upstream ${resp.status}` };
  const data = await resp.json();
  const result = data?.chart?.result?.[0];
  if (!result) return { symbol, error: "no data" };

  const q = result.indicators?.quote?.[0] ?? {};
  const close = (q.close ?? []).filter((x) => x != null);
  const high = (q.high ?? []).filter((x) => x != null);
  const low = (q.low ?? []).filter((x) => x != null);
  if (close.length < 60) return { symbol, error: "insufficient history" };

  // 14-period ATR (Wilder) and 20-day swing low — the stop inputs
  const trs = [];
  for (let i = 1; i < close.length; i++) {
    trs.push(Math.max(high[i] - low[i], Math.abs(high[i] - close[i - 1]),
                      Math.abs(low[i] - close[i - 1])));
  }
  let atr = trs.slice(0, 14).reduce((a, b) => a + b, 0) / 14;
  for (let i = 14; i < trs.length; i++) atr = (atr * 13 + trs[i]) / 14;

  // RSI-14, Wilder smoothing — the real thing, not a range position
  let up = 0, down = 0;
  for (let i = 1; i <= 14 && i < close.length; i++) {
    const d = close[i] - close[i - 1];
    if (d > 0) up += d; else down -= d;
  }
  up /= 14; down /= 14;
  for (let i = 15; i < close.length; i++) {
    const d = close[i] - close[i - 1];
    up = (up * 13 + Math.max(d, 0)) / 14;
    down = (down * 13 + Math.max(-d, 0)) / 14;
  }
  const rsi14 = down === 0 ? 100 : 100 - 100 / (1 + up / down);

  const last = result.meta?.regularMarketPrice ?? close[close.length - 1];
  const sma = (n) => {
    if (close.length < n) return null;
    return close.slice(-n).reduce((a, b) => a + b, 0) / n;
  };
  const sma200 = sma(200);
  const prior200 = close.length >= 221
    ? close.slice(-221, -21).reduce((a, b) => a + b, 0) / 200 : null;

  return {
    symbol,
    last,
    prevClose: close.length > 1 ? close[close.length - 2] : null,
    atr14: atr,
    rsi14,
    swingLow20: Math.min(...low.slice(-20)),
    sma50: sma(50),
    sma200,
    sma200Rising: sma200 != null && prior200 != null ? sma200 > prior200 : null,
    high52: Math.max(...close.slice(-252)),
    mom6m: close.length >= 126 ? close[close.length - 1] / close[close.length - 126] - 1 : null,
  };
}

export default async (req) => {
  const url = new URL(req.url);
  const raw = (url.searchParams.get("symbols") || "").toUpperCase();
  const symbols = raw.split(",").map((s) => s.trim()).filter(Boolean).slice(0, MAX_SYMBOLS);
  if (!symbols.length) return Response.json({ error: "no symbols" }, { status: 400 });
  if (!symbols.every((s) => /^[\^A-Z0-9&.-]{1,20}$/.test(s))) {
    return Response.json({ error: "bad symbol" }, { status: 400 });
  }

  try {
    const quotes = await Promise.all(symbols.map(fetchOne));
    return Response.json({ quotes }, {
      headers: {
        "Cache-Control": "public, max-age=600, stale-while-revalidate=3600",
        "Access-Control-Allow-Origin": "*",
      },
    });
  } catch (e) {
    return Response.json({ error: "fetch failed: " + e.message }, { status: 502 });
  }
};

export const config = { path: "/api/quotes" };
