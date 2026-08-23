// POST /api/backfill-background  — the backfill, running on Netlify.
//
// Background functions get a 15-minute budget, which is what a multi-year,
// multi-hundred-symbol pull needs. It returns immediately with 202; progress and
// the outcome are readable at /api/data-status.
//
// Guarded by ADVISOR_ADMIN_TOKEN when that variable is set, so a public URL
// cannot be used to hammer the upstream source.

import { runIngest } from "./_ingest.mjs";
import { logRun } from "./_store.mjs";

export default async (req) => {
  const url = new URL(req.url);
  const required = process.env.ADVISOR_ADMIN_TOKEN;
  if (required) {
    const given = url.searchParams.get("token") ||
      (req.headers.get("authorization") || "").replace(/^Bearer\s+/i, "");
    if (given !== required) {
      return new Response("forbidden", { status: 403 });
    }
  }

  const range = url.searchParams.get("range") || "10y";
  const limit = parseInt(url.searchParams.get("limit") || "0", 10) || 0;
  const merge = url.searchParams.get("merge") === "1";

  try {
    const summary = await runIngest({ range, merge, limit, trigger: "manual" });
    return Response.json(summary);
  } catch (err) {
    await logRun({ trigger: "manual", fatal: err.message });
    return Response.json({ error: "backfill failed", detail: err.message }, { status: 500 });
  }
};

export const config = { path: "/api/backfill-background" };
