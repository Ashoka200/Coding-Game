// The serverless backtest: proved on known worlds, and pinned to the Python
// original so the two implementations cannot quietly drift apart.
import fs from "fs";
import { backtest, buildScores, COSTS, deflatedSharpe, expectedMaxSharpe,
         oneWay, roundTrip, shuffleTest, SIGNALS,
         walkForward } from "./netlify/functions/_backtest.mjs";

let pass = 0, fail = 0;
const ok = (c, m) => { console.log((c ? "PASS " : "FAIL ") + m); c ? pass++ : fail++; };
const near = (a, b, tol = 1e-9) => Math.abs(a - b) < tol;

/* ---------- 1. parity with the tested Python implementation ---------- */
const fx = JSON.parse(fs.readFileSync("./tests-backtest-fixture.json", "utf8"));
const scores = Object.fromEntries(
  Object.entries(fx.scores).map(([k, v]) => [Number(k), v]));
const got = backtest(scores, fx.prices);

for (const [k, want] of Object.entries(fx.expected)) {
  ok(near(got[k], want, 1e-9),
     `parity with Python on ${k}: ${got[k]} vs ${want}`);
}

/* ---------- 2. the cost model ---------- */
ok(near(COSTS.sttBuy + COSTS.sttSell, 0.002), "securities transaction tax on both legs");
ok(oneWay(true) > oneWay(false), "stamp duty is buy-side only");
ok(roundTrip() > 0.003 && roundTrip() < 0.006,
   `a delivery round trip lands near 0.42% (${(roundTrip() * 100).toFixed(3)}%)`);

/* ---------- 3. synthetic worlds ---------- */
function world({ edge = 0, symbols = 50, days = 1300, seed = 1, drift = 0.0002 }) {
  let a = seed >>> 0;
  const rnd = () => { a = (a * 1664525 + 1013904223) >>> 0; return a / 4294967296; };
  const gauss = () => {
    let u = 0, v = 0;
    while (u === 0) u = rnd();
    while (v === 0) v = rnd();
    return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
  };
  const prices = {}, quality = {};
  for (let i = 0; i < symbols; i++) { prices["S" + i] = [100]; quality["S" + i] = gauss(); }
  for (let d = 0; d < days; d++) {
    for (const s of Object.keys(prices)) {
      const mu = drift + edge * quality[s] / 21;
      prices[s].push(prices[s][prices[s].length - 1] * Math.exp(mu + 0.02 * gauss()));
    }
  }
  const sc = {};
  for (let t = 60; t < days - 21; t += 21) {
    const row = {};
    for (const s of Object.keys(prices)) {
      row[s] = edge ? quality[s] + 0.3 * gauss() : gauss();
    }
    sc[t] = row;
  }
  return { prices, scores: sc };
}

const noise = world({ edge: 0, seed: 7 });
const rNoise = backtest(noise.scores, noise.prices);
const sNoise = shuffleTest(noise.scores, noise.prices, {}, 24, 7);
ok(rNoise.sharpe > 0.5,
   `a noise strategy still posts a respectable Sharpe (${rNoise.sharpe.toFixed(2)}) — that is the market`);
ok(Math.abs(sNoise.skillAboveChance) < 1.0,
   "but its skill above a shuffled portfolio is near zero");

const planted = world({ edge: 0.12, seed: 3 });
const rEdge = backtest(planted.scores, planted.prices);
const sEdge = shuffleTest(planted.scores, planted.prices, {}, 24, 3);
ok(rEdge.netAnnual > 0.05, "a planted edge is recovered");
ok(sEdge.passes && sEdge.skillAboveChance > 0.5,
   "and the shuffle test confirms the ranking is doing the work");

/* ---------- 4. the permutation-count guard ---------- */
const thin = shuffleTest(planted.scores, planted.prices, {}, 15, 3);
ok(!thin.runsSufficient && /permutations/.test(thin.reading),
   "too few permutations is reported, not silently failed");
ok(near(thin.minAchievableP, 1 / 16), "the floor on a permutation p-value is stated");

/* ---------- 5. mechanics ---------- */
ok(backtest({}, {}).periods === 0, "an empty panel returns zero rather than throwing");
const missing = { ...noise.scores };
for (const t of Object.keys(missing)) missing[t] = { ...missing[t], GHOST: 99 };
const withGhost = backtest(missing, { ...noise.prices, GHOST: new Array(100).fill(100) });
ok(withGhost.periods > 0, "a symbol whose series ends early is skipped, not fatal");

const w = walkForward(planted.scores, planted.prices, 4);
ok(w.ok && w.folds.length === 4, "walk-forward splits into folds");
ok(w.positiveFolds >= 3, "a real edge shows up in most folds");
ok(walkForward(noise.scores, noise.prices, 40).ok === false,
   "too short a history for the folds asked for is refused");

/* ---------- 6. the signals ---------- */
ok(Object.keys(SIGNALS).length >= 3, "more than one signal, so the search can be counted");
const built = buildScores(planted.prices, "momentum_12_1");
const firstT = Math.min(...Object.keys(built).map(Number));
ok(firstT >= 260, "momentum scores start only after a full formation window");
ok(SIGNALS.low_volatility.score(planted.prices.S0, 400) < 0,
   "low volatility is negated so that calmer ranks higher");
ok(SIGNALS.momentum_12_1.score(planted.prices.S0, 100) === null,
   "a score is null rather than guessed when history is too short");

/* ---------- 7. paying for the search ---------- */
ok(expectedMaxSharpe(1) === 0, "one trial has no luck benchmark to beat");
ok(expectedMaxSharpe(1000) > expectedMaxSharpe(10),
   "the more variants tried, the higher the bar luck alone clears");
const once = deflatedSharpe(1.5, 120, 1, 12);
const many = deflatedSharpe(1.5, 120, 2000, 12);
ok(once.passes && !many.passes,
   "the same backtest stops being evidence once the search is admitted");
ok(many.benchmarkAnnualFromLuck > once.benchmarkAnnualFromLuck,
   "and the luck benchmark rises with the count");

console.log("\n" + (fail ? fail + " FAILED" : "all checks passed") + ` (${pass} passed)`);
process.exit(fail ? 1 : 0);
