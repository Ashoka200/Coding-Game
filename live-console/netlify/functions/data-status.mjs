// GET /api/data-status — what the cloud store actually holds, and how the last
// runs went. This is how you check the backfill without guessing.

import { getRunLog, getSeries, getUniverse, priceStore } from "./_store.mjs";
import { jsonResponse } from "./_lib.mjs";

export default async (req) => {
  const url = new URL(req.url);
  const sample = (url.searchParams.get("symbol") || "").toUpperCase();

  try {
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
    return jsonResponse({
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
