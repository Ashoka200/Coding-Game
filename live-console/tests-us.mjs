// The US desk: the ET clock across daylight saving, SEC XBRL parsing, and the
// market registry that keeps the two desks from bleeding into each other.
import fs from "fs";
import { usMarketState, usSecondsToNextChange } from "./netlify/functions/_us_market.mjs";
import { annualSeries, cagr, latest } from "./netlify/functions/_sec.mjs";

let pass = 0, fail = 0;
const ok = (c, m) => { console.log((c ? "PASS " : "FAIL ") + m); c ? pass++ : fail++; };
const near = (a, b) => a != null && Math.abs(a - b) < 1e-9;

/* ---------- 1. the clock, on both sides of daylight saving ---------- */
const at = (iso) => usMarketState(new Date(iso));
// 09:30 ET is 14:30 UTC in winter and 13:30 UTC in summer. Getting this wrong
// by an hour twice a year is the classic US market-hours bug.
ok(at("2026-01-14T14:30:00Z").state === "open", "winter: 09:30 ET = 14:30 UTC is open");
ok(at("2026-01-14T14:29:00Z").state === "pre_market", "winter: one minute earlier is pre-market");
ok(at("2026-07-15T13:30:00Z").state === "open", "summer: 09:30 ET = 13:30 UTC is open");
ok(at("2026-07-15T14:30:00Z").state === "open", "summer: 14:30 UTC is mid-session, not the open");
ok(at("2026-01-14T14:30:00Z").zone === "EST" && at("2026-07-15T13:30:00Z").zone === "EDT",
   "the zone label follows daylight saving");
ok(at("2026-07-15T20:01:00Z").state === "after_hours", "16:01 ET is after hours");
ok(at("2026-07-15T20:01:00Z").live === false, "after hours is NOT live");
ok(at("2026-07-15T20:01:00Z").extended === true, "after hours is flagged as extended");
ok(at("2026-07-15T12:00:00Z").state === "pre_market", "08:00 ET is pre-market");
ok(at("2026-07-15T12:00:00Z").live === false, "pre-market is NOT live either");
ok(at("2026-07-18T15:00:00Z").state === "weekend", "Saturday is the weekend");
ok(usSecondsToNextChange(new Date("2026-07-15T13:29:00Z")) === 60, "a minute to the opening bell");

/* ---------- 2. SEC XBRL parsing ---------- */
const facts = (rows) => ({ facts: { "us-gaap": { Revenues: { units: { USD: rows } } } } });
const yr = (fy, val, extra = {}) => ({
  fy, val, form: "10-K", fp: "FY", filed: `${fy + 1}-02-01`,
  start: `${fy}-01-01`, end: `${fy}-12-31`, ...extra,
});

let s = annualSeries(facts([yr(2022, 100), yr(2023, 120), yr(2024, 150)]), ["Revenues"]);
ok(s.series.length === 3 && latest(s).value === 150, "three annual years, newest last");

// A quarterly fact carries the same tag and would silently understate the year.
s = annualSeries(facts([
  yr(2024, 150),
  { fy: 2024, val: 38, form: "10-K", fp: "FY", filed: "2025-02-01",
    start: "2024-01-01", end: "2024-03-31" },
]), ["Revenues"]);
ok(s.series.length === 1 && latest(s).value === 150,
   "a 90-day fact is rejected: a quarter must not be read as a year");

// A 10-Q must never enter an annual series.
s = annualSeries(facts([yr(2024, 150), { fy: 2024, val: 40, form: "10-Q", fp: "Q1",
  filed: "2024-05-01", start: "2024-01-01", end: "2024-03-31" }]), ["Revenues"]);
ok(s.series.length === 1 && latest(s).value === 150, "10-Q filings are excluded");

// An amended filing supersedes the original for the same year.
s = annualSeries(facts([
  yr(2024, 150),
  { fy: 2024, val: 145, form: "10-K/A", fp: "FY", filed: "2025-06-01",
    start: "2024-01-01", end: "2024-12-31" },
]), ["Revenues"]);
ok(latest(s).value === 145 && latest(s).form === "10-K/A",
   "the later amendment wins over the original 10-K");
ok(latest(s).filed === "2025-06-01", "the filing date travels with the number");

