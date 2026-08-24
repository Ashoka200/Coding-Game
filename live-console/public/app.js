/* Router and screens. Home leads with what needs a decision; on a quiet day it
   says so plainly and then offers something worth reading rather than
   manufacturing urgency. */
(function () {
  "use strict";

  var U = window.ADV_COMPANY;          // shared helpers
  var C = window.ADV_CHARTS;
  var h = U.h, esc = U.esc, inr = U.inr, num = U.num, pct = U.pct;

  var UNIVERSE = ["RELIANCE","TCS","HDFCBANK","ICICIBANK","INFY","LT","BHARTIARTL",
    "ITC","SBIN","TITAN","SUNPHARMA","AXISBANK","MARUTI","ASIANPAINT","BAJFINANCE",
    "HCLTECH","ULTRACEMCO","NESTLEIND","KOTAKBANK","TATAMOTORS","TATASTEEL","WIPRO"];
  var CORE = [{ symbol:"NIFTYBEES", desc:"Nifty 50 index fund", share:0.70 },
              { symbol:"JUNIORBEES", desc:"Nifty Next 50 index fund", share:0.30 }];
  var PROFILES = {
    careful:   { mix:[0.70,0.15,0.15], maxPos:0.05, stopMult:2.5, names:4 },
    balanced:  { mix:[0.60,0.30,0.10], maxPos:0.08, stopMult:2.0, names:5 },
    ambitious: { mix:[0.50,0.40,0.10], maxPos:0.12, stopMult:2.0, names:6 },
  };
  var S = { quotes:{}, nifty:null, riskOn:true, regime:null, plan:null,
            amount:1000000, profile:"balanced" };

  function el(id) { return document.getElementById(id); }
  function getJSON(u) { return fetch(u).then(function (r) { return r.json(); }); }
  function holdings() {
    try { return JSON.parse(localStorage.getItem("holdings") || "[]"); }
    catch (e) { return []; }
  }
  function startCapital() {
    try { return +localStorage.getItem("startCapital") || 0; } catch (e) { return 0; }
  }
  function clamp(x, a, b) { return Math.max(a, Math.min(b, x)); }

  function stageOf(q) {
    if (!q || q.sma200 == null) return 1;
    if (q.last > q.sma200 && q.sma200Rising && q.sma50 != null && q.last > q.sma50) return 2;
    if (q.last < q.sma200 && !q.sma200Rising) return 4;
    return q.sma200Rising ? 1 : 3;
  }
  var STAGE_LABEL = { 2:"Uptrend", 1:"Basing", 3:"Topping", 4:"Downtrend" };

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
    s += f.evEbitda != null ? clamp((30 - f.evEbitda) / 22, 0, 1) * 10 : 5;
    s += f.interestCover != null ? clamp((f.interestCover - 1) / 5, 0, 1) * 10 : 5;
    return known >= 3 ? Math.round(s) : null;
  }

  /* ---------------- routing ---------------- */
  var current = "home";
  function show(name) {
    current = name;
    ["home", "company", "invest", "portfolio"].forEach(function (n) {
      el("s-" + n).classList.toggle("on", n === name);
    });
    document.querySelectorAll("nav button").forEach(function (b) {
      if (b.dataset.nav === name) b.setAttribute("aria-current", "page");
      else b.removeAttribute("aria-current");
    });
    window.scrollTo({ top: 0, behavior: "smooth" });
  }
  document.querySelectorAll("nav button").forEach(function (b) {
    b.addEventListener("click", function () {
      show(b.dataset.nav);
      if (b.dataset.nav === "portfolio") renderPortfolio();
      if (b.dataset.nav === "invest") renderInvest();
      if (b.dataset.nav === "home") renderHome();
    });
  });
  el("brand").addEventListener("click", function () { show("home"); renderHome(); });

  var list = el("symlist");
  UNIVERSE.forEach(function (s) {
    var o = document.createElement("option"); o.value = s; list.appendChild(o);
  });
  el("lookup").addEventListener("keydown", function (ev) {
    if (ev.key === "Enter") openCompany(el("lookup").value.trim().toUpperCase());
  });
  el("lookup").addEventListener("change", function () {
    var v = el("lookup").value.trim().toUpperCase();
    if (v) openCompany(v);
  });

  /* ---------------- home ---------------- */
  function alarmsFor(quotes) {
    var held = holdings(), out = [];
    held.forEach(function (pos) {
      var q = quotes[pos.symbol];
      if (!q || !pos.stop) return;
      if (q.last <= pos.stop) {
        out.push({ pos: pos, quote: q,
                   value: pos.qty * q.last,
                   below: (pos.stop - q.last) / pos.stop });
      }
    });
    return out;
  }

  /* The desk note: the day's letterhead. It states the date and the two facts
     that condition everything below it — where the index stands, and what the
     regime machine calls that. Never a slogan; if there is nothing to say the
     panel simply carries the date. */
  function deskHead() {
    var n = S.nifty, day = n && n.prevClose ? n.last / n.prevClose - 1 : null;
    var when = new Date().toLocaleDateString("en-IN",
      { weekday:"long", day:"numeric", month:"long", year:"numeric" });
    var pulse = "";
    if (n && n.last != null) {
      pulse += '<div><div class="k">Nifty 50</div>' +
        '<div class="v" data-live-ltp="NIFTY50">' + num(n.last) + "</div></div>";
      if (day != null) {
        pulse += '<div><div class="k">Today</div><div class="v ' +
          (day >= 0 ? "up" : "down") + '" data-live-chg="NIFTY50">' +
          pct(day, 2) + "</div></div>";
      }
    }
    if (S.regime) {
      pulse += '<div><div class="k">Regime</div><div class="v">' +
        esc(S.regime) + "</div></div>";
    }
    return '<div class="deskhead"><div class="watermark" aria-hidden="true">' +
      '<svg viewBox="0 0 24 24"><path fill="#C9A24D" d="M12 1.6l2.3 6.6 6.9.3-5.4 4.3' +
      ' 1.9 6.7L12 15.7 6.3 19.5l1.9-6.7-5.4-4.3 6.9-.3z"/></svg></div>' +
      '<div class="left"><div class="eyebrow">Astraveda desk note</div>' +
      "<h1>Today</h1>" + '<div class="when">' + esc(when) + "</div></div>" +
      (pulse ? '<div class="pulse">' + pulse + "</div>" : "") + "</div>";
  }

  function renderHome() {
    var host = el("s-home");
    if (!Object.keys(S.quotes).length) {
      host.innerHTML = deskHead() + '<p class="lede"><span class="spin"></span>' +
        "Reading the market…</p>";
      return;
    }
    var held = holdings();
    var alarms = alarmsFor(S.quotes);
    var out = deskHead();

    // 1. the loud part — reserved for a breached exit price on something you own
    var alarmHtml = alarms.map(function (a) {
      return '<div class="alarm"><div class="mark">!</div><div class="body">' +
        "<h2>" + esc(a.pos.symbol) + " has fallen below your exit price</h2>" +
        "<p style='margin:0'>It last traded at <b class='mono'>" + num(a.quote.last) +
        "</b>, under the <b class='mono'>" + num(a.pos.stop) + "</b> you set when you " +
        "bought. The plan says sell — that decision was made when you were calm, and " +
        "this is only the execution. About <b>" + inr(a.value) + "</b> returns to cash.</p>" +
        '<div class="act"><button class="primary danger" data-sell="' + esc(a.pos.symbol) +
        '">Prepare the sell order</button>' +
        '<button class="ghost" data-open="' + esc(a.pos.symbol) + '">See why</button>' +
        "</div></div></div>";
    }).join("");

    // 2. quieter things that still want attention
    var attention = [];
    var total = held.reduce(function (t, p) {
      var q = S.quotes[p.symbol]; return t + (q ? p.qty * q.last : 0); }, 0);
    held.forEach(function (p) {
      var q = S.quotes[p.symbol];
      if (!q) return;
      var weight = total ? (p.qty * q.last) / total : 0;
      if (weight > 0.15) {
        attention.push({ symbol: p.symbol,
          text: "is " + (weight * 100).toFixed(0) + "% of the portfolio, past the 15% " +
                "concentration limit. Trimming is the disciplined move." });
      }
      if (p.stop && q.last > p.stop && (q.last - p.stop) / q.last < 0.04) {
        attention.push({ symbol: p.symbol,
          text: "is within 4% of its exit price. Nothing to do yet — but decide now what " +
                "you will do if it gets there, rather than in the moment." });
      }
    });

    if (!alarms.length && !attention.length) {
      out += '<p class="lede">Nothing needs your attention today.</p>';
    } else {
      out += '<p class="lede">' + (alarms.length ? alarms.length + " position" +
        (alarms.length > 1 ? "s need" : " needs") + " a decision." :
        attention.length + " thing" + (attention.length > 1 ? "s are" : " is") +
        " worth a look.") + "</p>";
    }
    out += alarmHtml;

    if (attention.length) {
      out += '<div class="card"><h2>Worth a look</h2>' + attention.map(function (a) {
        return "<p style='margin:0 0 10px'><b>" + esc(a.symbol) + "</b> " +
               esc(a.text) + "</p>"; }).join("") + "</div>";
    }

    // 3. the portfolio, if there is one
    if (held.length) {
      var start = startCapital();
      var invested = held.reduce(function (t, p) { return t + p.qty * p.cost; }, 0);
      var cash = Math.max(0, start - invested);
      var value = total + cash;
      out += sectionHead("Your portfolio") +
        '<div class="card"><div class="grid g4">' +
        U.stat("Worth today", inr(value),
               start ? (value >= start ? "+" : "") + inr(value - start) + " since you started" : "",
               value >= start ? "good" : "bad") +
        U.stat("Return", start ? pct(value / start - 1) : "—", held.length + " positions") +
        U.stat("Cash", inr(cash), "ready to invest") +
        U.stat("Positions at risk", String(alarms.length), "below their exit price",
               alarms.length ? "bad" : "") +
        "</div></div>";
    }

    // 4. today's ideas — only when the market allows it
    var scored = UNIVERSE.map(function (s) { return S.quotes[s]; }).filter(Boolean)
      .map(function (q) { return { q: q, stage: stageOf(q) }; })
      .filter(function (x) { return x.stage === 2; })
      .sort(function (a, b) { return (b.q.mom6m || 0) - (a.q.mom6m || 0); })
      .slice(0, 5);

    out += sectionHead("Ideas today", S.riskOn
      ? "in an uptrend, ranked by momentum"
      : "withheld — the market is below its long-term average");
    if (!S.riskOn) {
      out += '<div class="notice warn"><span class="k">Market conditions</span>' +
        "The index is below its 200-day average, so new buy ideas are withheld. Most " +
        "breakouts fail in weak markets, and the discipline of not buying is worth more " +
        "than any single idea.</div>";
    } else if (!scored.length) {
      out += '<div class="notice calm">Nothing in the watch universe is in a clean ' +
        "uptrend today. A forced trade is worse than no trade.</div>";
    } else {
      out += '<div class="card flush"><table><thead><tr><th>Company</th>' +
        '<th class="num">Price</th><th class="num">Today</th><th class="num">6 months</th>' +
        '<th class="num">From high</th><th>Shape</th></tr></thead><tbody>' +
        scored.map(function (x) {
          var q = x.q, day = q.prevClose ? q.last / q.prevClose - 1 : null;
          return '<tr class="go" data-open="' + esc(q.symbol) + '">' +
            '<td class="sym">' + esc(q.symbol) + "</td>" +
            '<td class="num" data-live-ltp="' + esc(q.symbol) + '">' + num(q.last) + "</td>" +
            '<td class="num ' + (day >= 0 ? "pos" : "neg") + '" data-live-chg="' +
              esc(q.symbol) + '">' + pct(day, 2) + "</td>" +
            '<td class="num ' + (q.mom6m >= 0 ? "pos" : "neg") + '">' + pct(q.mom6m) + "</td>" +
            '<td class="num">' + pct(q.high52 ? q.last / q.high52 - 1 : null) + "</td>" +
            '<td data-spark="' + esc(q.symbol) + '"></td></tr>';
        }).join("") + "</tbody></table></div>";
    }

    // 5. something to read
    out += sectionHead("Worth reading", "market context");
    out += '<div class="card" id="marketNews"><p class="muted">' +
      '<span class="spin"></span>Loading the market brief…</p></div>';

    host.innerHTML = out;
    wireHome(host);
    loadMarketNews();
  }

  function sectionHead(t, note) {
    return '<div class="sectionhead"><h2>' + esc(t) + "</h2>" +
           (note ? '<span class="note">' + esc(note) + "</span>" : "") + "</div>";
  }

  function wireHome(host) {
    host.querySelectorAll("[data-open]").forEach(function (n) {
      n.addEventListener("click", function () { openCompany(n.dataset.open); });
    });
    host.querySelectorAll("[data-sell]").forEach(function (n) {
      n.addEventListener("click", function (ev) {
        ev.stopPropagation();
        var sym = n.dataset.sell, pos = holdings().filter(function (p) {
          return p.symbol === sym; })[0];
        var q = S.quotes[sym];
        if (!pos || !q) return;
        var rows = [["Exchange","Symbol","Transaction","Quantity","OrderType","Price","Product"],
                    ["NSE", sym, "SELL", pos.qty, "MARKET", "", "CNC"]];
        var blob = new Blob([rows.map(function (r) { return r.join(","); }).join("\n")],
                            { type: "text/csv" });
        var a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = "sell-" + sym + ".csv";
        document.body.appendChild(a); a.click(); document.body.removeChild(a);
      });
    });
    host.querySelectorAll("[data-spark]").forEach(function (cell) {
      var q = S.quotes[cell.dataset.spark];
      if (q && q.history_bars) {
        cell.appendChild(C.sparkline([q.sma200, q.sma50, q.last]));
      }
    });
  }

  function loadMarketNews() {
    getJSON("/api/news?market=1").then(function (d) {
      var box = el("marketNews");
      if (!box) return;
      if (d.error || !(d.items || []).length) {
        box.innerHTML = "<p class='muted'>The news feed could not be reached, so there " +
          "is nothing to read here today.</p>";
        return;
      }
      box.innerHTML = "<p class='muted' style='margin-bottom:14px'>What is moving " +
        "Indian markets, most significant first.</p>" +
        d.items.slice(0, 6).map(function (i) {
          var tone = i.weight <= -2 ? "down" : i.weight >= 2 ? "up" : "mut";
          return "<div style='padding:10px 0;border-top:1px solid var(--line)'>" +
            "<span class='pill " + tone + "'>" + esc(i.eventLabel) + "</span> " +
            "<a href='" + esc(i.link) + "' target='_blank' rel='noopener'>" +
            esc(i.title) + "</a></div>";
        }).join("");
    }).catch(function () {});
  }

  /* ---------------- company ---------------- */
  function openCompany(symbol) {
    if (!symbol) return;
    show("company");
    var host = el("s-company");
    host.innerHTML = '<h1>' + esc(symbol) + '</h1><p class="lede"><span class="spin">' +
      "</span>Gathering everything known about this company…</p>";

    Promise.all([
      getJSON("/api/quotes?symbols=" + encodeURIComponent(symbol)),
      getJSON("/api/history?symbol=" + encodeURIComponent(symbol) + "&range=5y")
        .catch(function () { return null; }),
      getJSON("/api/fundamentals?symbols=" + encodeURIComponent(symbol))
        .catch(function () { return null; }),
      getJSON("/api/news?symbol=" + encodeURIComponent(symbol))
        .catch(function () { return null; }),
      getJSON("/api/deepdive?symbol=" + encodeURIComponent(symbol))
        .catch(function () { return null; }),
      getJSON("/api/ownership?symbol=" + encodeURIComponent(symbol))
        .catch(function () { return null; }),
    ]).then(function (res) {
      var q = ((res[0] || {}).quotes || []).filter(function (x) {
        return x.symbol === symbol && !x.error; })[0];
      if (!q) {
        host.innerHTML = "<h1>" + esc(symbol) + "</h1>" +
          '<div class="notice warn"><span class="k">No data</span>' +
          "Nothing could be retrieved for this symbol. Check the spelling, or the " +
          "data sources may be refusing requests right now.</div>";
        return;
      }
      host.innerHTML = "";
      U.render(host, assemble(symbol, q, res));
      host.querySelectorAll("[data-open]").forEach(function (n) {
        n.addEventListener("click", function () { openCompany(n.dataset.open); });
      });
    }).catch(function (e) {
      host.innerHTML = "<h1>" + esc(symbol) + "</h1>" +
        '<div class="notice warn">Could not load: ' + esc(e.message) + "</div>";
    });
  }

  function assemble(symbol, q, res) {
    var hist = res[1], fundRes = res[2], newsRes = res[3];
    var deep = res[4], own = res[5];
    var f = ((fundRes || {}).fundamentals || []).filter(function (x) {
      return x.symbol === symbol && !x.error; })[0] || null;
    var score = fundScore(f);
    var stage = stageOf(q);

    // sentiment from the news items we have
    var sentiment = null;
    if (newsRes && (newsRes.items || []).length) {
      var items = newsRes.items.map(function (i) {
        return { title: i.title, direction: i.weight, materiality: Math.abs(i.weight) >= 2 ? 0.7 : 0.3,
                 event: i.event, confirmed: true, about_company: true,
                 why: i.eventLabel, age_days: i.ageDays, link: i.link }; });
      sentiment = { method: "keywords", items: items,
                    summary: newsRes.pressure ? "Coverage reads " +
                      newsRes.pressure.tone + " overall." : null };
    }

    var holdingRec = holdings().filter(function (p) { return p.symbol === symbol; })[0];
    var v = window.ADV_VERDICT.decide({
      symbol: symbol, quote: q, fundamentals: f, fundScore: score,
      news: newsRes, stage: stage, regimeRiskOn: S.riskOn,
      held: holdingRec ? { qty: holdingRec.qty, cost: holdingRec.cost,
                           stop: holdingRec.stop } : null });

    // series for the price chart
    var series = null;
    if (hist && hist.close && hist.close.length) {
      var close = hist.close.filter(function (x) { return x != null; });
      var sma200 = close.map(function (_, i) {
        if (i < 199) return null;
        var sum = 0;
        for (var j = i - 199; j <= i; j++) sum += close[j];
        return sum / 200;
      });
      series = { dates: (hist.timestamps || []).map(function (t) {
                   return new Date(t * 1000).toISOString().slice(0, 10); }),
                 close: close, sma200: sma200 };
    }

    // financial history for the bar chart
    var financials = null;
    if (deep && deep.profitLoss && deep.profitLoss.rows) {
      var rows = deep.profitLoss.rows;
      var pick = function (names) {
        var keys = Object.keys(rows);
        for (var i = 0; i < names.length; i++) {
          for (var j = 0; j < keys.length; j++) {
            if (keys[j].toLowerCase().indexOf(names[i]) === 0) return rows[keys[j]];
          }
        }
        return null;
      };
      var cfoRows = deep.cashFlow && deep.cashFlow.rows ? deep.cashFlow.rows : {};
      var cfoKey = Object.keys(cfoRows).filter(function (k) {
        return k.toLowerCase().indexOf("cash from operating") === 0; })[0];
      financials = { periods: deep.profitLoss.periods,
                     sales: pick(["sales", "revenue"]),
                     profit: pick(["net profit"]),
                     cfo: cfoKey ? cfoRows[cfoKey] : null };
    }

    // ownership
    var ownRead = null, ownSeries = null;
    if (own && own.shareholding && own.shareholding.rows) {
      var shRows = own.shareholding.rows;
      ownRead = { holders: [], findings: [] };
      var find = function (needle) {
        var k = Object.keys(shRows).filter(function (x) {
          return x.toLowerCase().indexOf(needle) >= 0; })[0];
        return k ? shRows[k] : null;
      };
      var bands = [
        { name: "Promoters", values: find("promoter"), cls: "band-a" },
        { name: "Foreign institutions", values: find("fii"), cls: "band-b" },
        { name: "Domestic institutions", values: find("dii"), cls: "band-c" },
        { name: "Public", values: find("public"), cls: "band-d" },
      ].filter(function (b) { return b.values; });
      if (bands.length) {
        ownSeries = { quarters: own.shareholding.quarters, bands: bands };
        ownRead.holders = bands.map(function (b) {
          var vals = b.values.filter(function (x) { return x != null; });
          return { name: b.name, latest: vals[vals.length - 1] };
        });
        ownRead.findings = ownRead.holders.map(function (hd) {
          return hd.name + " hold " + num(hd.latest, 1) + "%.";
        });
      }
    }

    var sector = window.ADV_SECTORS ? window.ADV_SECTORS.forSymbol(symbol, deep && deep.name)
                                    : null;
    var valuationLabel = f && f.pe ? num(f.pe, 1) + "×" : "—";

    return {
      symbol: symbol, name: (deep && deep.name) || (f && f.name) || symbol,
      quote: q, verdict: v, series: series, financials: financials,
      sentiment: sentiment, ownership: ownRead, ownershipSeries: ownSeries,
      sector: sector, sectorLabel: sector ? sector.label : null,
      stage: stage, stageLabel: STAGE_LABEL[stage],
      holding: holdingRec ? { qty: holdingRec.qty, cost: holdingRec.cost,
                              stop: holdingRec.stop } : null,
      verdictSentence: sentence(v, q, f, score, stage),
      valuation: null,
      valuationLabel: valuationLabel,
      valuationNote: f && f.pe ? "price to earnings" : "no earnings data",
      valuationTone: f && f.pe ? (f.pe < 20 ? "good" : f.pe > 55 ? "bad" : "") : "",
      qualityScore: score,
      qualityNote: score == null ? "financials unavailable" : "quality, growth, value",
      qualityTone: score == null ? "" : score >= 70 ? "good" : score < 45 ? "bad" : "",
      creditLabel: f && f.debtToEquity != null ? num(f.debtToEquity, 2) + "×" : "—",
      creditNote: f && f.debtToEquity != null ? "debt to equity" : "not available",
      creditTone: f && f.debtToEquity != null
        ? (f.debtToEquity > 1.5 ? "bad" : "good") : "",
      credit: null,
      ownershipScore: null,
      ownershipNote: ownRead ? "disclosed quarterly" : "not available",
      ownershipTone: "",
      forecast: null,
    };
  }

  function sentence(v, q, f, score, stage) {
    var action = (window.ADV_VERDICT.ACTIONS[v.action] || {}).label || v.action;
    var bits = [action + "."];
    if (score != null) {
      bits.push(score >= 70 ? "The business is strong on the numbers available"
        : score >= 55 ? "The business is sound"
        : score >= 45 ? "The business is mixed" : "The business is weak on the numbers");
    } else {
      bits.push("No financials were available, so this rests on price and trend alone");
    }
    if (f && f.pe) {
      bits[bits.length - 1] += f.pe < 20 ? " and the price is undemanding"
        : f.pe > 55 ? " and the price already assumes a great deal" : " and fairly priced";
    }
    bits.push(stage === 2 ? "and the trend is with it."
      : stage === 4 ? "but the trend is against it."
      : "and the trend is unsettled.");
    return bits.join(" ").replace(" .", ".");
  }

  /* ---------------- invest and portfolio (kept, restyled) ---------------- */
  function renderInvest() {
    var host = el("s-invest");
    if (host.dataset.built) return;
    host.dataset.built = "1";
    host.innerHTML = "<h1>Invest an amount</h1>" +
      '<p class="lede">Tell the advisor how much, and it builds a complete plan — what ' +
      "to buy, how much of each, and the exit price for every holding. Nothing is " +
      "bought until you approve it.</p>" +
      '<div class="card"><div class="stat"><div class="k">Amount</div></div>' +
      '<div style="display:flex;align-items:baseline;gap:8px;border-bottom:2px solid ' +
      'var(--accent);padding-bottom:8px;margin:8px 0 16px">' +
      '<span class="mono" style="font-size:24px;color:var(--muted)">₹</span>' +
      '<input id="amt" class="mono" style="flex:1;font-size:30px;border:none;' +
      'background:none;color:var(--ink);padding:0;width:100%" value="10,00,000"></div>' +
      '<div class="row" style="margin-bottom:18px">' +
      ["careful","balanced","ambitious"].map(function (p) {
        return '<button class="ghost" data-prof="' + p + '"' +
          (p === "balanced" ? ' style="border-color:var(--ink)"' : "") + ">" +
          p.charAt(0).toUpperCase() + p.slice(1) + "</button>"; }).join("") +
      "</div>" +
      '<button class="primary" id="buildPlan">Build my plan</button>' +
      '<div id="planOut" style="margin-top:18px"></div></div>';

    host.querySelectorAll("[data-prof]").forEach(function (b) {
      b.addEventListener("click", function () {
        S.profile = b.dataset.prof;
        host.querySelectorAll("[data-prof]").forEach(function (x) {
          x.style.borderColor = x === b ? "var(--ink)" : ""; });
      });
    });
    el("amt").addEventListener("input", function () {
      var v = parseInt(el("amt").value.replace(/[^0-9]/g, ""), 10) || 0;
      S.amount = v;
      el("amt").value = v ? v.toLocaleString("en-IN") : "";
    });
    el("buildPlan").addEventListener("click", buildPlan);
  }

  function buildPlan() {
    var out = el("planOut");
    var cfg = PROFILES[S.profile];
    if (S.amount < 25000) {
      out.innerHTML = '<div class="notice warn">Minimum ₹25,000 — below that, costs ' +
        "and lot sizes eat the diversification.</div>";
      return;
    }
    out.innerHTML = '<p class="muted"><span class="spin"></span>Building…</p>';
    getJSON("/api/quotes?symbols=" + CORE.map(function (c) { return c.symbol; }).join(","))
      .then(function (d) {
        var qm = {};
        (d.quotes || []).forEach(function (q) { if (!q.error) qm[q.symbol] = q; });
        var mix = cfg.mix.slice(), notes = [], lines = [];
        if (!S.riskOn) {
          notes.push("The market is below its long-term average, so the stock sleeve " +
                     "stays in cash and only the index core is bought.");
          mix = [Math.min(mix[0], 0.6), 0, 1 - Math.min(mix[0], 0.6)];
        }
        CORE.forEach(function (c) {
          var q = qm[c.symbol];
          if (!q) { notes.push("No price for " + c.symbol + " — left out."); return; }
          var qty = Math.floor(S.amount * mix[0] * c.share / q.last);
          if (qty > 0) lines.push({ symbol:c.symbol, role:"Core", desc:c.desc, qty:qty,
                                    price:q.last, value:qty * q.last, stop:null });
        });
        if (mix[1] > 0) {
          var picks = UNIVERSE.map(function (s) { return S.quotes[s]; }).filter(Boolean)
            .filter(function (q) { return stageOf(q) === 2; })
            .sort(function (a, b) { return (b.mom6m || 0) - (a.mom6m || 0); })
            .slice(0, cfg.names);
          if (picks.length) {
            var per = Math.min(S.amount * mix[1] / picks.length, S.amount * cfg.maxPos);
            picks.forEach(function (q) {
              var stop = Math.max(q.swingLow20, q.last - cfg.stopMult * q.atr14);
              if (stop >= q.last) stop = q.last - cfg.stopMult * q.atr14;
              var qty = Math.floor(per / q.last);
              if (qty > 0) lines.push({ symbol:q.symbol, role:"Stock pick",
                desc:"in an uptrend", qty:qty, price:Math.round(q.last * 100) / 100,
                value:qty * q.last, stop:Math.round(stop * 100) / 100 });
            });
          } else {
            notes.push("No stock passed the trend filter today, so that sleeve stays in cash.");
          }
        }
        var invested = lines.reduce(function (t, l) { return t + l.value; }, 0);
        S.plan = { lines: lines, amount: S.amount, cash: S.amount - invested };
        out.innerHTML = '<table><thead><tr><th>What you buy</th><th>Role</th>' +
          '<th class="num">Qty</th><th class="num">Price</th><th class="num">Value</th>' +
          '<th class="num">Exit price</th></tr></thead><tbody>' +
          lines.map(function (l) {
            return "<tr><td><span class='sym'>" + esc(l.symbol) + "</span>" +
              "<div class='sub'>" + esc(l.desc) + "</div></td>" +
              "<td><span class='pill " + (l.role === "Core" ? "acc" : "up") + "'>" +
              esc(l.role) + "</span></td>" +
              '<td class="num">' + num(l.qty, 0) + "</td>" +
              '<td class="num">' + num(l.price) + "</td>" +
              '<td class="num">' + num(l.value, 0) + "</td>" +
              '<td class="num ' + (l.stop ? "neg" : "muted") + '">' +
              (l.stop ? num(l.stop) : "hold") + "</td></tr>";
          }).join("") +
          "<tr><td class='muted'>Cash kept back</td><td><span class='pill mut'>Cash</span>" +
          "</td><td></td><td></td><td class='num'>" + num(S.plan.cash, 0) +
          "</td><td class='num muted'>—</td></tr></tbody></table>" +
          notes.map(function (n) {
            return '<div class="notice warn">' + esc(n) + "</div>"; }).join("") +
          '<div class="row" style="margin-top:16px">' +
          '<button class="primary" id="savePlan">I placed these — track them</button>' +
          '<button class="ghost" id="csvPlan">Download as CSV</button></div>';
        el("savePlan").addEventListener("click", function () {
          try {
            localStorage.setItem("holdings", JSON.stringify(lines.map(function (l) {
              return { symbol:l.symbol, qty:l.qty, cost:l.price, stop:l.stop }; })));
            localStorage.setItem("startCapital", String(S.amount));
            renderPortfolio(); show("portfolio");
          } catch (e) { alert("Could not save in this browser."); }
        });
        el("csvPlan").addEventListener("click", function () {
          var rows = [["Exchange","Symbol","Transaction","Quantity","OrderType","Price","Product"]];
          lines.forEach(function (l) {
            rows.push(["NSE", l.symbol, "BUY", l.qty, "LIMIT",
                       Math.round(l.price * 1.002 * 10) / 10, "CNC"]); });
          var blob = new Blob([rows.map(function (r) { return r.join(","); }).join("\n")],
                              { type:"text/csv" });
          var a = document.createElement("a");
          a.href = URL.createObjectURL(blob); a.download = "advisor-orders.csv";
          document.body.appendChild(a); a.click(); document.body.removeChild(a);
        });
      });
  }

  function renderPortfolio() {
    var host = el("s-portfolio");
    var held = holdings();
    if (!held.length) {
      host.innerHTML = "<h1>Portfolio</h1>" +
        '<div class="notice calm">No positions saved yet. Build a plan under ' +
        "<b>Invest</b>, and mark it placed once you have bought.</div>";
      return;
    }
    var start = startCapital();
    var invested = held.reduce(function (t, p) { return t + p.qty * p.cost; }, 0);
    var cash = Math.max(0, start - invested);
    var value = held.reduce(function (t, p) {
      var q = S.quotes[p.symbol]; return t + (q ? p.qty * q.last : p.qty * p.cost); }, 0);
    var total = value + cash;

    host.innerHTML = "<h1>Portfolio</h1>" +
      '<div class="card"><div class="grid g4">' +
      U.stat("Worth today", inr(total),
             (total >= start ? "+" : "") + inr(total - start) + " since you started",
             total >= start ? "good" : "bad") +
      U.stat("Return", start ? pct(total / start - 1) : "—", held.length + " positions") +
      U.stat("Cash", inr(cash), "ready to invest") +
      U.stat("Invested", inr(invested), "at cost") +
      "</div></div>" +
      '<div class="card flush" style="margin-top:16px"><table><thead><tr>' +
      "<th>Holding</th><th class='num'>Qty</th><th class='num'>Cost</th>" +
      "<th class='num'>Now</th><th class='num'>Value</th><th class='num'>Gain</th>" +
      "<th class='num'>Room to exit</th><th>Action</th></tr></thead><tbody>" +
      held.map(function (p) {
        var q = S.quotes[p.symbol];
        var now = q ? q.last : null;
        var gain = now ? now / p.cost - 1 : null;
        var below = p.stop && now && now <= p.stop;
        return '<tr class="go" data-open="' + esc(p.symbol) + '">' +
          '<td class="sym">' + esc(p.symbol) + "</td>" +
          '<td class="num">' + num(p.qty, 0) + "</td>" +
          '<td class="num">' + num(p.cost) + "</td>" +
          '<td class="num">' + num(now) + "</td>" +
          '<td class="num">' + num(now ? p.qty * now : null, 0) + "</td>" +
          '<td class="num ' + (gain >= 0 ? "pos" : "neg") + '">' + pct(gain) + "</td>" +
          '<td class="num muted">' + (!p.stop ? "—" : below ? "below exit"
            : Math.round(100 * (now - p.stop) / now) + "% above") + "</td>" +
          "<td><span class='pill " + (below ? "down'>Sell" : "mut'>Hold") +
          "</span></td></tr>";
      }).join("") + "</tbody></table></div>" +
      '<p class="muted" style="margin-top:14px">Nothing here trades on its own. ' +
      "Every sell and every buy waits for you.</p>";
    host.querySelectorAll("[data-open]").forEach(function (n) {
      n.addEventListener("click", function () { openCompany(n.dataset.open); });
    });
  }

  /* The tape supplies the current price; the stored series still supplies every
     indicator, because those need history the tick does not carry. Prices on
     screen repaint themselves — this only re-renders when the live price has
     changed something that needs a *decision*, i.e. when a position crosses its
     exit. Re-rendering on every tick would throw away scroll position and any
     reasoning panel the reader had opened. */
  function startTape(symbols) {
    var LIVE = window.ADV_LIVE;
    if (!LIVE) return;
    var watch = symbols.concat(holdings().map(function (p) { return p.symbol; }));
    var uniqWatch = watch.filter(function (v, i) { return watch.indexOf(v) === i; });
    LIVE.track(uniqWatch);

    // If a Zerodha session is already in hand, stream instead of poll. The
    // indices come along so the desk note ticks with everything else.
    var K = window.ADV_KITE;
    if (K) {
      K.setSymbols(uniqWatch.concat(["NIFTY50", "BANKNIFTY"]));
      if (K.have()) K.connect();
    }
    LIVE.subscribe(function () {
      var before = alarmsFor(S.quotes).map(function (a) { return a.pos.symbol; }).join(",");
      Object.keys(S.quotes).forEach(function (sym) {
        S.quotes[sym] = LIVE.merge(S.quotes[sym]);
      });
      if (S.nifty) S.nifty = LIVE.merge(S.nifty);
      var after = alarmsFor(S.quotes).map(function (a) { return a.pos.symbol; }).join(",");
      if (before !== after && current === "home") renderHome();
    });
  }

  /* ---------------- boot ---------------- */
  getJSON("/api/quotes?symbols=^NSEI").then(function (d) {
    var n = ((d.quotes || []).filter(function (q) { return q.symbol === "^NSEI"; })[0]);
    S.nifty = n;
    if (n && n.sma200 != null) {
      S.riskOn = n.last > n.sma200;
      var dd = n.high52 ? n.last / n.high52 - 1 : 0;
      var state = S.riskOn && dd > -0.05 ? "Normal" : dd < -0.2 ? "Crisis"
                  : dd < -0.1 ? "Stress" : "Caution";
      S.regime = state;
      el("regime").innerHTML = "Market <b>" + state + "</b>";
      // repaint the desk note now the index is known — but never over an
      // error state, which owns the screen once shown.
      if (current === "home" && Object.keys(S.quotes).length) renderHome();
    } else {
      el("regime").textContent = "Market state unknown";
    }
  }).catch(function () { el("regime").textContent = "Market data unavailable"; });

  var all = UNIVERSE.concat(holdings().map(function (p) { return p.symbol; }));
  var uniq = all.filter(function (v, i) { return all.indexOf(v) === i; });
  getJSON("/api/quotes?symbols=" + encodeURIComponent(uniq.slice(0, 25).join(",")))
    .then(function (d) {
      (d.quotes || []).forEach(function (q) { if (!q.error) S.quotes[q.symbol] = q; });
      renderHome();
      startTape(uniq);
    })
    .catch(function () {
      el("s-home").innerHTML = deskHead() +
        '<div class="notice warn"><span class="k">No market data</span>' +
        "The data service could not be reached, so nothing can be shown. Every figure " +
        "in this app comes from a named source — none are estimated to fill the gap.</div>";
    });
})();
