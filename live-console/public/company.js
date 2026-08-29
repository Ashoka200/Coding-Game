/* The company page: one page per company, sections in the order the doctrine
   uses — verdict, then what could go wrong, then what it is worth, then the
   business, ownership, news, trend.

   Every section that draws a conclusion carries its reasoning underneath. That
   is the point of this app: no other tool lets you argue with its logic. */
(function () {
  "use strict";

  var C = window.ADV_CHARTS;

  function h(tag, cls, html) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (html != null) n.innerHTML = html;
    return n;
  }
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; });
  }
  /* Money and digit grouping follow the market on screen: rupees in lakh/crore
     grouping, dollars in thousands. The name `inr` is kept because every screen
     already calls it; what it actually means is "money, in the current market". */
  function inr(n, d) {
    var M = window.ADV_MARKETS;
    if (M) return M.money(n, d);
    return n == null || isNaN(n) ? "—" : "₹" + Number(n).toLocaleString("en-IN",
      { maximumFractionDigits: d == null ? 0 : d, minimumFractionDigits: d == null ? 0 : d });
  }
  function num(n, d) {
    var M = window.ADV_MARKETS;
    if (M) return M.number(n, d);
    return n == null || isNaN(n) ? "—" : Number(n).toLocaleString("en-IN",
      { maximumFractionDigits: d == null ? 2 : d, minimumFractionDigits: d == null ? 2 : d });
  }
  function pct(x, d) {
    return x == null || isNaN(x) ? "—"
      : (x >= 0 ? "+" : "") + (x * 100).toFixed(d == null ? 1 : d) + "%";
  }

  /** A gap, shown in place, saying what is missing and why it matters. */
  function gap(what, why) {
    return h("div", "gap", "<b>" + esc(what) + "</b> — " + esc(why));
  }

  /** The reasoning chain, collapsed. The heart of the product. */
  function why(chain, label) {
    if (!chain || !chain.length) return h("span");
    var d = h("details", "why");
    var sum = h("summary", null, esc(label || ("How this was decided — " +
                                               chain.length + " steps")));
    d.appendChild(sum);
    var ol = h("ol", "chain");
    chain.forEach(function (step) {
      var li = h("li", ["Veto", "Resolution", "Conflict"].indexOf(step.stage) >= 0
                       ? "key" : null);
      li.innerHTML = '<span class="stage">' + esc(step.stage) + "</span>" +
                     '<span class="finding">' + esc(step.finding) + "</span>";
      ol.appendChild(li);
    });
    d.appendChild(ol);
    return d;
  }

  function stat(k, v, s, cls) {
    return '<div class="stat ' + (cls || "") + '"><div class="k">' + esc(k) + "</div>" +
           '<div class="v">' + v + '</div><div class="s">' + esc(s || "") + "</div></div>";
  }

  function sectionHead(title, note, infoKey) {
    return '<div class="sectionhead"><h2>' + esc(title) +
           (infoKey ? '<span data-info="' + infoKey + '"></span>' : "") + "</h2>" +
           (note ? '<span class="note">' + esc(note) + "</span>" : "") + "</div>";
  }

  var ACTION_TONE = { SELL: "down", TRIM: "warn", HOLD: "mut", WATCH: "mut",
                      AVOID: "down", ACCUMULATE: "info", BUY: "up" };

  /* ---------------- the header: all four elements, stacked ---------------- */
  function header(d) {
    var q = d.quote, v = d.verdict, holding = d.holding;
    var wrap = h("div", "card");
    var action = (window.ADV_VERDICT.ACTIONS[v.action] || {});
    var day = q && q.prevClose ? q.last / q.prevClose - 1 : null;

    // 1. identity and price
    var top = h("div");
    top.style.cssText = "display:flex;align-items:flex-start;gap:20px;flex-wrap:wrap";
    top.innerHTML =
      '<div style="flex:1;min-width:230px">' +
        "<h1>" + esc(d.name || d.symbol) + "</h1>" +
        '<div class="muted" style="margin-top:2px">' + esc(d.symbol) +
          (d.sectorLabel ? " · " + esc(d.sectorLabel) : "") + "</div>" +
      "</div>" +
      '<div style="text-align:right">' +
        '<div class="mono" style="font-size:30px;font-weight:500" data-live-ltp="' +
          esc(d.symbol) + '">' + num(q.last) + "</div>" +
        '<div style="font-size:13.5px"><span class="' + (day >= 0 ? "pos" : "neg") +
          '" data-live-chg="' + esc(d.symbol) + '">' + pct(day, 2) + "</span> today</div>" +
        '<div class="muted" style="font-size:11px;margin-top:3px" data-live-at="' +
          esc(d.symbol) + '"></div>' +
      "</div>";
    wrap.appendChild(top);

    // 2. the verdict, in a sentence
    var verdictBox = h("div");
    verdictBox.style.cssText = "margin-top:18px;padding-top:18px;border-top:1px solid var(--line)";
    verdictBox.innerHTML =
      '<div class="row" style="margin-bottom:8px">' +
        '<span class="pill ' + (ACTION_TONE[v.action] || "mut") + '" ' +
          'style="font-size:12.5px;padding:6px 14px">' + esc(action.label || v.action) + "</span>" +
        '<span class="muted">conviction ' + v.conviction + "/100</span>" +
        (holding ? '<span class="muted">' + num(holding.qty, 0) + " held at " +
                   num(holding.cost) + "</span>" : "") +
      "</div>" +
      '<p style="font-size:16.5px;margin:0">' + esc(d.verdictSentence) + "</p>" +
      '<p class="muted" style="margin:6px 0 0">' + esc(v.horizon) + "</p>";
    verdictBox.appendChild(why(v.chain));
    wrap.appendChild(verdictBox);

    // 3. the scorecard
    var scores = h("div", "grid g4");
    scores.style.cssText += ";margin-top:18px;padding-top:18px;border-top:1px solid var(--line)";
    scores.innerHTML =
      stat("Valuation", d.valuationLabel, d.valuationNote,
           d.valuationTone) +
      stat("Business quality", d.qualityScore == null ? "—" : d.qualityScore + "/100",
           d.qualityNote, d.qualityTone) +
      stat("Balance sheet", d.creditLabel, d.creditNote, d.creditTone) +
      stat("Ownership", d.ownershipScore == null ? "—" : d.ownershipScore + "/100",
           d.ownershipNote, d.ownershipTone);
    wrap.appendChild(scores);

    // 4. the price chart, with your exit price marked
    var chartBox = h("div");
    chartBox.style.cssText = "margin-top:20px";
    chartBox.appendChild(C.priceChart({
      dates: d.series && d.series.dates, close: d.series && d.series.close,
      sma200: d.series && d.series.sma200,
      exitPrice: holding ? holding.stop : (v.levels ? v.levels.stop : null),
      entryPrice: holding ? holding.cost : null, height: 250,
    }));
    wrap.appendChild(chartBox);
    return wrap;
  }

  /* ---------------- 1. what could go wrong ---------------- */
  function risks(d) {
    var box = h("div");
    box.innerHTML = sectionHead("What could go wrong", "risk before reward");
    var card = h("div", "card");
    var items = (d.credit && d.credit.findings) || [];
    var flags = (d.credit && d.credit.flags) || [];
    var sectorRisks = d.sector ? d.sector.structural : [];

    if (!d.credit) {
      card.appendChild(gap("Balance-sheet screens not run",
        "the statements behind Altman-Z, Beneish-M and the maturity wall were not " +
        "available from any source. Nothing here rules out a credit problem."));
    } else if (!flags.length && items.length) {
      card.innerHTML = '<p>' + esc(items[0]) + "</p>";
    }
    if (flags.length) {
      var list = h("ul");
      list.style.cssText = "margin:0;padding-left:19px";
      items.forEach(function (f) { list.appendChild(h("li", null, esc(f))); });
      card.appendChild(list);
    }
    if (sectorRisks && sectorRisks.length) {
      var sec = h("div");
      sec.style.cssText = "margin-top:16px;padding-top:14px;border-top:1px solid var(--line)";
      sec.innerHTML = '<div class="stat"><div class="k">Structural risks of ' +
        esc(d.sector.label.toLowerCase()) + "</div></div><ul style='margin:8px 0 0;" +
        "padding-left:19px;color:var(--ink-2)'>" +
        sectorRisks.map(function (r) { return "<li>" + esc(r) + "</li>"; }).join("") + "</ul>";
      card.appendChild(sec);
    }
    var notes = h("div", "notice calm");
    notes.innerHTML = "<span class='k'>Not visible in any feed</span>" +
      "Contingent liabilities, pending litigation, customer concentration and " +
      "related-party transactions live in the notes to the accounts. They are where " +
      "most permanent losses begin, and no screen can see them.";
    card.appendChild(notes);
    box.appendChild(card);
    return box;
  }

  /* ---------------- 2. what it is worth ---------------- */
  function worth(d) {
    var box = h("div");
    box.innerHTML = sectionHead("What it is worth", "three lenses, not one");
    var card = h("div", "card");
    var v = d.valuation;
    if (!v || v.fair_value_base == null) {
      card.appendChild(gap("Valuation could not be computed",
        (v && v.unknowns && v.unknowns.length
          ? "missing: " + v.unknowns.map(function (u) { return u.field; }).join(", ")
          : "the inputs a discounted cash flow needs were not available") +
        ". A valuation built on estimated inputs would be a guess with decimal places."));
      box.appendChild(card);
      return box;
    }
    card.appendChild(C.valuationBand({
      price: d.quote.last, low: v.fair_value_low,
      base: v.fair_value_base, high: v.fair_value_high }));
    var summary = h("p");
    summary.style.cssText = "margin-top:14px;font-size:15.5px";
    summary.textContent = v.verdict
      ? "On the numbers available this looks " + v.verdict + "."
      : "A fair-value range was computed, but no verdict follows from it.";
    card.appendChild(summary);
    if (v.implied_growth != null) {
      var rev = h("div", "notice warn");
      rev.innerHTML = "<span class='k'>What the price already assumes</span>" +
        "At " + num(d.quote.last) + " the market is pricing in about <b>" +
        (v.implied_growth * 100).toFixed(1) + "%</b> annual cash-flow growth. " +
        "The question is not whether this company can grow — it is whether it can beat that.";
      card.appendChild(rev);
    }
    (v.lenses || []).forEach(function (lens) {
      if (lens.value_per_share == null) return;
      var row = h("div");
      row.style.cssText = "display:flex;justify-content:space-between;padding:9px 0;" +
                          "border-top:1px solid var(--line);font-size:14px";
      row.innerHTML = "<span>" + esc(lens.name.replace(/_/g, " ")) + "</span>" +
                      '<span class="mono">' + num(lens.value_per_share) + "</span>";
      card.appendChild(row);
    });
    box.appendChild(card);
    return box;
  }

  /* ---------------- 3. the business ---------------- */
  function business(d) {
    var box = h("div");
    box.innerHTML = sectionHead("The business", "what it earns and what it runs on");
    var card = h("div", "card");
    if (d.financials && d.financials.sales) {
      card.appendChild(C.barChart({
        labels: d.financials.periods,
        series: [
          { name: "Sales", values: d.financials.sales, cls: "bar" },
          { name: "Net profit", values: d.financials.profit, cls: "bar-2" },
          { name: "Cash from operations", values: d.financials.cfo, cls: "bar-3" },
        ], height: 200 }));
    } else {
      card.appendChild(gap("No financial history",
        "the statements could not be retrieved, so revenue and profit cannot be shown."));
    }
    if (d.sector) {
      var inputs = h("div", "grid g2");
      inputs.style.cssText += ";margin-top:18px";
      inputs.innerHTML =
        "<div><div class='stat'><div class='k'>What it depends on</div></div>" +
        "<ul style='margin:8px 0 0;padding-left:19px;color:var(--ink-2)'>" +
        d.sector.inputs.map(function (i) { return "<li>" + esc(i) + "</li>"; }).join("") +
        "</ul></div>" +
        "<div><div class='stat'><div class='k'>Government policy that moves it</div></div>" +
        "<ul style='margin:8px 0 0;padding-left:19px;color:var(--ink-2)'>" +
        d.sector.policy.map(function (i) { return "<li>" + esc(i) + "</li>"; }).join("") +
        "</ul></div>";
      card.appendChild(inputs);
    }
    box.appendChild(card);
    return box;
  }

  /* ---------------- 4. who owns it ---------------- */
  function ownership(d) {
    var box = h("div");
    box.innerHTML = sectionHead("Who is buying and selling", "disclosed quarterly", "");
    var card = h("div", "card");
    var o = d.ownership;
    if (!o || !o.holders || !o.holders.length) {
      card.appendChild(gap("Shareholding not available",
        "quarterly disclosures could not be retrieved for this company."));
      box.appendChild(card);
      return box;
    }
    if (d.ownershipSeries) {
      card.appendChild(C.stackChart({
        labels: d.ownershipSeries.quarters, bands: d.ownershipSeries.bands, height: 180 }));
    }
    var findings = h("ul");
    findings.style.cssText = "margin:16px 0 0;padding-left:19px";
    (o.findings || []).forEach(function (f) {
      findings.appendChild(h("li", null, esc(f))); });
    card.appendChild(findings);
    box.appendChild(card);
    return box;
  }

  /* ---------------- 5. news ---------------- */
  function news(d) {
    var box = h("div");
    box.innerHTML = sectionHead("What is being said", d.sentiment
      ? "read by " + (d.sentiment.method === "llm" ? "a language model" : "keyword matching")
      : "");
    var card = h("div", "card flush");
    var items = (d.sentiment && d.sentiment.items) || [];
    if (!items.length) {
      card.style.padding = "22px";
      card.appendChild(gap("No recent coverage",
        "nothing was found in the last fortnight. Absence of news is not evidence " +
        "that nothing is happening."));
      box.appendChild(card);
      return box;
    }
    if (d.sentiment.summary) {
      var sum = h("p");
      sum.style.cssText = "margin:14px 0 4px;font-size:15px";
      sum.textContent = d.sentiment.summary;
      card.appendChild(sum);
    }
    var tbl = h("table");
    tbl.innerHTML = "<tbody>" + items.slice(0, 8).map(function (i) {
      var tone = i.direction <= -2 ? "down" : i.direction >= 2 ? "up"
                 : i.direction ? "warn" : "mut";
      return "<tr><td style='width:120px'><span class='pill " + tone + "'>" +
        esc(i.event || "news") + "</span></td>" +
        "<td style='white-space:normal'>" +
        (i.link ? '<a href="' + esc(i.link) + '" target="_blank" rel="noopener">' +
          esc(i.title) + "</a>" : esc(i.title)) +
        (i.confirmed === false ? " <span class='pill mut'>unconfirmed</span>" : "") +
        "<div class='sub'>" + esc(i.why || "") + "</div></td>" +
        "<td class='num sub'>" + (i.age_days == null ? "" : i.age_days + "d") + "</td></tr>";
    }).join("") + "</tbody>";
    card.appendChild(tbl);
    box.appendChild(card);
    return box;
  }

  /* ---------------- 6. trend and levels ---------------- */
  function trend(d) {
    var box = h("div");
    box.innerHTML = sectionHead("The trend and your levels", "where to act");
    var card = h("div", "card");
    var v = d.verdict, lv = v.levels, q = d.quote;
    var grid = h("div", "grid g4");
    grid.innerHTML =
      stat("Trend", d.stageLabel, "stage " + d.stage + " of 4") +
      stat("Exit price", lv ? num(lv.stop) : "—", "where the reason to own it fails", "bad") +
      stat("First target", lv ? num(lv.target1) : "—", "1.5× your risk", "good") +
      stat("Second target", lv ? num(lv.target2) : "—", "2.5× your risk", "good");
    card.appendChild(grid);
    var detail = h("p", "muted");
    detail.style.cssText = "margin-top:14px";
    detail.textContent = "RSI " + num(q.rsi14, 0) + " · " +
      pct(q.high52 ? q.last / q.high52 - 1 : null) + " from the 52-week high · " +
      "daily range " + (q.atr14 && q.last ? (q.atr14 / q.last * 100).toFixed(1) + "%" : "—") +
      (q.history_bars ? " · " + q.history_bars + " sessions of stored history" : "");
    card.appendChild(detail);
    if (d.forecast && d.forecast.prob_up != null) {
      var f = d.forecast;
      var fc = h("div", "notice info");
      fc.innerHTML = "<span class='k'>What happened last time it looked like this</span>" +
        "In " + f.samples + " past sessions with the same trend, momentum and volatility, " +
        "this was higher " + (f.prob_up * 100).toFixed(0) + "% of the time " +
        (f.horizon_days) + " sessions later (" + (f.ci_low * 100).toFixed(0) + "–" +
        (f.ci_high * 100).toFixed(0) + "% range). The base rate for any stock is " +
        (f.base_rate_prob_up * 100).toFixed(0) + "%. " +
        (f.verdict.indexOf("no edge") === 0
          ? "<b>That is no edge at all</b> — this configuration tells you nothing."
          : "The worst of those cases lost " + Math.abs(f.worst * 100).toFixed(0) + "%.");
      card.appendChild(fc);
    } else if (d.forecast) {
      card.appendChild(gap("No base rate available", d.forecast.verdict ||
        "not enough comparable history to say what usually happens from here."));
    }
    box.appendChild(card);
    return box;
  }

  function render(host, d) {
    host.innerHTML = "";
    host.appendChild(header(d));
    host.appendChild(risks(d));
    host.appendChild(worth(d));
    host.appendChild(business(d));
    host.appendChild(ownership(d));
    host.appendChild(news(d));
    host.appendChild(trend(d));
    if (window.ADV_INFO) window.ADV_INFO.decorate(host);
  }

  window.ADV_COMPANY = { render: render, why: why, gap: gap, stat: stat,
                         esc: esc, inr: inr, num: num, pct: pct, h: h };
})();
