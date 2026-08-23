// POST /api/backfill-background — the backfill, running on Netlify.
//
// Background functions get a 15-minute budget. A full Nifty 500 × 10-year pull
// is larger than that, so this processes what it can, saves a cursor, and
// re-invokes itself to continue. Progress is readable at /api/data-status
// throughout — you never have to guess whether it is still working.

import { continueInBackground, processJob, startJob } from "./_ingest.mjs";
import { getJob, jobIsStale, logRun } from "./_store.mjs";

const WORK_BUDGET_MS = 10 * 60_000;     // leave headroom inside the 15-minute limit

export default async (req) => {
  const url = new URL(req.url);
  const token = process.env.ADVISOR_ADMIN_TOKEN;
  if (token) {
    const given = url.searchParams.get("token") ||
      (req.headers.get("authorization") || "").replace(/^Bearer\s+/i, "");
    if (given !== token) return new Response("forbidden", { status: 403 });
  }

  const resuming = url.searchParams.get("resume") === "1";
  const range = url.searchParams.get("range") || "10y";
  const merge = url.searchParams.get("merge") === "1";
  const limit = parseInt(url.searchParams.get("limit") || "0", 10) || 0;
  const trigger = url.searchParams.get("trigger") || (resuming ? "resume" : "manual");

  try {
    if (!resuming) {
      const existing = await getJob();
      const running = existing && !existing.finished_at && !jobIsStale(existing);
      if (running && url.searchParams.get("force") !== "1") {
        return Response.json({
          started: false,
          message: "a backfill is already running; watch /api/data-status",
          progress: { done: existing.done, total: existing.total, cursor: existing.cursor },
        }, { status: 409 });
      }
      await startJob({ range, merge, limit, trigger, force: true });
    }

    const { finished, processed, job } = await processJob({ budgetMs: WORK_BUDGET_MS });

    let handedOff = false;
    if (!finished) {
      handedOff = await continueInBackground(process.env.URL, token);
    }

    return Response.json({
      finished,
      processed_this_run: processed,
      progress: job ? { done: job.done, failed: job.failed.length,
                        cursor: job.cursor, total: job.total } : null,
      universe_source: job?.universe_source,
      universe_note: job?.universe_note,
      continued: handedOff,
      message: finished
        ? "Backfill complete. /api/data-status shows what is stored."
        : handedOff
          ? "Time budget reached; a follow-on run was started to continue."
          : "Time budget reached. Call this endpoint again with ?resume=1 to continue.",
    });
  } catch (err) {
    await logRun({ trigger, fatal: err.message });
    return Response.json({ error: "backfill failed", detail: err.message }, { status: 500 });
  }
};

export const config = { path: "/api/backfill-background" };