// Tag fallback: filers use different names for the same concept.
const alt = { facts: { "us-gaap": {
  RevenueFromContractWithCustomerExcludingAssessedTax: { units: { USD: [yr(2024, 200)] } } } } };
ok(annualSeries(alt, ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax"])
     .tag === "RevenueFromContractWithCustomerExcludingAssessedTax",
   "falls through to the next tag name when the first is absent");
ok(annualSeries(facts([]), ["Revenues"]) === null, "no usable facts yields null, not a guess");

/* ---------- 3. growth arithmetic that refuses nonsense ---------- */
const g = annualSeries(facts([yr(2021, 100), yr(2024, 200)]), ["Revenues"]);
ok(near(cagr(g, 3), Math.pow(2, 1 / 3) - 1), "CAGR across three years");
const loss = annualSeries(facts([yr(2021, -50), yr(2024, -10)]), ["Revenues"]);
ok(cagr(loss, 3) === null,
   "a loss narrowing to a smaller loss is not growth — no rate is produced");
const flip = annualSeries(facts([yr(2021, -20), yr(2024, 80)]), ["Revenues"]);
ok(cagr(flip, 3) === null, "a sign change produces no growth rate rather than nonsense");
ok(cagr(annualSeries(facts([yr(2024, 100)]), ["Revenues"])) === null,
   "one data point cannot imply a trend");

/* ---------- 4. the market registry ---------- */
const store = {};
global.localStorage = { getItem: (k) => store[k] ?? null,
                        setItem: (k, v) => { store[k] = String(v); } };
global.window = {};
new Function(fs.readFileSync("./public/markets.js", "utf8")).call(global);
const M = global.window.ADV_MARKETS;

ok(M.id() === "in", "India is the default desk");
ok(M.money(1234567) === "₹12,34,567", "rupees use lakh grouping");
M.set("us");
ok(M.id() === "us", "the desk switches");
ok(M.money(1234567) === "$1,234,567", "dollars use thousands grouping, not lakhs");
ok(M.holdingsKey() === "holdings:us" , "US holdings are stored separately");
M.set("in");
ok(M.holdingsKey() === "holdings",
   "the India key is unchanged, so existing holdings survive the upgrade");

// Endpoints must not cross markets: a US ticker sent to the Indian feed would
// be silently suffixed .NS and price a different company.
ok(M.get("us").api.quotes("AAPL").includes("market=us"), "US quotes carry the market flag");
ok(!M.get("in").api.quotes("TCS").includes("market=us"), "India quotes do not");
ok(M.get("us").api.live("AAPL").startsWith("/api/us-live"), "the US tape has its own feed");
ok(M.get("us").api.deep === null && M.get("us").api.own === null,
   "engines that do not exist for the US are null, so the page shows a gap");
ok(M.get("in").universe.indexOf("AAPL") === -1 &&
   M.get("us").universe.indexOf("RELIANCE") === -1, "the universes do not overlap");

/* ---------- 5. the US doctrine says the things that change the answer ---------- */
const notes = M.get("us").notes.map((n) => n.k + " " + n.t).join(" ");
ok(/Liberalised Remittance/.test(notes) && /250,000/.test(notes), "LRS cap is stated");
ok(/₹10 lakh/.test(notes) && /20%/.test(notes), "the TCS threshold and rate are stated");
ok(/25%/.test(notes) && /Form 67/.test(notes),
   "dividend withholding and the form that reclaims it are both stated");
ok(/111A does not apply/.test(notes) && /slab/.test(notes),
   "the trap is named: 111A does not cover foreign shares, so STCG is at slab");
ok(/24 months/.test(notes) && /12\.5%/.test(notes), "the long-term threshold and rate");
ok(/Schedule FA/.test(notes), "the disclosure obligation is stated");
ok(/\$25,000/.test(notes), "the pattern-day-trader threshold is stated");
ok(/Tax positions are as understood/.test(M.get("us").disclaimer),
   "and it says plainly that tax law moves and to check with a CA");
ok(M.get("in").notes.length === 0, "the India desk is not given US tax notes");

console.log("\n" + (fail ? fail + " FAILED" : "all checks passed") + " (" + pass + " passed)");
process.exit(fail ? 1 : 0);
