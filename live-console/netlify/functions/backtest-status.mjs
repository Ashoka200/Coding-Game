// GET /api/backtest-status — read the last backtest result.
import { metaStore } from "./_store.mjs";

export default async () => {
  try {
    const r = await metaStore().get("backtest_result", { type: "json" });
    if (!r) {
      return Response.json({
        ok: false,
        state: "never run",
        next: "POST /api/backtest-background to start one. It needs the price "
            + "store filled first — check /api/data-status.",
      }, { headers: { "Cache-Control": "no-store" } });
    }
    return Response.json(r, { headers: { "Cache-Control": "no-store" } });
  } catch (e) {
    return Response.json({ ok: false, error: e.message }, { status: 500 });
  }
};
