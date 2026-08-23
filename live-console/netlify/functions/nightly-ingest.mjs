// Scheduled: every weekday evening after the Indian market closes, top up the
// stored history. Runs on Netlify's schedule — no laptop, no cron on your machine.
//
// 13:15 UTC = 18:45 IST, comfortably after the 15:30 IST close and the
// end-of-day data publication.

import { runIngest } from "./_ingest.mjs";
import { logRun } from "./_store.mjs";

export default async () => {
  try {
    // merge:true keeps the stored history and appends only new sessions
    const summary = await runIngest({ range: "3mo", merge: true, trigger: "scheduled" });
    return Response.json(summary);
  } catch (err) {
    await logRun({ trigger: "scheduled", fatal: err.message });
    return Response.json({ error: err.message }, { status: 500 });
  }
};

export const config = { schedule: "15 13 * * 1-5" };
