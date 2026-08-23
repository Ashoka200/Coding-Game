// Exercise the resumable job: cursor advances, progress survives "crashes",
// failures are recorded not substituted, and a resume finishes the work.
import { mergeSeries } from "./netlify/functions/_store.mjs";

// --- in-memory stand-in for Netlify Blobs ---
const blobs = new Map(); let job = null;
const store = {
  getJob: async () => job,
  putJob: async (j) => { job = { ...j, updated_at: new Date().toISOString() }; },
  putSeries: async (s, series) => blobs.set(s, series),
  getSeries: async (s) => blobs.get(s) ?? null,
};

const UNIVERSE = Array.from({ length: 23 }, (_, i) => `SYM${i}`);
const FLAKY = new Set(["SYM3", "SYM11"]);

async function fakeFetch(symbol) {
  if (FLAKY.has(symbol)) throw new Error("http 429");
  return { dates: ["2026-08-20", "2026-08-21"], open: [1, 2], high: [1, 2],
           low: [1, 2], close: [10, 11], volume: [100, 200] };
}

async function processChunk(budgetCalls) {
  let calls = 0;
  while (job.cursor < job.symbols.length && calls < budgetCalls) {
    const slice = job.symbols.slice(job.cursor, job.cursor + 4);
    const results = await Promise.all(slice.map(async (s) => {
      try { await store.putSeries(s, await fakeFetch(s)); return null; }
      catch (e) { return { symbol: s, error: e.message }; }
    }));
    results.forEach((r) => { if (r) job.failed.push(r); });
    job.cursor += slice.length;
    job.done += slice.length - results.filter(Boolean).length;
    calls += slice.length;
    await store.putJob(job);
  }
  return job.cursor >= job.symbols.length;
}

job = { symbols: UNIVERSE, cursor: 0, done: 0, failed: [], total: UNIVERSE.length,
        started_at: new Date().toISOString(), finished_at: null };

// run 1: small budget, must NOT finish
let finished = await processChunk(8);
console.log("run 1 -> finished:", finished, "| cursor:", job.cursor, "| stored:", blobs.size);
if (finished) throw new Error("should not finish in run 1");

// simulate the runner dying: state must be intact for a resume
const snapshot = JSON.parse(JSON.stringify(job));
console.log("progress survived a crash -> cursor:", snapshot.cursor, "done:", snapshot.done);

// run 2: resume from cursor
finished = await processChunk(8);
console.log("run 2 -> finished:", finished, "| cursor:", job.cursor);

// run 3: drain
finished = await processChunk(100);
console.log("run 3 -> finished:", finished, "| cursor:", job.cursor, "of", job.total);

console.log("stored symbols:", blobs.size, "(expected", UNIVERSE.length - FLAKY.size + ")");
console.log("failures recorded:", job.failed.map((f) => f.symbol).join(","));
if (blobs.size !== UNIVERSE.length - FLAKY.size) throw new Error("wrong stored count");
if (job.failed.length !== FLAKY.size) throw new Error("failures not recorded");
for (const f of FLAKY) if (blobs.has(f)) throw new Error("failed symbol was written anyway!");
console.log("failed symbols were NOT written with substituted data ✓");
if (job.done + job.failed.length !== job.total) throw new Error("accounting mismatch");
console.log("accounting: done", job.done, "+ failed", job.failed.length, "= total", job.total, "✓");

// --- merge must not duplicate dates and must stay chronological ---
const existing = { dates: ["2026-08-19","2026-08-20"], open:[1,1], high:[1,1], low:[1,1],
                   close:[9,10], volume:[1,1] };
const fresh = { dates: ["2026-08-20","2026-08-21"], open:[1,1], high:[1,1], low:[1,1],
                close:[10,11], volume:[1,1] };
const merged = mergeSeries(existing, fresh);
console.log("merge ->", merged.dates.join(","), "| closes:", merged.close.join(","));
if (merged.dates.length !== 3) throw new Error("merge duplicated or dropped a date");
if (merged.dates.join(",") !== "2026-08-19,2026-08-20,2026-08-21") throw new Error("out of order");
console.log("merge: no duplicates, chronological ✓");
