/* Runs the verdict engine over holdings or any symbol, and renders the news feed. */
(function () {
  "use strict";
  function el(id) { return document.getElementById(id); }
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
    return { "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;" }[c]; }); }
  function num(n, d) { return n == null || isNaN(n) ? "—" :
    Number(n).toLocaleString("en-IN", { maximumFractionDigits: d == null ? 2 : d,
                                        minimumFractionDigits: d == null ? 2 : d }); }

  function getJSON(u) { return fetch(u).then(function (r) { return r.json(); }); }

  function stageOf(q) {
    if (!q || q.sma200 == null) return 1;
    if (q.last > q.sma200 && q.sma200Rising && q.sma50 != null && q.last > q.sma50) return 2;
    if (q.last < q.sma200 && !q.sma200Rising) return 4;
    return q.sma200Rising ? 1 : 3;
  }
  function clamp(x, a, b) { return Math.max(a, Math.min(b, x)); }
  /* same weights as the Fundamentals tab, kept local so this file stands alone */
  function fundScore(f) {
    if (!f || f.error) return null;
    var s = 0, known = 0;
    var prof = f.roe != null ? f.roe : f.roce;
    if (prof != null) { s += clamp(prof / 0.20, 0, 1) * 20; known++; } else s += 10;
    if (f.opMargin != null) { s += clamp(f.opMargin / 0.20, 0, 1) * 10; known++; } else s += 5;
    if (f.debtToEquity != null) { s += clamp(1 - f.debtToEquity / 2, 0, 1) * 10; known++; } else s += 5;
    if (f.revenueGrowth != null) { s += clamp(f.revenueGrowth / 0.15, 0, 1) * 12.5; known++; } else s += 6.25;
    if (f.earningsGrowth != null) { s += clamp(f.earningsGrowth / 0.15, 0, 1) * 12.5; known++; } else s += 6.25;
    if (f.pe != null && f.pe > 0) { s += clamp((60 - f.pe) / 45, 0, 1) * 15; known++; } else s += 7.5;
    if (f.evEbitda != null && f.evEbitda > 0) { s += clamp((30 - f.evEbitda) / 22, 0, 1) * 10; known++; } else s += 5;
    if (f.currentRatio != null) { s += clamp((f.currentRatio - 0.8) / 1.2, 0, 1) * 10; known++; }
    else if (f.interestCover != null) { s += clamp((f.interestCover - 1) / 5, 0, 1) * 10; known++; }
    else s += 5;
    return known >= 3 ? Math.round(s) : null;   // too little known to call it a score
  }

  function assess(symbols, holdingsMap) {
    var status = el("adviceStatus");
    status.innerHTML = '<span class="spin"></span>Gathering evidence…';
    return Promise.all([
      getJSON("/api/quotes?symbols=" + encodeURIComponent(symbols.concat(["^NSEI"]).join(","))),
      getJSON("/api/fundamentals?symbols=" + encodeURIComponent(symbols.join(","))),
      Promise.all(symbols.map(function (s) {
        return getJSON("/api/news?symbol=" + encodeURIComponent(s))
          .catch(function () { return { symbol: s, error: "unavailable", items: [] }; });
      }))
    ]).then(function (res) {
      var qmap = {}; (res[0].quotes || []).forEach(function (q) { if (!q.error) qmap[q.symbol] = q; });
      var fmap = {}; (res[1].fundamentals || []).forEach(function (f) { fmap[f.symbol] = f; });
      var nmap = {}; res[2].forEach(function (n) { nmap[n.symbol] = n; });
      var nifty = qmap["^NSEI"];
      var riskOn = nifty && nifty.sma200 != null ? nifty.last > nifty.sma200 : true;

      var verdicts = symbols.map(function (s) {
        var q = qmap[s];
        if (!q) return null;
        var f = fmap[s];
        return window.ADV_VERDICT.decide({
          symbol: s, quote: q, fundamentals: f && !f.error ? f : null,
          fundScore: fundScore(f), news: nmap[s], stage: stageOf(q),
          regimeRiskOn: riskOn, held: holdingsMap ? holdingsMap[s] : null
        });
      }).filter(Boolean);

      status.textContent = "";
      return { verdicts: verdicts, fundNote: res[1], riskOn: riskOn, quotes: qmap };
    });
  }

  function render(out, holdingsMap) {
    var order = window.ADV_VERDICT.ACTIONS;
    var vs = out.verdicts.slice().sort(function (a, b) {
      return (order[a.action] || {}).order - (order[b.action] || {}).order; });
    var urgent = vs.filter(function (v) { return v.action === "SELL" || v.action === "TRIM"; });

    var html = "";
    if (!out.riskOn) html += '<div class="notice warnn"><span class="k">Market conditions</span>' +
      'The market is below its long-term average. New buying is restrained across every verdict ' +
      'below — this is the playbook, not a forecast.</div>';
    if (urgent.length) html += '<div class="notice err"><span class="k" style="color:var(--down)">' +
      'Needs a decision today</span>' + urgent.map(function (v) {
        return esc(v.symbol) + " — " + (order[v.action] || {}).label.toLowerCase(); }).join("; ") + '.</div>';

    var fd = out.fundNote;
    if (fd && (!fd.sources || !fd.sources.length)) {
      html += '<div class="notice info"><strong>No financial source answered.</strong> Verdicts ' +
        'below are based on price, trend and news only, and cannot be long-term calls.' +
        (fd.diagnostics && fd.diagnostics.length
          ? '<details style="margin-top:8px"><summary style="cursor:pointer">Why (' +
            fd.diagnostics.length + ' attempts)</summary><ul style="margin:8px 0 0;padding-left:18px">' +
            fd.diagnostics.map(function (d) { return "<li>" + esc(d) + "</li>"; }).join("") +
            '</ul></details>' : "") + '</div>';
    } else if (fd && fd.sources) {
      html += '<p class="muted">Financials from ' + esc(fd.sources.join(", ")) + '.</p>';
    }

    html += vs.map(function (v) {
      var h = holdingsMap && holdingsMap[v.symbol];
      var extra = h && h.qty ? num(h.qty, 0) + " held at " + num(h.cost) : "";
      return window.ADV_VERDICT.card(v, extra);
    }).join("");
    el("adviceBody").innerHTML = html || '<div class="notice info">No verdicts produced.</div>';
  }

  el("runHoldings").addEventListener("click", function () {
    var held = [];
    try { held = JSON.parse(localStorage.getItem("holdings") || "[]"); } catch (e) {}
    if (!held.length) {
      el("adviceBody").innerHTML = '<div class="notice info">No saved positions. Build a plan in ' +
        '<strong>Invest an amount</strong> and mark it placed, or check a single symbol above.</div>';
      return;
    }
    var total = 0, map = {};
    held.forEach(function (h) { total += h.qty * h.cost; });
    held.forEach(function (h) {
      map[h.symbol] = { qty: h.qty, cost: h.cost, stop: h.stop,
                        weight: total ? (h.qty * h.cost) / total : null };
    });
    assess(held.map(function (h) { return h.symbol; }), map)
      .then(function (out) { render(out, map); })
      .catch(function (e) { el("adviceStatus").textContent = "Failed: " + e.message; });
  });

  el("runOne").addEventListener("click", function () {
    var s = (el("adviceSym").value || "").trim().toUpperCase();
    if (!s) return;
    assess([s], null).then(function (out) { render(out, null); })
      .catch(function (e) { el("adviceStatus").textContent = "Failed: " + e.message; });
  });

  /* ---------- news tab ---------- */
  function renderNews(d, label) {
    var st = el("newsStatus"); st.textContent = "";
    if (d.error) {
      el("newsBody").innerHTML = '<div class="notice err"><strong>News unavailable.</strong> ' +
        esc(d.detail || "") + '</div>';
      return;
    }
    var p = d.pressure || {};
    var toneCls = p.tone === "positive" ? "up" : p.tone === "negative" ? "down" : "mut";
    el("newsBody").innerHTML =
      '<div class="stats" style="margin-bottom:16px">' +
      '<div class="stat"><div class="k">Coverage</div><div class="v">' + (d.items || []).length +
      '</div><div class="s">items for ' + esc(label) + '</div></div>' +
      '<div class="stat ' + (p.tone === "negative" ? "bad" : p.tone === "positive" ? "good" : "") +
      '"><div class="k">Net tone</div><div class="v" style="font-size:19px">' +
      '<span class="pill ' + toneCls + '">' + esc(p.tone || "—") + '</span></div>' +
      '<div class="s">recency-weighted, score ' + (p.net == null ? "—" : p.net) + '</div></div>' +
      '<div class="stat ' + (d.materialCount ? "warnb" : "") + '"><div class="k">Material events</div>' +
      '<div class="v">' + (d.materialCount || 0) + '</div>' +
      '<div class="s">strong enough to change a decision</div></div></div>' +
      '<div class="card tight"><div class="tablewrap"><table><thead><tr>' +
      '<th>Event</th><th>Headline</th><th>Source</th><th class="num">Age</th></tr></thead><tbody>' +
      (d.items || []).map(function (i) {
        var cls = i.weight <= -2 ? "down" : i.weight >= 2 ? "up" : i.weight ? "warn" : "mut";
        return '<tr><td><span class="pill ' + cls + '">' + esc(i.eventLabel) + '</span></td>' +
          '<td style="white-space:normal;max-width:520px"><a href="' + esc(i.link) +
          '" target="_blank" rel="noopener">' + esc(i.title) + '</a></td>' +
          '<td class="muted">' + esc(i.source) + '</td>' +
          '<td class="num muted">' + (i.ageDays == null ? "—" : i.ageDays + "d") + '</td></tr>';
      }).join("") + '</tbody></table></div></div>' +
      '<p class="muted" style="margin-top:12px">Headlines are third-party reporting, not verified ' +
      'fact. The advisor weights them by event type and recency; it never acts on a headline alone.</p>';
  }

  el("loadMarketNews").addEventListener("click", function () {
    el("newsStatus").innerHTML = '<span class="spin"></span>Loading…';
    getJSON("/api/news?market=1").then(function (d) { renderNews(d, "the market"); })
      .catch(function (e) { el("newsStatus").textContent = "Failed: " + e.message; });
  });
  el("loadStockNews").addEventListener("click", function () {
    var s = (el("newsSym").value || "").trim().toUpperCase();
    if (!s) return;
    el("newsStatus").innerHTML = '<span class="spin"></span>Loading…';
    getJSON("/api/news?symbol=" + encodeURIComponent(s))
      .then(function (d) { renderNews(d, s); })
      .catch(function (e) { el("newsStatus").textContent = "Failed: " + e.message; });
  });
})();
