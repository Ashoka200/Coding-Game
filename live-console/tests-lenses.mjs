// The browser port of the investor lenses and the failure checks, pinned to the
// Python original. Three companies, every score, every criterion, every verdict.
import fs from "fs";

let pass = 0, fail = 0;
const ok = (c, m) => { console.log((c ? "PASS " : "FAIL ") + m); c ? pass++ : fail++; };
const near = (a, b, tol = 1e-12) =>
  (a === null && b === null) || (a != null && b != null && Math.abs(a - b) < tol);

global.window = {};
new Function(fs.readFileSync("./public/lenses.js", "utf8")).call(global);
const L = global.window.ADV_LENSES;
const fx = JSON.parse(fs.readFileSync("./tests-lenses-fixture.json", "utf8"));

for (const [name, want] of Object.entries(fx.cases)) {
  const facts = want.facts;

  ok(near(L.derive(facts).peg, want.peg, 1e-12), `${name}: PEG matches Python`);

  const got = L.applyAll(facts);
  ok(got.length === want.lenses.length, `${name}: same number of lenses`);

  want.lenses.forEach((w, i) => {
    const g = got[i];
    ok(g.author === w.author, `${name}: lens ${i} is ${w.author}`);
    ok(near(g.score, w.score, 1e-12),
       `${name}/${w.author}: score ${g.score} vs ${w.score}`);
    ok(g.judged === w.judged && g.unknown === w.unknown,
       `${name}/${w.author}: judged ${g.judged}, unknown ${g.unknown}`);
    ok(g.verdict === w.verdict, `${name}/${w.author}: verdict wording identical`);

    const bad = w.criteria.filter((wc, j) =>
      got[i].criteria[j].passed !== wc.passed ||
      got[i].criteria[j].seen !== wc.seen ||
      got[i].criteria[j].theme !== wc.theme);
    ok(bad.length === 0,
       `${name}/${w.author}: all ${w.criteria.length} criteria match ` +
       (bad.length ? `(first mismatch: ${bad[0].name})` : ""));
  });

  const con = L.consensus(got);
  ok(con.ok === want.consensus.ok, `${name}: consensus ok flag`);
  if (con.ok) {
    ok(con.stance === want.consensus.stance, `${name}: consensus stance identical`);
    ok(JSON.stringify(con.unanimous_weaknesses) ===
       JSON.stringify(want.consensus.unanimous_weaknesses),
       `${name}: unanimous weaknesses by theme match`);
    ok(JSON.stringify(con.accepted_by) === JSON.stringify(want.consensus.accepted_by),
       `${name}: same lenses accept it`);
  }

  const modes = L.runAll(facts);
  want.failures.forEach((w, i) => {
    ok(modes[i].name === w.name && modes[i].triggered === w.triggered &&
       modes[i].severity === w.severity,
       `${name}: ${w.name} → ${w.triggered} (${w.severity})`);
  });

  const d = L.discount(facts, got);
  ok(d.headline === want.discount.headline, `${name}: discount headline identical`);
  ok(JSON.stringify(Object.keys(d.suspended_authors).sort()) ===
     JSON.stringify(Object.keys(want.discount.suspended_authors).sort()),
     `${name}: the same authors are suspended`);
  ok(JSON.stringify(d.endorsements_still_standing.sort()) ===
     JSON.stringify(want.discount.endorsements_still_standing.sort()),
     `${name}: the same endorsements still stand`);
}

/* ---------- the properties, not just the parity ---------- */
ok(L.applyAll({}).every((v) => v.score === null),
   "with no data at all, no lens scores anything");
ok(L.runAll({}).every((m) => m.triggered === null && m.severity === "unknown"),
   "an untestable failure check says so rather than passing");
ok(L.derive({ pe: 30, earningsCagr3y: -0.1 }).peg === null,
   "no PEG for a shrinking business");
ok(L.consensus(L.applyAll({})).ok === false,
   "no consensus can be drawn from nothing");

// The teaching case: a quality trap scores WELL on the lenses and is caught
// only by the failure checks. That gap is the whole reason failures exist.
const qt = fx.cases.quality_trap;
const qtLenses = L.applyAll(qt.facts);
ok(qtLenses.filter((v) => v.score >= 0.6).length >= 4,
   "the quality trap passes four or more lenses cleanly");
ok(L.discount(qt.facts, qtLenses).fired.some((m) => m.name === "Quality trap"),
   "and is caught only by the failure checks");

console.log("\n" + (fail ? fail + " FAILED" : "all checks passed") + ` (${pass} passed)`);
process.exit(fail ? 1 : 0);
