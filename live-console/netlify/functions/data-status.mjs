// GET /api/data-status — what the cloud store actually holds, and how the last
// runs went. This is how you check the backfill without guessing.

import { maybeAutoStart } from "./_autostart.mjs";
import { getJob, getRunLog, getSeries, getUniverse, jobIsStale, priceStore } from "./_store.mjs";
import { jsonResponse } from "./_lib.mjs";

export default async (req) => {
  const url = new URL(req.url);
  const sample = (url.searchParams.get("symbol") || "").toUpperCase();

  const auto = url.searchParams.get("autostart") === "0"
    ? { triggered: false, reason: "suppressed" }
    : await maybeAutoStart();

  try {
    const job = await getJob();
    const universe = await getUniverse();
    const { blobs } = await priceStore().list();
    const stored = (blobs || []).map((b) => b.key);

    let sampleInfo = null;
    if (sample) {
      const s = await getSeries(sample);
      sampleInfo = s
        ? { symbol: sample, bars: s.count, first: s.first, last: s.last,
            stored_at: s.stored_at }
        : { symbol: sample, stored: false };
    }

    const runs = await getRunLog();
    const running = job && !job.finished_at && !jobIsStale(job);
    return jsonResponse({
      backfill: job ? {
        state: job.finished_at ? "finished" : running ? "running" : "stalled",
        done: job.done, failed: job.failed.length, total: job.total,
        percent: job.total ? Math.round((job.cursor / job.total) * 100) : 0,
        started_at: job.started_at, finished_at: job.finished_at,
        updated_at: job.updated_at, trigger: job.trigger,
        recent_failures: job.failed.slice(-8),
        note: running ? "Working. Call again in a minute to see progress."
          : job.finished_at ? "Complete."
          : "The runner stopped before finishing. POST /api/backfill-background?resume=1 "
            + "to continue from where it left off.",
      } : null,
      autostart: auto,
      stored_symbols: stored.length,
      symbols: stored.slice(0, 400).sort(),
      universe: universe
        ? { count: universe.count, source: universe.source, stored_at: universe.stored_at }
        : null,
      sample: sampleInfo,
      recent_runs: runs.slice(0, 5),
      ready: stored.length > 50,
      note: stored.length > 50
        ? "The cloud store has history. Analysis that needs stored series (breadth, "
          + "backtests, long averages) is available."
        : "The store is empty or thin. Trigger /api/backfill-background to populate it.",
    }, { maxAge: 60 });
  } catch (err) {
    return jsonResponse({ error: "store unreadable", detail: err.message,
                          hint: "Netlify Blobs may not be enabled for this site yet." },
                        { status: 200, maxAge: 30 });
  }
};

export const config = { path: "/api/data-status" };
