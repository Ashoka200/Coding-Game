/* 360° Advisor — analysis engines running on live data.
   Ports of the repository's Python: technical.py, levels.py, fundamentals.py,
   fno.py, planner.py, plus the Castle-in-the-Air diagnostic (Malkiel). */
(function () {
  "use strict";

  var UNIVERSE = ["RELIANCE","TCS","HDFCBANK","ICICIBANK","INFY","LT","BHARTIARTL",
    "ITC","SBIN","TITAN","SUNPHARMA","AXISBANK","MARUTI","ASIANPAINT","BAJFINANCE",
    "HCLTECH","ULTRACEMCO","NESTLEIND","KOTAKBANK","TATAMOTORS"];
  var CORE = [
    { symbol: "NIFTYBEES", desc: "Nifty 50 index fund", share: 0.70 },
    { symbol: "JUNIORBEES", desc: "Nifty Next 50 index fund", share: 0.30 }
  ];
  var PROFILES = {
    careful:   { mix:[0.70,0.15,0.15], maxPos:0.05, stopMult:2.5, names:4 },
    balanced:  { mix:[0.60,0.30,0.10], maxPos:0.08, stopMult:2.0, names:5 },
    ambitious: { mix:[0.50,0.40,0.10], maxPos:0.12, stopMult:2.0, names:6 }
  };
  var LIMIT_BUFFER = 0.002;

  var S = { quotes:{}, nifty:null, fundamentals:null, plan:null,
            amount:1000000, profile:"balanced", castle:null };

  /* ---------- helpers ---------- */
  function inr(n, d) {
    if (n == null || isNaN(n)) return "—";
    return "₹" + Number(n).toLocaleString("en-IN",
      { maximumFractionDigits: d == null ? 0 : d, minimumFractionDigits: d == null ? 0 : d });
  }
  function num(n, d) {
    if (n == null || isNaN(n)) return "—";
    return Number(n).toLocaleString("en-IN",
      { maximumFractionDigits: d == null ? 0 : d, minimumFractionDigits: d == null ? 0 : d });
  }
  function pct(x, d) { return x == null || isNaN(x) ? "—" : (x >= 0 ? "+" : "") + (x * 100).toFixed(d == null ? 1 : d) + "%"; }
  function el(id) { return document.getElementById(id); }
  function clamp(x, a, b) { return Math.max(a, Math.min(b, x)); }
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) {
    return { "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;" }[c]; }); }

  /* ---------- tabs ---------- */
  var tabs = document.querySelectorAll("nav button");
  tabs.forEach(function (b) {
    b.addEventListener("click", function () {
      tabs.forEach(function (x) { x.setAttribute("aria-selected", "false"); });
      b.setAttribute("aria-selected", "true");
      document.querySelectorAll("section.pane").forEach(function (s) { s.classList.remove("active"); });
      el("p-" + b.dataset.tab).classList.add("active");
      if (b.dataset.tab === "portfolio") renderPortfolio();
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
  });

  /* ---------- data ---------- */
  function fetchQuotes(symbols) {
    return fetch("/api/quotes?symbols=" + encodeURIComponent(symbols.join(",")))
      .then(function (r) { if (!r.ok) throw new Error("data service " + r.status); return r.json(); })
      .then(function (d) {
        var map = {};
        (d.quotes || []).forEach(function (q) { if (!q.error) map[q.symbol] = q; });
        return map;
      });
  }

  /* ---------- technical engine (technical.py) ---------- */
  function stage(q) {
    if (q.sma200 == null) return 1;
    if (q.last > q.sma200 && q.sma200Rising && q.sma50 != null && q.last > q.sma50) return 2;
    if (q.last < q.sma200 && !q.sma200Rising) return 4;
    return q.sma200Rising ? 1 : 3;
  }
  function stageLabel(s) {
    return { 2:["Uptrend","up"], 1:["Basing","warn"], 3:["Topping","warn"], 4:["Downtrend","down"] }[s];
  }
  function rsiFrom(q) {
    // the quotes function gives us trend inputs; approximate RSI-14 position from
    // where price sits between the 52w high and the 20d swing low
    if (q.high52 == null || q.swingLow20 == null || q.high52 === q.swingLow20) return null;
    return clamp(100 * (q.last - q.swingLow20) / (q.high52 - q.swingLow20), 0, 100);
  }
  function techScore(q) {
    var s = 0, st = stage(q);
    s += ({2:40,1:20,3:10,4:0})[st];
    if (q.mom6m != null) s += clamp(q.mom6m * 60, 0, 15);
    if (q.high52) s += clamp(((q.last / q.high52 - 1) + 0.25) * 60, 0, 15);
    if (q.sma50 != null && q.last > q.sma50) s += 10;
    if (q.sma200 != null && q.last > q.sma200) s += 10;
    var volPct = q.atr14 && q.last ? q.atr14 / q.last : null;
    if (volPct != null && volPct < 0.03) s += 10;   // orderly trend, not a lottery ticket
    return Math.round(clamp(s, 0, 100));
  }
  function detectSetup(q) {
    if (stage(q) !== 2) return null;
    var from52 = q.last / q.high52 - 1;
    if (from52 > -0.01) return "New 52-week high";
    var nearEma = q.sma50 ? Math.abs(q.last / q.sma50 - 1) : 1;
    if (nearEma <= 0.03) return "Pullback to trend";
    if (from52 > -0.06) return "Pushing toward highs";
    return null;
  }
  function levels(q, capital, riskPct) {
    var entry = q.last;
    var stop = Math.max(q.swingLow20, entry - 2 * q.atr14);
    if (stop >= entry) stop = entry - 2 * q.atr14;
    var risk = entry - stop;
    if (risk <= 0) return null;
    var qty = Math.floor(Math.min((capital * riskPct) / risk, (capital * 0.08) / entry));
    return { entryLow: entry, entryHigh: entry + 0.5 * q.atr14, stop: stop,
             t1: entry + 1.5 * risk, t2: entry + 2.5 * risk, risk: risk, qty: qty,
             rr: 2.5 };
  }

  /* ---------- regime ---------- */
  function renderRegime() {
    var n = S.nifty;
    var chip = el("regimeChip");
    if (!n) { chip.textContent = "market data unavailable"; return null; }
    var above = n.sma200 != null && n.last > n.sma200;
    var dd = n.high52 ? n.last / n.high52 - 1 : 0;
    var state = above && dd > -0.05 ? ["EXPANSION","up","Full program — new positions allowed."]
      : dd < -0.20 ? ["CRISIS","down","Staged buying by the written plan only."]
      : dd < -0.10 ? ["STRESS","down","No new trading longs; index core only."]
      : ["CAUTION","warn","Position sizes cut; build the shopping list."];
    chip.textContent = state[0];
    chip.style.background = "var(--" + (state[1] === "up" ? "up-soft" : state[1] === "down" ? "down-soft" : "warn-soft") + ")";
    chip.style.color = "var(--" + state[1] + ")";
    el("regimeStats").innerHTML =
      stat("Market state", state[0], state[2], state[1] === "up" ? "good" : state[1] === "down" ? "bad" : "warnb") +
      stat("Nifty 50", num(n.last), (above ? "above" : "below") + " its 200-day average") +
      stat("From 1-year high", pct(dd), dd < -0.1 ? "a real correction" : "normal range") +
      stat("Suggestions today", "—", "counted after the scan", "");
    return { state: state[0], riskOn: state[0] === "EXPANSION" };
  }
  function stat(k, v, s, cls) {
    return '<div class="stat ' + (cls || "") + '"><div class="k">' + esc(k) + '</div>' +
           '<div class="v">' + v + '</div><div class="s">' + esc(s || "") + '</div></div>';
  }

  /* ---------- LIVE PICKS ---------- */
  function renderPicks() {
    var rows = UNIVERSE.map(function (s) { return S.quotes[s]; }).filter(Boolean);
    if (!rows.length) {
      el("sugRows").innerHTML = '<tr><td colspan="9" class="muted">No data — the feed is unreachable.</td></tr>';
      return;
    }
    var scored = rows.map(function (q) {
      return { q:q, score:techScore(q), setup:detectSetup(q), st:stage(q) };
    }).sort(function (a, b) { return b.score - a.score; });

    var reg = renderRegime();
    var sugg = scored.filter(function (x) { return x.setup; });
    if (reg && !reg.riskOn) {
      el("picksNote").innerHTML = '<div class="notice warnn"><span class="k">Regime filter active</span>' +
        'The market is not in a clean uptrend, so buy suggestions are withheld — most breakouts fail ' +
        'in weak markets. The ranking below is still shown as context.</div>';
      sugg = [];
    } else { el("picksNote").innerHTML = ""; }

    var st4 = el("regimeStats").querySelectorAll(".stat .v");
    if (st4.length >= 4) st4[3].textContent = String(sugg.length);

    el("sugRows").innerHTML = sugg.length ? sugg.map(function (x) {
      var L = levels(x.q, 1000000, 0.0075);
      if (!L) return "";
      return '<tr><td class="sym">' + x.q.symbol + '</td>' +
        '<td><span class="pill acc">' + esc(x.setup) + '</span></td>' +
        '<td class="num">' + num(x.q.last, 2) + '</td>' +
        '<td class="num">' + num(L.entryLow, 2) + "–" + num(L.entryHigh, 2) + '</td>' +
        '<td class="num neg">' + num(L.stop, 2) + '</td>' +
        '<td class="num pos">' + num(L.t1, 2) + '</td>' +
        '<td class="num pos">' + num(L.t2, 2) + '</td>' +
        '<td class="num">1 : 2.5</td>' +
        '<td class="num"><strong>' + x.score + '</strong></td></tr>';
    }).join("") : '<tr><td colspan="9" class="muted">No setup qualifies today. ' +
      'A forced trade is worse than no trade.</td></tr>';

    el("rankRows").innerHTML = scored.map(function (x) {
      var q = x.q, sl = stageLabel(x.st);
      var day = q.prevClose ? q.last / q.prevClose - 1 : null;
      var volPct = q.atr14 && q.last ? q.atr14 / q.last : null;
      return '<tr><td class="sym">' + q.symbol + '</td>' +
        '<td class="num">' + num(q.last, 2) + '</td>' +
        '<td class="num ' + (day >= 0 ? "pos" : "neg") + '">' + pct(day, 2) + '</td>' +
        '<td><span class="pill ' + sl[1] + '">' + sl[0] + '</span></td>' +
        '<td class="num">' + num(rsiFrom(q), 0) + '</td>' +
        '<td class="num">' + pct(q.high52 ? q.last / q.high52 - 1 : null) + '</td>' +
        '<td class="num ' + (q.mom6m >= 0 ? "pos" : "neg") + '">' + pct(q.mom6m) + '</td>' +
        '<td class="num">' + (volPct == null ? "—" : (volPct * 100).toFixed(1) + "%") + '</td>' +
        '<td class="num"><strong>' + x.score + '</strong></td></tr>';
    }).join("");
  }

  /* ---------- FUNDAMENTALS (fundamentals.py) ---------- */
  function fundScore(f) {
    var score = 0, gaps = [], flags = [];
    // Quality 40
    if (f.roe != null) score += clamp(f.roe / 0.20, 0, 1) * 20; else { score += 10; gaps.push("ROE"); }
    if (f.opMargin != null) score += clamp(f.opMargin / 0.20, 0, 1) * 10; else { score += 5; gaps.push("margins"); }
    if (f.debtToEquity != null) {
      var de = f.debtToEquity > 5 ? f.debtToEquity / 100 : f.debtToEquity;
      score += clamp(1 - de / 2, 0, 1) * 10;
      if (de > 2) flags.push("heavily indebted");
    } else { score += 5; gaps.push("debt"); }
    // Growth 25
    if (f.revenueGrowth != null) score += clamp(f.revenueGrowth / 0.15, 0, 1) * 12.5;
    else { score += 6.25; gaps.push("revenue growth"); }
    if (f.earningsGrowth != null) score += clamp(f.earningsGrowth / 0.15, 0, 1) * 12.5;
    else { score += 6.25; gaps.push("earnings growth"); }
    // Valuation 25
    if (f.pe != null && f.pe > 0) {
      score += clamp((60 - f.pe) / 45, 0, 1) * 15;
      if (f.pe > 80) flags.push("priced for perfection");
    } else { score += 7.5; gaps.push("P/E"); }
    if (f.evEbitda != null && f.evEbitda > 0) score += clamp((30 - f.evEbitda) / 22, 0, 1) * 10;
    else { score += 5; gaps.push("EV/EBITDA"); }
    // Safety 10
    if (f.currentRatio != null) score += clamp((f.currentRatio - 0.8) / 1.2, 0, 1) * 10;
    else { score += 5; gaps.push("liquidity"); }
    return { score: Math.round(score), gaps: gaps, flags: flags };
  }
  function fundRead(f, sc) {
    if (sc.flags.length) return sc.flags[0].charAt(0).toUpperCase() + sc.flags[0].slice(1);
    if (sc.score >= 72) return "Strong business, sensibly priced";
    if (sc.score >= 58) return "Sound, nothing alarming";
    if (sc.score >= 45) return "Mixed — check what is weak";
    return "Weak on the numbers";
  }

  function loadFundamentals() {
    var st = el("fundStatus");
    st.innerHTML = '<span class="spin"></span>Fetching…';
    return fetch("/api/fundamentals?symbols=" + encodeURIComponent(UNIVERSE.slice(0, 15).join(",")))
      .then(function (r) { return r.json(); })
      .then(function (d) {
        S.fundamentals = {};
        (d.fundamentals || []).forEach(function (f) { if (!f.error) S.fundamentals[f.symbol] = f; });
        var got = Object.keys(S.fundamentals).length;
        st.textContent = got ? got + " companies loaded." :
          "The fundamentals source is unavailable right now — no numbers rather than invented ones.";
        renderFundamentals();
        return S.fundamentals;
      })
      .catch(function (e) {
        st.textContent = "Could not load fundamentals (" + e.message + ").";
        return {};
      });
  }

  function renderFundamentals() {
    var syms = Object.keys(S.fundamentals || {});
    if (!syms.length) {
      el("fundRows").innerHTML = '<tr><td colspan="9" class="muted">No fundamental data available. ' +
        'The technical and Castle screens still work on price data.</td></tr>';
      return;
    }
    var rows = syms.map(function (s) {
      var f = S.fundamentals[s];
      return { f:f, sc:fundScore(f) };
    }).sort(function (a, b) { return b.sc.score - a.sc.score; });

    el("fundRows").innerHTML = rows.map(function (x) {
      var f = x.f, de = f.debtToEquity != null ? (f.debtToEquity > 5 ? f.debtToEquity / 100 : f.debtToEquity) : null;
      return '<tr class="click" data-sym="' + f.symbol + '"><td><span class="sym">' + f.symbol + '</span>' +
        '<div class="muted">' + esc((f.name || "").slice(0, 34)) + '</div></td>' +
        '<td class="num"><strong>' + x.sc.score + '</strong></td>' +
        '<td class="num">' + num(f.pe, 1) + '</td>' +
        '<td class="num">' + num(f.pb, 1) + '</td>' +
        '<td class="num">' + pct(f.roe) + '</td>' +
        '<td class="num">' + pct(f.opMargin) + '</td>' +
        '<td class="num">' + num(de, 2) + '</td>' +
        '<td class="num">' + pct(f.revenueGrowth) + '</td>' +
        '<td>' + esc(fundRead(f, x.sc)) + (x.sc.gaps.length ?
          ' <span class="pill mut">' + x.sc.gaps.length + ' gaps</span>' : "") + '</td></tr>';
    }).join("");

    el("fundRows").querySelectorAll("tr.click").forEach(function (tr) {
      tr.addEventListener("click", function () { fundDetail(tr.dataset.sym); });
    });
  }

  function fundDetail(sym) {
    var f = S.fundamentals[sym]; if (!f) return;
    var sc = fundScore(f);
    var q = S.quotes[sym];
    var parts = [
      ["Profitability (ROE)", f.roe == null ? null : clamp(f.roe / 0.25, 0, 1)],
      ["Operating margin", f.opMargin == null ? null : clamp(f.opMargin / 0.25, 0, 1)],
      ["Low debt", f.debtToEquity == null ? null : clamp(1 - (f.debtToEquity > 5 ? f.debtToEquity / 100 : f.debtToEquity) / 2, 0, 1)],
      ["Revenue growth", f.revenueGrowth == null ? null : clamp(f.revenueGrowth / 0.20, 0, 1)],
      ["Earnings growth", f.earningsGrowth == null ? null : clamp(f.earningsGrowth / 0.20, 0, 1)],
      ["Valuation (cheaper is more)", f.pe == null ? null : clamp((60 - f.pe) / 45, 0, 1)]
    ];
    var cash = f.operatingCashflow && f.freeCashflow
      ? "Free cash flow " + inr(f.freeCashflow / 1e7, 0) + " Cr of " + inr(f.operatingCashflow / 1e7, 0) + " Cr operating"
      : "Cash-flow detail not available";
    el("fundDetail").innerHTML =
      '<h2>' + esc(f.name || sym) + ' — the read</h2><div class="grid2"><div class="card">' +
      parts.map(function (p) {
        return '<div class="bar"><div class="bl">' + esc(p[0]) + '</div><div class="track">' +
          '<div class="fill" style="width:' + (p[1] == null ? 0 : p[1] * 100) + '%;' +
          (p[1] == null ? "background:var(--line)" : "") + '"></div></div>' +
          '<div class="bv">' + (p[1] == null ? "—" : Math.round(p[1] * 100)) + '</div></div>';
      }).join("") +
      '<p class="muted" style="margin-top:12px">' + esc(cash) + '. ' +
      (f.dividendYield ? "Dividend yield " + pct(f.dividendYield) + ". " : "") +
      (f.beta != null ? "Moves " + f.beta.toFixed(2) + "× the market." : "") + '</p></div>' +
      '<div class="card"><div class="stat" style="border:none;padding:0;margin-bottom:12px">' +
      '<div class="k">Fundamental score</div><div class="v">' + sc.score + ' / 100</div>' +
      '<div class="s">' + esc(fundRead(f, sc)) + '</div></div>' +
      (sc.flags.length ? '<div class="notice err">Flag: ' + esc(sc.flags.join("; ")) + '</div>' : "") +
      (sc.gaps.length ? '<div class="notice info">Not available from the free source: ' +
        esc(sc.gaps.join(", ")) + '. These score neutral — never assumed good.</div>' : "") +
      (q ? '<p class="muted">Trend right now: ' + stageLabel(stage(q))[0].toLowerCase() +
        ', ' + pct(q.last / q.high52 - 1) + ' from its 52-week high. Fundamentals say what to own; ' +
        'the trend says when.</p>' : "") +
      '</div></div>';
  }
  el("loadFund").addEventListener("click", loadFundamentals);

  /* ---------- CASTLE IN THE AIR (Malkiel) ---------- */
  function castleScore(q) {
    // How much of this price is crowd enthusiasm rather than arithmetic?
    var c = 0, fuel = [];
    var ext = q.sma200 ? q.last / q.sma200 - 1 : 0;          // stretch above trend
    c += clamp(ext / 0.40, 0, 1) * 30;
    if (ext > 0.25) fuel.push("far above its long-term trend");
    if (q.mom6m != null) {
      c += clamp(q.mom6m / 0.50, 0, 1) * 30;                  // 6m run
      if (q.mom6m > 0.35) fuel.push("a steep six-month run");
    }
    var from52 = q.high52 ? q.last / q.high52 - 1 : -1;
    c += clamp((from52 + 0.10) / 0.10, 0, 1) * 20;            // pinned at highs
    if (from52 > -0.02) fuel.push("sitting at its highs");
    var volPct = q.atr14 && q.last ? q.atr14 / q.last : 0;
    c += clamp((volPct - 0.015) / 0.035, 0, 1) * 20;          // agitation
    if (volPct > 0.035) fuel.push("unusually wide daily swings");
    return { score: Math.round(clamp(c, 0, 100)), ext: ext, fuel: fuel, volPct: volPct };
  }

  function classify(ff, cs) {
    if (ff == null) return ["Unmeasured", "mut",
      "No fundamental data, so we cannot tell whether the price rests on earnings or on hope."];
    if (ff >= 55 && cs < 50) return ["Firm ground", "up",
      "The price is supported by the business, and the crowd has not arrived. This is where patient money is usually best paid — and where it waits longest."];
    if (ff >= 55 && cs >= 50) return ["Well-founded castle", "sky",
      "Good business AND an enthusiastic crowd. The most comfortable place to hold, and the easiest place to overstay: the crowd leaves faster than the earnings do."];
    if (ff < 55 && cs >= 50) return ["Castle in the air", "down",
      "The crowd is doing the lifting, not the earnings. You are relying on someone paying more than you did. If you buy this, size it small and know your exit before you enter."];
    return ["Neglected and weak", "mut",
      "Neither the numbers nor the crowd support it. Cheapness alone is not a reason."];
  }

  function runCastle() {
    var st = el("castleStatus");
    st.innerHTML = '<span class="spin"></span>Running…';
    var need = S.fundamentals ? Promise.resolve(S.fundamentals) : loadFundamentals();
    need.then(function () {
      var rows = UNIVERSE.map(function (s) {
        var q = S.quotes[s]; if (!q) return null;
        var f = (S.fundamentals || {})[s];
        var ff = f ? fundScore(f).score : null;
        var cs = castleScore(q);
        var cl = classify(ff, cs.score);
        return { sym:s, q:q, ff:ff, cs:cs, cls:cl };
      }).filter(Boolean).sort(function (a, b) { return b.cs.score - a.cs.score; });
      S.castle = rows;
      st.textContent = rows.length + " stocks mapped." +
        (S.fundamentals && Object.keys(S.fundamentals).length ? "" :
         " Without fundamentals only the crowd axis is measured.");
      renderCastle(rows);
    });
  }

  function renderCastle(rows) {
    // quadrant map
    var q = el("quad");
    var html = '<div class="qc" style="position:absolute;inset:0">' +
      '<div style="position:absolute;left:50%;top:0;bottom:0;width:1px;background:var(--line)"></div>' +
      '<div style="position:absolute;top:50%;left:0;right:0;height:1px;background:var(--line)"></div>' +
      '<div class="qlabel" style="left:10px;top:8px">Castle in the air</div>' +
      '<div class="qlabel" style="right:10px;top:8px">Well-founded castle</div>' +
      '<div class="qlabel" style="left:10px;bottom:8px">Neglected</div>' +
      '<div class="qlabel" style="right:10px;bottom:8px">Firm ground</div></div>';
    rows.forEach(function (r) {
      if (r.ff == null) return;
      var x = clamp(r.ff, 0, 100), y = clamp(r.cs.score, 0, 100);
      html += '<div class="dot" data-sym="' + r.sym + '" title="' + r.sym +
        '" style="left:' + x + '%;top:' + (100 - y) + '%;background:var(--' +
        (r.cls[1] === "mut" ? "muted" : r.cls[1]) + ')"><span>' + r.sym + '</span></div>';
    });
    q.innerHTML = html;
    q.querySelectorAll(".dot").forEach(function (d) {
      d.addEventListener("click", function () { castlePanel(d.dataset.sym); });
    });

    el("castleRows").innerHTML = rows.map(function (r) {
      return '<tr class="click" data-sym="' + r.sym + '"><td class="sym">' + r.sym + '</td>' +
        '<td class="num">' + (r.ff == null ? "—" : r.ff) + '</td>' +
        '<td class="num"><strong>' + r.cs.score + '</strong></td>' +
        '<td><span class="pill ' + r.cls[1] + '">' + esc(r.cls[0]) + '</span></td>' +
        '<td class="num">' + pct(r.cs.ext) + '</td>' +
        '<td class="num">' + (r.cs.fuel.length || "—") + '</td>' +
        '<td class="muted">' + esc(r.cls[2].split(".")[0]) + '.</td></tr>';
    }).join("");
    el("castleRows").querySelectorAll("tr.click").forEach(function (tr) {
      tr.addEventListener("click", function () { castlePanel(tr.dataset.sym); });
    });
    if (rows.length) castlePanel(rows[0].sym);
  }

  function castlePanel(sym) {
    var r = (S.castle || []).filter(function (x) { return x.sym === sym; })[0];
    if (!r) return;
    var fuel = r.cs.fuel.length ? r.cs.fuel.join(", ") : "nothing unusual — the price is calm";
    el("castlePanel").innerHTML =
      '<div class="card"><div style="display:flex;align-items:baseline;gap:12px;flex-wrap:wrap">' +
      '<h2 style="margin:0">' + sym + '</h2><span class="pill ' + r.cls[1] + '">' + esc(r.cls[0]) + '</span></div>' +
      '<div class="bar" style="margin-top:14px"><div class="bl">Firm foundation</div><div class="track">' +
      '<div class="fill" style="width:' + (r.ff || 0) + '%;background:var(--up)"></div></div>' +
      '<div class="bv">' + (r.ff == null ? "—" : r.ff) + '</div></div>' +
      '<div class="bar"><div class="bl">Castle (crowd)</div><div class="track">' +
      '<div class="fill" style="width:' + r.cs.score + '%;background:var(--sky)"></div></div>' +
      '<div class="bv">' + r.cs.score + '</div></div>' +
      '<p style="margin:14px 0 0">' + esc(r.cls[2]) + '</p>' +
      '<p class="muted" style="margin:10px 0 0">Crowd fuel: ' + esc(fuel) + '. ' +
      'Price is ' + pct(r.cs.ext) + ' from its long-term trend line' +
      (r.cs.ext > 0.25 ? ' — a gap that historically closes by the price falling, not the trend rising.' : '.') +
      '</p>' +
      '<p class="muted" style="margin:10px 0 0"><em>Malkiel\'s point: neither theory is wrong. ' +
      'Firm-foundation buyers are paid by the business over years; castle buyers are paid by the ' +
      'next buyer, and only while there is one.</em></p></div>';
  }
  el("loadCastle").addEventListener("click", runCastle);

  /* ---------- F&O (fno.py) ---------- */
  function normCdf(x) {
    var t = 1 / (1 + 0.2316419 * Math.abs(x));
    var d = 0.3989423 * Math.exp(-x * x / 2);
    var p = d * t * (0.3193815 + t * (-0.3565638 + t * (1.781478 + t * (-1.821256 + t * 1.330274))));
    return x > 0 ? 1 - p : p;
  }
  function bs(spot, strike, t, iv, r, kind) {
    if (t <= 0 || iv <= 0) return { price: Math.max(0, kind === "call" ? spot - strike : strike - spot), delta: 0 };
    var d1 = (Math.log(spot / strike) + (r + iv * iv / 2) * t) / (iv * Math.sqrt(t));
    var d2 = d1 - iv * Math.sqrt(t);
    var disc = Math.exp(-r * t);
    if (kind === "call") return { price: spot * normCdf(d1) - strike * disc * normCdf(d2), delta: normCdf(d1) };
    return { price: strike * disc * normCdf(-d2) - spot * normCdf(-d1), delta: normCdf(d1) - 1 };
  }

  function loadFno() {
    var sym = el("fnoSym").value;
    var capital = +el("fnoCapital").value || 1000000;
    el("fnoStatus").innerHTML = '<span class="spin"></span>Analysing…';
    var underlying = sym === "NIFTY" ? "^NSEI" : sym === "BANKNIFTY" ? "^NSEBANK" : sym;
    Promise.all([
      fetchQuotes([underlying]),
      fetch("/api/optionchain?symbol=" + encodeURIComponent(sym)).then(function (r) { return r.json(); })
        .catch(function () { return { error: "unreachable" }; })
    ]).then(function (res) {
      var q = res[0][underlying];
      var chain = res[1];
      el("fnoStatus").textContent = "";
      renderFno(sym, q, chain, capital);
    });
  }

  function renderFno(sym, q, chain, capital) {
    if (!q) {
      el("fnoStats").innerHTML = "";
      el("fnoSuggestion").innerHTML = '<div class="notice err">No price data for ' + esc(sym) + '.</div>';
      el("fnoChain").innerHTML = "";
      return;
    }
    var spot = chain && chain.spot ? chain.spot : q.last;
    // historical volatility from ATR (a robust proxy when we have no IV)
    var hv = q.atr14 && q.last ? (q.atr14 / q.last) * Math.sqrt(252) : null;
    var iv = chain && chain.atmIV ? chain.atmIV / 100 : null;
    var ivp = iv && hv ? clamp((iv / hv - 0.8) / 0.6, 0, 1) : null;  // rich vs its own realised
    var st = stage(q);
    var view = st === 2 ? "bullish" : st === 4 ? "bearish" : "rangebound";
    var expensive = ivp == null ? null : ivp >= 0.55;

    el("fnoStats").innerHTML =
      stat("Spot", num(spot, 2), sym) +
      stat("Realised volatility", hv == null ? "—" : (hv * 100).toFixed(1) + "%", "annualised, from daily range") +
      stat("Implied volatility", iv == null ? "—" : (iv * 100).toFixed(1) + "%",
           iv == null ? "chain unavailable" : (expensive ? "options are expensive" : "options are cheap"),
           iv == null ? "" : (expensive ? "warnb" : "good")) +
      stat("Put/Call ratio", chain && chain.pcr ? chain.pcr : "—",
           chain && chain.maxPain ? "max pain " + num(chain.maxPain) : "positioning unavailable");

    // strategy selection — direction second, volatility first
    var strat, legs, why, maxLoss, maxGain;
    var width = Math.max(1, Math.round(spot * 0.02 / (spot > 5000 ? 100 : spot > 1000 ? 20 : 5)) *
                            (spot > 5000 ? 100 : spot > 1000 ? 20 : 5));
    var atm = Math.round(spot / width) * width;
    var t = 21 / 365, rr = 0.065;
    var useIv = iv || hv || 0.2;

    if (view === "rangebound" && expensive === false) {
      strat = "No trade";
      why = "The trend is unclear and options are not expensive enough to be worth selling. " +
            "Waiting is a position.";
      legs = []; maxLoss = 0; maxGain = 0;
    } else if (expensive) {
      // sell premium with defined risk, in the direction of the trend
      var sellStrike = view === "bearish" ? atm + width : atm - width;
      var buyStrike = view === "bearish" ? atm + 2 * width : atm - 2 * width;
      var kind = view === "bearish" ? "call" : "put";
      var credit = Math.abs(bs(spot, sellStrike, t, useIv, rr, kind).price -
                            bs(spot, buyStrike, t, useIv, rr, kind).price);
      strat = view === "bearish" ? "Bear call spread" : "Bull put spread";
      legs = [["SELL", kind.toUpperCase(), sellStrike], ["BUY", kind.toUpperCase(), buyStrike]];
      maxGain = credit; maxLoss = width - credit;
      why = "Implied volatility is rich versus what this underlying actually moves, so you are paid " +
            "to sell it. The bought leg caps the loss — that is the whole point.";
    } else {
      var k1 = view === "bearish" ? atm : atm;
      var k2 = view === "bearish" ? atm - width : atm + width;
      var kind2 = view === "bearish" ? "put" : "call";
      var debit = Math.abs(bs(spot, k1, t, useIv, rr, kind2).price -
                           bs(spot, k2, t, useIv, rr, kind2).price);
      strat = view === "bearish" ? "Bear put spread" : "Bull call spread";
      legs = [["BUY", kind2.toUpperCase(), k1], ["SELL", kind2.toUpperCase(), k2]];
      maxLoss = debit; maxGain = width - debit;
      why = "Options are not expensive, so buy the move rather than sell it — and cap the cost " +
            "with the sold leg instead of paying for a naked option.";
    }

    var lot = sym === "NIFTY" ? 75 : sym === "BANKNIFTY" ? 30 : 250;
    var lossPerLot = maxLoss * lot;
    var lots = lossPerLot > 0 ? Math.floor((capital * 0.0075) / lossPerLot) : 0;

    // target and stop expressed on the UNDERLYING, which is what you can watch
    var target = view === "bearish" ? spot - 1.5 * q.atr14 : spot + 1.5 * q.atr14;
    var stop = view === "bearish" ? spot + q.atr14 : spot - q.atr14;

    el("fnoSuggestion").innerHTML =
      '<h2>Suggested structure</h2><div class="grid2"><div class="card">' +
      '<div style="display:flex;align-items:baseline;gap:11px;flex-wrap:wrap;margin-bottom:10px">' +
      '<span style="font-family:Archivo,sans-serif;font-weight:800;font-size:19px">' + esc(strat) + '</span>' +
      (legs.length ? '<span class="pill up">defined risk</span>' : '<span class="pill mut">wait</span>') + '</div>' +
      (legs.length ? '<div class="tablewrap"><table><thead><tr><th>Leg</th><th>Type</th>' +
        '<th class="num">Strike</th></tr></thead><tbody>' +
        legs.map(function (l) {
          return '<tr><td><strong style="color:var(--' + (l[0] === "BUY" ? "up" : "down") + ')">' +
            l[0] + '</strong></td><td>' + l[1] + '</td><td class="num">' + num(l[2]) + '</td></tr>';
        }).join("") + '</tbody></table></div>' : "") +
      '<p style="margin:12px 0 0">' + esc(why) + '</p></div>' +
      '<div class="card">' +
      (legs.length ?
        '<div class="stats" style="grid-template-columns:1fr 1fr">' +
        stat("Max loss per lot", inr(lossPerLot), "this is your risk, not the margin", "bad") +
        stat("Max gain per lot", inr(maxGain * lot), "at or beyond the sold strike", "good") +
        stat("Lots at 0.75% risk", String(Math.max(lots, 0)), "of " + inr(capital)) +
        stat("Reward : risk", maxLoss > 0 ? (maxGain / maxLoss).toFixed(2) + " : 1" : "—", "before costs") +
        '</div>' +
        '<div class="notice warnn" style="margin-top:12px"><span class="k">Underlying target &amp; stop</span>' +
        'Take profit if ' + esc(sym) + ' reaches <strong class="mono">' + num(target, 2) + '</strong>; ' +
        'abandon the trade if it hits <strong class="mono">' + num(stop, 2) + '</strong>. ' +
        'Exit credit spreads at 50–60% of max profit; never hold a short leg into the final week ' +
        'for the last few rupees.</div>'
        : '<div class="notice info">No structure is worth entering on this underlying today.</div>') +
      (iv == null ? '<div class="notice info" style="margin-top:10px">Live option chain unavailable, ' +
        'so implied volatility is estimated from realised movement. Verify actual premiums and IV ' +
        'in your broker terminal before placing.</div>' : "") +
      '</div></div>';

    el("fnoChain").innerHTML = chain && chain.strikes && chain.strikes.length ?
      '<h2>Option chain — ' + esc(chain.expiry || "") + '</h2><div class="card tight"><div class="tablewrap">' +
      '<table><thead><tr><th class="num">Call OI</th><th class="num">Call IV</th><th class="num">Call ₹</th>' +
      '<th class="num">Strike</th><th class="num">Put ₹</th><th class="num">Put IV</th><th class="num">Put OI</th>' +
      '</tr></thead><tbody>' + chain.strikes.map(function (s) {
        var isAtm = Math.abs(s.strike - spot) < width / 2;
        return '<tr' + (isAtm ? ' style="background:var(--accent-soft)"' : '') + '>' +
          '<td class="num">' + num(s.callOI) + '</td><td class="num">' + num(s.callIV, 1) + '</td>' +
          '<td class="num">' + num(s.callLtp, 2) + '</td>' +
          '<td class="num"><strong>' + num(s.strike) + '</strong></td>' +
          '<td class="num">' + num(s.putLtp, 2) + '</td><td class="num">' + num(s.putIV, 1) + '</td>' +
          '<td class="num">' + num(s.putOI) + '</td></tr>';
      }).join("") + '</tbody></table></div></div>' +
      '<p class="muted">Open interest shows where the crowd is positioned — useful context, ' +
      'never a signal on its own.</p>'
      : '<p class="muted" style="margin-top:14px">Live chain not available for ' + esc(sym) +
        ' right now; the structure above is derived from realised volatility.</p>';
  }
  el("loadFno").addEventListener("click", loadFno);

  /* ---------- INVEST FLOW (planner.py) ---------- */
  function gotoStep(n) {
    ["i1","i2","i3"].forEach(function (id, i) { el(id).classList.toggle("active", i + 1 === n); });
    var steps = document.querySelectorAll("#steps .step"), bars = document.querySelectorAll("#steps .sbar");
    steps.forEach(function (e2, i) {
      e2.classList.toggle("on", i + 1 === n);
      e2.classList.toggle("done", i + 1 < n);
      e2.querySelector(".dotn").textContent = String(i + 1);
    });
    bars.forEach(function (b, i) { b.classList.toggle("done", i + 1 < n); });
    window.scrollTo({ top: 0, behavior: "smooth" });
  }
  var amtInput = el("amount");
  amtInput.addEventListener("input", function () {
    var v = parseInt(String(amtInput.value).replace(/[^0-9]/g, ""), 10) || 0;
    S.amount = v; amtInput.value = v ? v.toLocaleString("en-IN") : "";
  });
  document.querySelectorAll(".chip").forEach(function (c) {
    c.addEventListener("click", function () {
      S.amount = +c.dataset.amt; amtInput.value = S.amount.toLocaleString("en-IN");
    });
  });
  document.querySelectorAll(".prof").forEach(function (p) {
    p.addEventListener("click", function () {
      document.querySelectorAll(".prof").forEach(function (x) { x.setAttribute("aria-pressed","false"); });
      p.setAttribute("aria-pressed","true"); S.profile = p.dataset.p;
    });
  });

  function buildPlan() {
    var cfg = PROFILES[S.profile], amount = S.amount, status = el("buildStatus");
    if (amount < 25000) {
      status.innerHTML = '<span class="neg">Minimum ₹25,000 — below that, costs and lot sizes eat the diversification.</span>';
      return;
    }
    status.innerHTML = '<span class="spin"></span>Building…';
    el("build").disabled = true;
    fetchQuotes(CORE.map(function (c) { return c.symbol; })).then(function (coreQ) {
      var n = S.nifty;
      var riskOn = n && n.sma200 != null ? n.last > n.sma200 : true;
      var mix = cfg.mix.slice(), notes = [];
      if (!riskOn) {
        notes.push("The market is below its long-term average, so the stock sleeve stays in cash and " +
                   "only the index core is bought. This is the playbook, not a forecast.");
        mix = [Math.min(mix[0], 0.60), 0, 1 - Math.min(mix[0], 0.60)];
      }
      var lines = [], coreAmt = amount * mix[0];
      CORE.forEach(function (c) {
        var q = coreQ[c.symbol];
        if (!q) { notes.push("No live price for " + c.symbol + " — left out of this plan."); return; }
        var qty = Math.floor(coreAmt * c.share / q.last);
        if (qty > 0) lines.push({ symbol:c.symbol, role:"core", desc:c.desc, qty:qty,
                                  price:q.last, value:qty * q.last, stop:null, risk:0 });
      });
      if (mix[1] > 0) {
        var eligible = UNIVERSE.map(function (s) { return S.quotes[s]; }).filter(Boolean)
          .filter(function (q) { return stage(q) === 2; })
          .map(function (q) { return { q:q, score:techScore(q) }; })
          .sort(function (a, b) { return b.score - a.score; })
          .slice(0, cfg.names);
        if (eligible.length) {
          var per = Math.min(amount * mix[1] / eligible.length, amount * cfg.maxPos);
          eligible.forEach(function (e) {
            var q = e.q;
            var stop = Math.max(q.swingLow20, q.last - cfg.stopMult * q.atr14);
            if (stop >= q.last) stop = q.last - cfg.stopMult * q.atr14;
            var qty = Math.floor(per / q.last);
            if (qty <= 0) return;
            var price = Math.round(q.last * 100) / 100, st = Math.round(stop * 100) / 100;
            lines.push({ symbol:q.symbol, role:"satellite",
                         desc:"in an uptrend, score " + e.score, qty:qty, price:price,
                         value:qty * price, stop:st, risk:qty * (price - st) });
          });
          if (eligible.length < cfg.names) notes.push("Only " + eligible.length +
            " stock(s) passed the trend filter, so each gets a larger share (capped by the profile limit).");
        } else {
          notes.push("No stock passed the trend filter today, so that sleeve stays in cash.");
        }
      }
      var invested = lines.reduce(function (s, l) { return s + l.value; }, 0);
      var coreVal = lines.filter(function (l) { return l.role === "core"; })
                         .reduce(function (s, l) { return s + l.value; }, 0);
      var satBad = lines.filter(function (l) { return l.role === "satellite"; })
                        .reduce(function (s, l) { return s + Math.max(l.risk, l.value * 0.09); }, 0);
      S.plan = { amount:amount, profile:S.profile, lines:lines, notes:notes, invested:invested,
                 cash:amount - invested, badMonth:coreVal * 0.07 + satBad, mix:mix, riskOn:riskOn };
      renderPlan(); status.innerHTML = ""; el("build").disabled = false; gotoStep(2);
    }).catch(function (e) {
      status.innerHTML = '<span class="neg">Could not reach the data service (' + esc(e.message) + ').</span>';
      el("build").disabled = false;
    });
  }
  el("build").addEventListener("click", buildPlan);

  function renderPlan() {
    var p = S.plan;
    el("planTitle").textContent = "Your plan for " + inr(p.amount);
    el("planSub").textContent = p.profile.charAt(0).toUpperCase() + p.profile.slice(1) +
      " profile · " + (p.riskOn ? "market conditions normal" : "market below its long-term average");
    var cashPct = Math.max(0, 1 - p.mix[0] - p.mix[1]);
    el("allocbar").innerHTML =
      '<div style="width:' + p.mix[0] * 100 + '%;background:var(--accent)">CORE ' + Math.round(p.mix[0] * 100) + '%</div>' +
      (p.mix[1] > 0 ? '<div style="width:' + p.mix[1] * 100 + '%;background:var(--up)">STOCKS ' + Math.round(p.mix[1] * 100) + '%</div>' : '') +
      '<div style="width:' + cashPct * 100 + '%;background:var(--surface2);color:var(--muted)">CASH ' + Math.round(cashPct * 100) + '%</div>';
    el("planRows").innerHTML = p.lines.map(function (l) {
      return '<tr><td><span class="sym">' + l.symbol + '</span><div class="muted">' + esc(l.desc) + '</div></td>' +
        '<td><span class="pill ' + (l.role === "core" ? "acc\">Core" : "up\">Stock pick") + '</span></td>' +
        '<td class="num">' + num(l.qty) + '</td><td class="num">' + num(l.price, 2) + '</td>' +
        '<td class="num">' + num(l.value) + '</td>' +
        '<td class="num ' + (l.stop ? "neg" : "muted") + '">' + (l.stop ? num(l.stop, 2) : "hold") + '</td></tr>';
    }).join("") +
      '<tr><td><span class="sym" style="color:var(--muted)">Cash kept back</span></td>' +
      '<td><span class="pill mut">Cash</span></td><td></td><td></td>' +
      '<td class="num">' + num(p.cash) + '</td><td class="num muted">—</td></tr>';
    el("planNotes").innerHTML = p.notes.map(function (n) {
      return '<div class="notice warnn">' + esc(n) + '</div>'; }).join("");
    el("badMonth").innerHTML = "This plan could be down about <strong class='mono'>" + inr(p.badMonth) +
      "</strong> (" + (100 * p.badMonth / p.amount).toFixed(1) + "%) in a bad month. If that number " +
      "would make you sell everything, choose the Careful profile instead.";
  }
  el("back1").addEventListener("click", function () { gotoStep(1); });
  el("back2").addEventListener("click", function () { gotoStep(2); });
  el("approve").addEventListener("click", function () { renderOrders(); gotoStep(3); });

  function orders() {
    return S.plan.lines.filter(function (l) { return l.qty > 0; }).map(function (l) {
      return { variety:"regular", tradingsymbol:l.symbol, exchange:"NSE", transaction_type:"BUY",
               order_type:"LIMIT", quantity:l.qty, product:"CNC", readonly:false,
               price: Math.round(l.price * (1 + LIMIT_BUFFER) * 10) / 10 };
    });
  }
  function renderOrders() {
    var os = orders();
    var total = os.reduce(function (s, o) { return s + o.quantity * o.price; }, 0);
    el("ordTitle").textContent = "Send " + os.length + " orders to your Demat account";
    el("ordSummary").textContent = os.length + " buy orders · about " + inr(total) +
      " · cash left " + inr(S.plan.cash);
    el("ordRows").innerHTML = os.map(function (o) {
      return '<tr><td><strong class="pos">BUY</strong> <span class="sym">' + o.tradingsymbol + '</span></td>' +
        '<td class="num">' + num(o.quantity) + '</td><td class="num">' + num(o.price, 2) + '</td>' +
        '<td class="num">' + num(o.quantity * o.price) + '</td></tr>';
    }).join("");
    el("fData").value = JSON.stringify(os);
    el("fKey").value = el("kitekey").value.trim();
  }
  try { el("kitekey").value = localStorage.getItem("kiteApiKey") || ""; } catch (e) {}
  el("kitekey").addEventListener("input", function () {
    try { localStorage.setItem("kiteApiKey", el("kitekey").value.trim()); } catch (e) {}
  });
  el("kiteForm").addEventListener("submit", function (ev) {
    var k = el("kitekey").value.trim();
    el("fKey").value = k; el("fData").value = JSON.stringify(orders());
    if (!k) { ev.preventDefault();
      alert("Add your Kite API key first (free at kite.trade), or use Download as CSV."); }
  });
  el("dlCsv").addEventListener("click", function () {
    var rows = [["Exchange","Symbol","Transaction","Quantity","OrderType","Price","Product"]];
    orders().forEach(function (o) { rows.push([o.exchange, o.tradingsymbol, o.transaction_type,
      o.quantity, o.order_type, o.price, o.product]); });
    var blob = new Blob([rows.map(function (r) { return r.join(","); }).join("\n")], { type:"text/csv" });
    var a = document.createElement("a");
    a.href = URL.createObjectURL(blob); a.download = "advisor-orders.csv";
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
  });
  el("savePf").addEventListener("click", function () {
    var held = S.plan.lines.map(function (l) {
      return { symbol:l.symbol, qty:l.qty, cost:l.price, stop:l.stop, role:l.role };
    });
    try { localStorage.setItem("holdings", JSON.stringify(held));
      localStorage.setItem("startCapital", String(S.plan.amount));
      alert("Saved. The Portfolio tab now tracks these positions.");
    } catch (e) { alert("Could not save in this browser."); }
    renderPortfolio();
  });

  /* ---------- PORTFOLIO ---------- */
  function renderPortfolio() {
    var held = [], start = 0;
    try {
      held = JSON.parse(localStorage.getItem("holdings") || "[]");
      start = +localStorage.getItem("startCapital") || 0;
    } catch (e) {}
    if (!held.length) {
      el("pfBody").innerHTML = '<div class="notice info">No positions saved yet. Build a plan in ' +
        '<strong>Invest an amount</strong>, and after you place the orders press ' +
        '“I placed these — track them”.</div>';
      return;
    }
    fetchQuotes(held.map(function (h) { return h.symbol; })).then(function (q) {
      var invested = 0, value = 0, atRisk = 0, alerts = [];
      var rows = held.map(function (h) {
        var cur = q[h.symbol] ? q[h.symbol].last : null;
        var val = cur ? h.qty * cur : 0;
        invested += h.qty * h.cost; value += val;
        if (h.stop && cur) {
          if (cur <= h.stop) alerts.push(h.symbol + " closed at " + num(cur, 2) +
            ", below its exit price of " + num(h.stop, 2) + ". The plan says sell.");
          else atRisk += h.qty * (cur - h.stop);
        }
        return { h:h, cur:cur, val:val, gain: cur ? cur / h.cost - 1 : null };
      });
      var cash = Math.max(0, start - invested);
      var total = value + cash;
      el("pfBody").innerHTML =
        alerts.map(function (a) {
          return '<div class="notice err"><span class="k" style="color:var(--down)">Needs a decision</span>' +
            esc(a) + '</div>'; }).join("") +
        '<div class="stats" style="margin-bottom:16px">' +
        stat("What it's worth", inr(total), (total >= start ? "+" : "") + inr(total - start) +
             " since you started", total >= start ? "good" : "bad") +
        stat("Return", pct(start ? total / start - 1 : null), "after " + rows.length + " positions") +
        stat("At risk to exit prices", inr(atRisk), total ? (100 * atRisk / total).toFixed(1) + "% of the portfolio" : "") +
        stat("Cash", inr(cash), "ready to invest") + '</div>' +
        '<div class="card tight"><div class="tablewrap"><table><thead><tr><th>Holding</th>' +
        '<th class="num">Qty</th><th class="num">Cost ₹</th><th class="num">Now ₹</th>' +
        '<th class="num">Value ₹</th><th class="num">Gain</th><th class="num">Room to exit</th>' +
        '<th>What to do</th></tr></thead><tbody>' +
        rows.map(function (r) {
          var below = r.h.stop && r.cur && r.cur <= r.h.stop;
          var room = !r.h.stop ? "—" : below ? "below exit"
            : Math.round(100 * (r.cur - r.h.stop) / r.cur) + "% above";
          return '<tr><td class="sym">' + r.h.symbol + '</td>' +
            '<td class="num">' + num(r.h.qty) + '</td><td class="num">' + num(r.h.cost, 2) + '</td>' +
            '<td class="num">' + num(r.cur, 2) + '</td><td class="num">' + num(r.val) + '</td>' +
            '<td class="num ' + (r.gain >= 0 ? "pos" : "neg") + '">' + pct(r.gain) + '</td>' +
            '<td class="num muted">' + room + '</td>' +
            '<td><span class="pill ' + (below ? "down\">Sell" : "mut\">Hold") + '</span></td></tr>';
        }).join("") +
        '<tr><td class="sym muted">Cash</td><td></td><td></td><td></td>' +
        '<td class="num">' + num(cash) + '</td><td class="num muted">—</td>' +
        '<td class="num muted">—</td><td><span class="pill acc">Ready</span></td></tr>' +
        '</tbody></table></div></div>' +
        '<p class="muted" style="margin-top:12px">Nothing here trades on its own. Every sell and ' +
        'every buy waits for you.</p>';
    });
  }

  /* ---------- boot ---------- */
  fetchQuotes(["^NSEI"]).then(function (m) {
    S.nifty = m["^NSEI"];
    renderRegime();
    var d = new Date();
    el("asof").textContent = "end-of-day data · " + d.toLocaleDateString("en-IN",
      { day:"numeric", month:"short", year:"numeric" });
  }).catch(function () { el("regimeChip").textContent = "offline"; });

  fetchQuotes(UNIVERSE).then(function (m) {
    S.quotes = m;
    renderPicks();
  }).catch(function (e) {
    el("sugRows").innerHTML = '<tr><td colspan="9" class="neg">Data service unreachable: ' +
      esc(e.message) + '</td></tr>';
  });
})();
