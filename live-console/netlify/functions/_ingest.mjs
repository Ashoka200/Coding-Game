// Fetch daily history and store it. Runs on Netlify, so it uses Netlify's network
// rather than a laptop's — this is the "backfill", living in the cloud.
//
// A full Nifty 500 × 10-year pull is bigger than one function invocation, so the
// work is a RESUMABLE JOB: each run processes symbols until its time budget is
// nearly spent, saves a cursor, and the next run continues from there. Nothing
// is re-fetched needlessly and nothing is silently skipped.

import {
  clearJob, getJob, getSeries, jobIsStale, logRun, mergeSeries,
  putJob, putSeries, putUniverse,
} from "./_store.mjs";
import { resolveUniverse, INDEX_SYMBOLS } from "./_universe.mjs";

const UA = { "User-Agent": "Mozilla/5.0 (advisor-360 data layer)" };
const CONCURRENCY = 4;
const PAUSE_MS = 200;          // polite pacing between batches

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

async function ingestOne(symbol, range, merge) {
  const fresh = await fetchSeries(symbol, range);
  const series = merge ? mergeSeries(await getSeries(symbol), fresh) : fresh;
  await putSeries(symbol, series);
  return { symbol, bars: series.dates.length, last: series.dates.at(-1) };
}

/** Start a job (or return the one already running). */
export async function startJob({ range = "10y", merge = false, limit = 0,
                                 trigger = "manual", force = false } = {}) {
  const existing = await getJob();
  if (existing && !existing.finished_at && !jobIsStale(existing) && !force) {
    return { started: false, reason: "a job is already running", job: existing };
  }
  const uni = await resolveUniverse();
  await putUniverse(uni.symbols, uni.source);
  let symbols = [...INDEX_SYMBOLS, ...uni.symbols];
  if (limit > 0) symbols = symbols.slice(0, limit);

  const job = {
    started_at: new Date().toISOString(), finished_at: null, trigger,
    range, merge, symbols, cursor: 0,
    total: symbols.length, done: 0, failed: [],
    universe_source: uni.source, universe_note: uni.note,
  };
  await putJob(job);
  return { started: true, job };
}

/**
 * Process the job from its cursor until the time budget is nearly spent.
 * Returns { finished, processed, job }.
 */
export async function processJob({ budgetMs = 10 * 60_000 } = {}) {
  const started = Date.now();
  let job = await getJob();
  if (!job) return { finished: true, processed: 0, job: null, reason: "no job" };
  if (job.finished_at) return { finished: true, processed: 0, job, reason: "already finished" };

  let processed = 0;
  while (job.cursor < job.symbols.length) {
    if (Date.now() - started > budgetMs) break;            // hand over to the next run
    const slice = job.symbols.slice(job.cursor, job.cursor + CONCURRENCY);
    const results = await Promise.all(slice.map(async (symbol) => {
      try {
        await ingestOne(symbol, job.range, job.merge);
        return null;
      } catch (err) {
        return { symbol, error: err.message };
      }
    }));
    results.forEach((r) => { if (r) job.failed.push(r); });
    job.cursor += slice.length;
    job.done += slice.length - results.filter(Boolean).length;
    processed += slice.length;
    await putJob(job);                                     // progress survives a crash
    if (job.cursor < job.symbols.length) {
      await new Promise((r) => setTimeout(r, PAUSE_MS));
    }
  }

  const finished = job.cursor >= job.symbols.length;
  if (finished) {
    job.finished_at = new Date().toISOString();
    await putJob(job);
    await logRun({
      trigger: job.trigger, range: job.range, merge: job.merge,
      universe_source: job.universe_source, universe_note: job.universe_note,
      requested: job.total, stored: job.done, failed: job.failed.length,
      failures: job.failed.slice(0, 15),
      seconds: Math.round((Date.now() - new Date(job.started_at).getTime()) / 1000),
    });
  }
  return { finished, processed, job };
}

/** Ask this site to continue the job in a fresh invocation. Fire and forget. */
export async function continueInBackground(siteUrl, token) {
  if (!siteUrl) return false;
  const url = new URL("/api/backfill-background", siteUrl);
  url.searchParams.set("resume", "1");
  if (token) url.searchParams.set("token", token);
  try {
    // Deliberately not awaited to completion — the point is to hand off.
    fetch(url.toString(), { method: "POST" }).catch(() => {});
    return true;
  } catch {
    return false;
  }
}

/** Convenience for small runs: start and drain in one invocation. */
export async function runIngest(opts = {}) {
  await startJob({ ...opts, force: true });
  const { job } = await processJob({ budgetMs: opts.budgetMs ?? 10 * 60_000 });
  return job;
}

export { clearJob };
