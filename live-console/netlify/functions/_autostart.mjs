// Self-populating store.
//
// If the store is empty and no job is running, the first request to any data
// endpoint kicks off the backfill in the background. Opening the site is enough
// to start it — and if the store is ever wiped, it refills itself.
//
// The trigger is fire-and-forget: the current request is never delayed, and it
// returns whatever it can from the live path meanwhile.

import { continueInBackground } from "./_ingest.mjs";
import { getJob, jobIsStale, priceStore } from "./_store.mjs";

const MIN_HEALTHY_SYMBOLS = 20;
let lastAttempt = 0;
const COOLDOWN_MS = 5 * 60_000;         // never stampede the trigger

export async function maybeAutoStart() {
  if (Date.now() - lastAttempt < COOLDOWN_MS) return { triggered: false, reason: "cooldown" };
  lastAttempt = Date.now();
  try {
    const job = await getJob();
    if (job && !job.finished_at && !jobIsStale(job)) {
      return { triggered: false, reason: "already running" };
    }
    const { blobs } = await priceStore().list();
    if ((blobs || []).length >= MIN_HEALTHY_SYMBOLS) {
      return { triggered: false, reason: "store already populated" };
    }
    const url = new URL("/api/backfill-background", process.env.URL || "");
    url.searchParams.set("trigger", "auto");
    if (process.env.ADVISOR_ADMIN_TOKEN) {
      url.searchParams.set("token", process.env.ADVISOR_ADMIN_TOKEN);
    }
    fetch(url.toString(), { method: "POST" }).catch(() => {});
    return { triggered: true, reason: "store empty — backfill started" };
  } catch (err) {
    return { triggered: false, reason: `could not check the store: ${err.message}` };
  }
}

export { continueInBackground };
