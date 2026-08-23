// Persistent storage for the cloud data layer.
//
// The advisor needs stored history — you cannot compute a 200-day average, market
// breadth or a backtest from a single snapshot. Netlify Blobs gives the functions
// a durable store, so the "backfill" runs on Netlify's own network (which can
// reach the data sources) instead of on someone's laptop.

import { getStore } from "@netlify/blobs";

const PRICES = "prices";     // one blob per symbol: daily OHLC series
const META = "meta";         // universe list, run logs

export function priceStore() {
  return getStore({ name: PRICES, consistency: "strong" });
}
export function metaStore() {
  return getStore({ name: META, consistency: "strong" });
}

/** Store a symbol's daily series. Series are stored whole and replaced whole. */
export async function putSeries(symbol, series) {
  await priceStore().setJSON(symbol, {
    symbol,
    stored_at: new Date().toISOString(),
    count: series.dates.length,
    first: series.dates[0] ?? null,
    last: series.dates[series.dates.length - 1] ?? null,
    ...series,
  });
}

export async function getSeries(symbol) {
  try {
    return await priceStore().get(symbol, { type: "json" });
  } catch {
    return null;
  }
}

/** Merge new daily bars into a stored series without duplicating dates. */
export function mergeSeries(existing, fresh) {
  if (!existing || !existing.dates?.length) return fresh;
  const seen = new Set(existing.dates);
  const out = {
    dates: existing.dates.slice(), open: existing.open.slice(),
    high: existing.high.slice(), low: existing.low.slice(),
    close: existing.close.slice(), volume: existing.volume.slice(),
  };
  fresh.dates.forEach((d, i) => {
    if (seen.has(d)) return;
    out.dates.push(d); out.open.push(fresh.open[i]); out.high.push(fresh.high[i]);
    out.low.push(fresh.low[i]); out.close.push(fresh.close[i]);
    out.volume.push(fresh.volume[i]);
  });
  // keep chronological
  const order = out.dates.map((d, i) => i).sort((a, b) =>
    out.dates[a] < out.dates[b] ? -1 : out.dates[a] > out.dates[b] ? 1 : 0);
  return {
    dates: order.map((i) => out.dates[i]), open: order.map((i) => out.open[i]),
    high: order.map((i) => out.high[i]), low: order.map((i) => out.low[i]),
    close: order.map((i) => out.close[i]), volume: order.map((i) => out.volume[i]),
  };
}

export async function putUniverse(symbols, source) {
  await metaStore().setJSON("universe", {
    symbols, source, stored_at: new Date().toISOString(), count: symbols.length,
  });
}

export async function getUniverse() {
  try {
    return await metaStore().get("universe", { type: "json" });
  } catch {
    return null;
  }
}

/* ---- resumable job state ----
   A full Nifty 500 pull is larger than one function invocation, so the work is a
   job with a cursor: each run processes a slice, saves progress, and the next
   run resumes exactly where it stopped. Nothing is re-fetched needlessly and
   nothing is silently skipped. */

export async function getJob() {
  try {
    return await metaStore().get("job", { type: "json" });
  } catch {
    return null;
  }
}

export async function putJob(job) {
  await metaStore().setJSON("job", { ...job, updated_at: new Date().toISOString() });
}

export async function clearJob() {
  try { await metaStore().delete("job"); } catch { /* already gone */ }
}

/** A job is stale (its runner died) if nothing has updated it for a while. */
export function jobIsStale(job, minutes = 20) {
  if (!job?.updated_at) return true;
  return Date.now() - new Date(job.updated_at).getTime() > minutes * 60_000;
}

export async function logRun(entry) {
  const store = metaStore();
  let log = [];
  try {
    log = (await store.get("runlog", { type: "json" })) || [];
  } catch { /* first run */ }
  log.unshift({ at: new Date().toISOString(), ...entry });
  await store.setJSON("runlog", log.slice(0, 40));
}

export async function getRunLog() {
  try {
    return (await metaStore().get("runlog", { type: "json" })) || [];
  } catch {
    return [];
  }
}
