// Scheduled, self-healing data maintenance.
//
// Runs hourly, but does almost nothing most of the time. Each run decides:
//
//   store empty      -> start a full backfill (10 years)
//   job in progress  -> continue it from its cursor
//   stale (>20h)     -> top up with a short merge
//   fresh            -> return immediately, touching no upstream
//
// Hourly scheduling is what makes this self-starting: nobody has to visit the
// site or run a command, and a wiped store refills within the hour. The freshness
// check is what keeps it polite — a populated, current store costs one cheap
// metadata read per hour and no upstream requests at all.

import { continueInBackground, processJob, startJob } from "./_ingest.mjs";
import { getJob, getUniverse, jobIsStale, logRun, priceStore } from "./_store.mjs";

const WORK_BUDGET_MS = 8 * 60_000;      // scheduled functions get less room than background
const MIN_HEALTHY_SYMBOLS = 20;
const STALE_AFTER_HOURS = 20;

async function storeState() {
  try {
    const { blobs } = await priceStore().list();
    const count = (blobs || []).length;
    const uni = await getUniverse();
    const storedAt = uni?.stored_at ? new Date(uni.stored_at).getTime() : 0;
    const ageHours = storedAt ? (Date.now() - storedAt) / 3_600_000 : Infinity;
    return { count, ageHours };
  } catch (err) {
    return { count: 0, ageHours: Infinity, error: err.message };
  }
}

export default async () => {
  try {
    const job = await getJob();

    // 1. A job is already running — carry it forward rather than starting again.
    if (job && !job.finished_at && !jobIsStale(job)) {
      const { finished, processed, job: after } = await processJob({
        budgetMs: WORK_BUDGET_MS });
      if (!finished) await continueInBackground(process.env.URL,
                                                process.env.ADVISOR_ADMIN_TOKEN);
      return Response.json({ action: "continued", processed,
                             progress: { done: after.done, total: after.total },
                             finished });
    }

    const state = await storeState();

    // 2. Empty or thin store — fill it. This is the self-starting path.
    if (state.count < MIN_HEALTHY_SYMBOLS) {
      await startJob({ range: "10y", merge: false, trigger: "scheduled-backfill",
                       force: true });
      const { finished, processed, job: after } = await processJob({
        budgetMs: WORK_BUDGET_MS });
      if (!finished) await continueInBackground(process.env.URL,
                                                process.env.ADVISOR_ADMIN_TOKEN);
      return Response.json({ action: "backfill started",
                             reason: `store held ${state.count} symbols`,
                             processed, finished,
                             progress: { done: after.done, total: after.total } });
    }

    // 3. Populated but stale — top up with a short merge.
    if (state.ageHours > STALE_AFTER_HOURS) {
      await startJob({ range: "3mo", merge: true, trigger: "scheduled-topup",
                       force: true });
      const { finished, processed, job: after } = await processJob({
        budgetMs: WORK_BUDGET_MS });
      if (!finished) await continueInBackground(process.env.URL,
                                                process.env.ADVISOR_ADMIN_TOKEN);
      return Response.json({ action: "top-up", processed, finished,
                             progress: { done: after.done, total: after.total } });
    }

    // 4. Fresh — do nothing, and touch no upstream.
    return Response.json({ action: "none",
                           reason: `${state.count} symbols stored, refreshed `
                                   + `${state.ageHours.toFixed(1)}h ago` });
  } catch (err) {
    await logRun({ trigger: "scheduled", fatal: err.message });
    return Response.json({ error: err.message }, { status: 500 });
  }
};

// Hourly, off the hour so this site does not pile onto the top-of-hour crowd.
export const config = { schedule: "17 * * * *" };
