// POST/GET /api/backtest-background — run the real backtest on the stored bars.
//
// A background function because this reads several hundred ten-year series out
// of the blob store and runs every signal over all of them; that is minutes of
// work, not the ten seconds a normal function gets.
//
// The honesty that matters here is the trial count. Three signals are run, and
// the deflated Sharpe is told about all three — so a result that only looks
// good because it was the best of three is reported as exactly that.

import { backtest, buildScores, combinationReport, combineSignals,
         deflatedSharpe, shuffleTest, SIGNALS, walkForward } from "./_backtest.mjs";
import { getSeries, getUniverse, metaStore } from "./_store.mjs";

const RESULT_KEY = "backtest_result";
const MAX_SYMBOLS = 500;
const REBALANCE = 21;
const PERIODS_PER_YEAR = 250 / REBALANCE;

async function loadPanel(limit) {
  const universe = await getUniverse();
  const symbols = (universe?.symbols || []).slice(0, limit);
  const prices = {};
  const skipped = [];
  for (const sym of symbols) {
    try {
      const s = await getSeries(sym);
      // Ten years is the point; a name with two is not evidence about a decade
      // and would quietly shorten every window it appears in.
      if (s && Array.isArray(s.close) && s.close.length >= 800) {
        prices[sym] = s.close;
      } else {
        skipped.push({ symbol: sym, bars: s?.close?.length ?? 0 });
      }
    } catch (e) {
      skipped.push({ symbol: sym, error: e.message });
    }
  }
  return { prices, skipped, requested: symbols.length };
}

export default async (req) => {
  const started = Date.now();
  const url = new URL(req.url);
  const limit = Math.min(MAX_SYMBOLS, Number(url.searchParams.get("limit")) || MAX_SYMBOLS);

  const { prices, skipped, requested } = await loadPanel(limit);
  const symbols = Object.keys(prices);
  if (symbols.length < 30) {
    await metaStore().setJSON(RESULT_KEY, {
      ok: false,
      why: `only ${symbols.length} symbols had 800+ daily bars, which is too few `
         + `to backtest a cross-section. Run the backfill first.`,
      requested, skipped: skipped.slice(0, 20), at: new Date().toISOString(),
    });
    return Response.json({ ok: false, symbols: symbols.length });
  }

  // Trim every series to a common length so index t means the same date for
  // every name. Misaligned panels are the quietest way to invent an edge.
  const shortest = Math.min(...symbols.map((s) => prices[s].length));
  for (const s of symbols) prices[s] = prices[s].slice(prices[s].length - shortest);

  const signalKeys = Object.keys(SIGNALS);
  // The combination is a fourth thing tried, and counting it is the difference
  // between honest multiple-testing correction and a flattering one.
  const trials = signalKeys.length + 1;
  const results = [];
  const scoreSets = {};
  const byName = {};

  for (const key of signalKeys) {
    const scores = buildScores(prices, key, REBALANCE);
    scoreSets[key] = scores;
    const rebalances = Object.keys(scores).length;
    if (rebalances < 12) {
      results.push({ signal: key, ok: false,
                     why: `only ${rebalances} rebalances after the warm-up` });
      continue;
    }
    const r = backtest(scores, prices, { topN: 20, rebalanceEvery: REBALANCE });
    const sh = shuffleTest(scores, prices, { topN: 20, rebalanceEvery: REBALANCE }, 24);
    const wf = walkForward(scores, prices, 4, { topN: 20, rebalanceEvery: REBALANCE });
    const ds = deflatedSharpe(r.sharpe, r.periods, trials, PERIODS_PER_YEAR);

    const checks = {
      shuffle: sh.passes,
      deflated: ds.passes,
      consistent: wf.ok ? wf.positiveFolds >= 3 : null,
    };
    const decided = Object.values(checks).filter((v) => v !== null);
    const evidence = decided.length >= 2 && decided.every(Boolean);

    results.push({
      signal: key,
      ok: true,
      label: SIGNALS[key].label,
      note: SIGNALS[key].note,
      periods: r.periods,
      netAnnual: r.netAnnual,
      grossAnnual: r.grossAnnual,
      annualVol: r.annualVol,
      sharpe: r.sharpe,
      maxDrawdown: r.maxDrawdown,
      turnover: r.turnover,
      costDrag: r.costDrag,
      hitRate: r.hitRate,
      skillAboveChance: sh.skillAboveChance,
      shufflePValue: sh.pValue,
      shufflePasses: sh.passes,
      deflatedSharpe: ds.deflated,
      deflatedPasses: ds.passes,
      luckBenchmark: ds.benchmarkAnnualFromLuck,
      foldsPositive: wf.ok ? wf.positiveFolds : null,
      foldsReading: wf.ok ? wf.reading : wf.why,
      verdict: evidence
        ? "this is evidence"
        : "not evidence — " + Object.entries(checks)
            .filter(([, v]) => v === false).map(([k]) => k).join(", "),
    });
    byName[key] = r;
  }

  // What the signals are worth together. The average correlation measured here
  // replaces the 0.35 that has been driving every reachability verdict in this
  // system since it was written.
  let combination = { ok: false, why: "not enough usable signals" };
  const usable = Object.keys(scoreSets).filter((k) => Object.keys(scoreSets[k]).length >= 12);
  if (usable.length >= 2) {
    const combinedScores = combineSignals(...usable.map((k) => scoreSets[k]));
    const cfg = { topN: 20, rebalanceEvery: REBALANCE };
    const rc = Object.keys(combinedScores).length >= 12
      ? backtest(combinedScores, prices, cfg) : null;
    combination = combinationReport(
      Object.fromEntries(usable.map((k) => [k, byName[k]])), rc);
    if (rc) {
      const shc = shuffleTest(combinedScores, prices, cfg, 24);
      const dsc = deflatedSharpe(rc.sharpe, rc.periods, trials, PERIODS_PER_YEAR);
      const wfc = walkForward(combinedScores, prices, 4, cfg);
      combination.combined_run = {
        periods: rc.periods, netAnnual: rc.netAnnual, sharpe: rc.sharpe,
        maxDrawdown: rc.maxDrawdown, turnover: rc.turnover, costDrag: rc.costDrag,
        skillAboveChance: shc.skillAboveChance, shufflePasses: shc.passes,
        deflatedSharpe: dsc.deflated, deflatedPasses: dsc.passes,
        foldsPositive: wfc.ok ? wfc.positiveFolds : null,
        verdict: (shc.passes && dsc.passes && wfc.ok && wfc.positiveFolds >= 3)
          ? "this is evidence" : "not evidence",
      };
    }
    combination.what_this_replaces =
      "Every reachability verdict in this system has been using an assumed "
      + "average signal correlation of 0.35. This is the measured figure.";
  }

  const payload = {
    ok: true,
    at: new Date().toISOString(),
    seconds: Math.round((Date.now() - started) / 1000),
    universe: { requested, used: symbols.length, skipped: skipped.length,
                bars_each: shortest },
    trials_counted: trials,
    combination,
    rebalance_days: REBALANCE,
    costs_round_trip: 0.00422,
    results,
    honesty: "Every signal here was run over the same data and all of them are "
           + "counted in the deflated Sharpe, so a winner that only won because "
           + "three were tried is reported as not evidence.",
  };
  await metaStore().setJSON(RESULT_KEY, payload);
  return Response.json({ ok: true, signals: results.length, seconds: payload.seconds });
};

export const config = { type: "background" };
