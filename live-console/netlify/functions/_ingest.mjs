// Fetch daily history and store it. Runs on Netlify, so it uses Netlify's network
// rather than a laptop's — this is the "backfill", living in the cloud.

import { getSeries, logRun, mergeSeries, putSeries, putUniverse } from "./_store.mjs";
import { resolveUniverse, INDEX_SYMBOLS } from "./_universe.mjs";

const UA = { "User-Agent": "Mozilla/5.0 (advisor-360 data layer)" };

/** Daily OHLCV for one symbol. Throws rather than returning partial data. */
export async function fetchSeries(symbol, range = "10y") {
  const yahoo = symbol.startsWith("^") || symbol.includes(".") ? symbol : `${symbol}.NS`;
  const url = `https://query1.finance.yahoo.com/v8/finance/chart/` +
    `${encodeURIComponent(yahoo)}?range=${range}&interval=1d`;
  const resp = await fetch(url, { headers: UA });
  if (!resp.ok) throw new Error(`http ${resp.status}`);
  const result = (await resp.json())?.chart?.result?.[0];
  if (!result?.timestamp?.length) throw new Error("empty chart payload");
  const q = result.indicators?.quote?.[0] ?? {};
  const dates = [], open = [], high = [], low = [], close = [], volume = [];
  result.timestamp.forEach((t, i) => {
    if (q.close?.[i] == null) return;                 // skip holidays / gaps
    dates.push(new Date(t * 1000).toISOString().slice(0, 10));
    open.push(q.open?.[i] ?? null); high.push(q.high?.[i] ?? null);
    low.push(q.low?.[i] ?? null); close.push(q.close[i]);
    volume.push(q.volume?.[i] ?? null);
  });
  if (!close.length) throw new Error("no usable bars");
  return { dates, open, high, low, close, volume };
}

/**
 * Ingest a batch of symbols. Returns a per-symbol result; a symbol that fails is
 * recorded as failed and never written with substituted data.
 */
export async function ingestSymbols(symbols, { range = "10y", merge = false,
                                               concurrency = 4 } = {}) {
  const done = [], failed = [];
  for (let i = 0; i < symbols.length; i += concurrency) {
    const slice = symbols.slice(i, i + concurrency);
    await Promise.all(slice.map(async (symbol) => {
      try {
        const fresh = await fetchSeries(symbol, range);
        const series = merge ? mergeSeries(await getSeries(symbol), fresh) : fresh;
        await putSeries(symbol, series);
        done.push({ symbol, bars: series.dates.length, last: series.dates.at(-1) });
      } catch (err) {
        failed.push({ symbol, error: err.message });
      }
    }));
    // be a polite client of a free source
    if (i + concurrency < symbols.length) await new Promise((r) => setTimeout(r, 250));
  }
  return { done, failed };
}

/** Full run: resolve the universe, store it, then ingest everything. */
export async function runIngest({ range = "10y", merge = false, limit = 0,
                                 trigger = "manual" } = {}) {
  const started = Date.now();
  const uni = await resolveUniverse();
  await putUniverse(uni.symbols, uni.source);

  let symbols = [...INDEX_SYMBOLS, ...uni.symbols];
  if (limit > 0) symbols = symbols.slice(0, limit);

  const { done, failed } = await ingestSymbols(symbols, { range, merge });
  const summary = {
    trigger, range, merge,
    universe_source: uni.source,
    universe_note: uni.note,
    requested: symbols.length,
    stored: done.length,
    failed: failed.length,
    failures: failed.slice(0, 15),
    seconds: Math.round((Date.now() - started) / 1000),
  };
  await logRun(summary);
  return summary;
}
