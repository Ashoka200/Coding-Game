/* 360° deep dive — read a company the way an owner would.
   Financial statements → derived risk register → supply chain, policy exposure
   and growth runway from a sector knowledge map. Every finding names the number
   it came from; anything that needs the annual report is said so, not guessed. */
(function () {
  "use strict";

  /* ---------- sector knowledge: what each business runs on ---------- */
  var SECTORS = {
    it: {
      label: "IT services",
      inputs: ["engineering talent (wage inflation is the main cost)", "USD/INR realisation"],
      policy: ["US and UK visa rules", "safe-harbour transfer-pricing norms",
               "SEZ/GST treatment of exports"],
      structural: ["client and vertical concentration", "discretionary tech budgets are cyclical",
                   "AI pressure on the billable-hour model"],
      growth: ["large deal wins and renewal rates", "offshore mix", "utilisation and pyramid"]
    },
    bank: {
      label: "Banks & lenders",
      inputs: ["deposits and wholesale borrowing (cost of funds)"],
      policy: ["RBI repo rate and liquidity stance", "NPA recognition and provisioning norms",
               "priority-sector lending targets", "capital adequacy rules"],
      structural: ["credit cycle — losses arrive years after the loans",
                   "asset-liability mismatch", "unsecured retail book quality"],
      growth: ["deposit franchise (CASA)", "branch and digital reach", "net interest margin"]
    },
    pharma: {
      label: "Pharmaceuticals",
      inputs: ["APIs and key starting materials (heavy China dependence)", "solvents, energy"],
      policy: ["USFDA inspection outcomes", "NPPA domestic price control",
               "PLI schemes for APIs and medical devices"],
      structural: ["US generic price erosion", "plant observations can halt a whole site",
                   "patent cliffs and litigation"],
      growth: ["complex generics and biosimilars pipeline", "branded domestic formulations",
               "ANDA approvals"]
    },
    auto: {
      label: "Automobiles & components",
      inputs: ["steel, aluminium, copper", "semiconductors", "rubber and plastics"],
      policy: ["emission norms (BS-VI, CAFE)", "EV incentives and FAME schemes",
               "GST rates on vehicles", "PLI for auto components"],
      structural: ["deeply cyclical demand", "the EV transition can strand engine investment",
                   "chip and supply-chain shocks"],
      growth: ["new model cycle", "exports", "content per vehicle"]
    },
    fmcg: {
      label: "Consumer staples",
      inputs: ["palm oil and edible oils", "crude-linked packaging", "agri commodities", "milk"],
      policy: ["GST rates", "food safety regulation", "rural income schemes"],
      structural: ["rural demand sensitivity", "aggressive local and D2C competition",
                   "advertising spend is a permanent cost of staying visible"],
      growth: ["distribution reach", "premiumisation", "new categories"]
    },
    cement: {
      label: "Cement & building materials",
      inputs: ["limestone reserves", "coal and petcoke", "diesel and freight"],
      policy: ["government infrastructure capex", "housing schemes", "mining and royalty rules"],
      structural: ["regional overcapacity destroys pricing", "freight-cost sensitivity",
                   "sharp cyclicality"],
      growth: ["capacity additions near demand", "premium products", "regional mix"]
    },
    metal: {
      label: "Metals & mining",
      inputs: ["iron ore, bauxite, coking coal", "energy"],
      policy: ["export duties", "mining auctions and lease renewals", "import safeguards"],
      structural: ["global commodity cycle sets the price, not the company",
                   "China's demand and supply swing everything", "high fixed costs"],
      growth: ["captive raw material", "value-added mix", "cost position on the global curve"]
    },
    energy: {
      label: "Oil, gas & energy",
      inputs: ["crude oil", "natural gas", "refining feedstock"],
      policy: ["excise duties and subsidies", "administered price mechanisms",
               "energy-transition targets"],
      structural: ["crude price swings", "refining margin cycles",
                   "long-term demand risk from electrification"],
      growth: ["petrochemical integration", "retail network", "new-energy investment"]
    },
    telecom: {
      label: "Telecom",
      inputs: ["spectrum", "network equipment", "tower and fibre capex"],
      policy: ["spectrum auction pricing", "AGR dues and licence fees", "tariff regulation"],
      structural: ["capital intensity never stops", "tariff wars destroy returns",
                   "high leverage"],
      growth: ["ARPU repair", "data consumption", "enterprise and fixed broadband"]
    },
    infra: {
      label: "Infrastructure & capital goods",
      inputs: ["steel and cement", "skilled labour", "imported components"],
      policy: ["government capex cycle", "Gati Shakti and PLI", "land and clearance regimes"],
      structural: ["order execution risk", "receivables from government buyers",
                   "working capital swallows growth"],
      growth: ["order book and its quality", "private capex revival", "export orders"]
    },
    chem: {
      label: "Chemicals",
      inputs: ["crude derivatives", "imported intermediates (China supply)", "energy"],
      policy: ["anti-dumping duties", "PLI and import substitution", "environmental clearances"],
      structural: ["China dumping resets prices without warning",
                   "capacity cycles overshoot", "environmental compliance cost"],
      growth: ["China+1 customer wins", "specialty mix", "long-term contracts"]
    },
    generic: {
      label: "General business",
      inputs: ["raw materials and energy", "labour"],
      policy: ["GST and tax regime", "sector regulation", "import/export duties"],
      structural: ["competitive intensity", "demand cyclicality", "input cost pass-through"],
      growth: ["capacity expansion", "market share", "new products"]
    }
  };

  var SYMBOL_SECTOR = {
    TCS:"it", INFY:"it", HCLTECH:"it", WIPRO:"it", TECHM:"it", LTIM:"it",
    HDFCBANK:"bank", ICICIBANK:"bank", SBIN:"bank", AXISBANK:"bank", KOTAKBANK:"bank",
    BAJFINANCE:"bank", INDUSINDBK:"bank", BAJAJFINSV:"bank",
    SUNPHARMA:"pharma", DRREDDY:"pharma", CIPLA:"pharma", DIVISLAB:"pharma", LUPIN:"pharma",
    MARUTI:"auto", TATAMOTORS:"auto", M_M:"auto", BAJAJ_AUTO:"auto", EICHERMOT:"auto",
    HEROMOTOCO:"auto", BOSCHLTD:"auto",
    ITC:"fmcg", HINDUNILVR:"fmcg", NESTLEIND:"fmcg", BRITANNIA:"fmcg", DABUR:"fmcg",
    TITAN:"fmcg", ASIANPAINT:"chem",
    ULTRACEMCO:"cement", SHREECEM:"cement", AMBUJACEM:"cement", GRASIM:"cement",
    TATASTEEL:"metal", JSWSTEEL:"metal", HINDALCO:"metal", VEDL:"metal", COALINDIA:"metal",
    RELIANCE:"energy", ONGC:"energy", BPCL:"energy", IOC:"energy", GAIL:"energy",
    NTPC:"energy", POWERGRID:"energy",
    BHARTIARTL:"telecom", IDEA:"telecom",
    LT:"infra", SIEMENS:"infra", ABB:"infra", BEL:"infra", ADANIPORTS:"infra",
    PIDILITIND:"chem", SRF:"chem", UPL:"chem", TATACHEM:"chem"
  };

  function sectorFor(sym, name) {
    if (SYMBOL_SECTOR[sym]) return SECTORS[SYMBOL_SECTOR[sym]];
    var n = (name || "").toLowerCase();
    if (/bank|financ|capital|housing|credit/.test(n)) return SECTORS.bank;
    if (/pharma|labor|health|drug/.test(n)) return SECTORS.pharma;
    if (/motor|auto|vehicle/.test(n)) return SECTORS.auto;
    if (/cement/.test(n)) return SECTORS.cement;
    if (/steel|metal|alum|zinc|copper|mining/.test(n)) return SECTORS.metal;
    if (/petro|oil|gas|energy|power/.test(n)) return SECTORS.energy;
    if (/tele|communic/.test(n)) return SECTORS.telecom;
    if (/chem|paint|fertil/.test(n)) return SECTORS.chem;
    if (/infra|construc|engineer|project/.test(n)) return SECTORS.infra;
    if (/consumer|food|bever|foods/.test(n)) return SECTORS.fmcg;
    if (/tech|info|soft|system|digital/.test(n)) return SECTORS.it;
    return SECTORS.generic;
  }

  /* ---------- helpers ---------- */
  function el(id) { return document.getElementById(id); }
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
    return { "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;" }[c]; }); }
  function num(n, d) {
    return n == null || isNaN(n) ? "—" : Number(n).toLocaleString("en-IN",
      { maximumFractionDigits: d == null ? 0 : d, minimumFractionDigits: d == null ? 0 : d }); }
  function pctv(x, d) { return x == null || isNaN(x) ? "—" :
    (x >= 0 ? "+" : "") + (x * 100).toFixed(d == null ? 1 : d) + "%"; }
  function cr(n) { return n == null ? "—" : "₹" + num(n) + " Cr"; }
  function clean(a) { return (a || []).filter(function (v) { return v != null && isFinite(v); }); }
  function lastOf(a) { var c = clean(a); return c.length ? c[c.length - 1] : null; }
  function cagr(a, years) {
    var c = clean(a); if (c.length < 2) return null;
    var span = years || c.length - 1;
    var first = c[Math.max(0, c.length - 1 - span)], last = c[c.length - 1];
    if (!first || first <= 0 || last <= 0) return null;
    var n = Math.min(span, c.length - 1);
    return Math.pow(last / first, 1 / n) - 1;
  }
  function rowOf(block, names) {
    if (!block || !block.rows) return null;
    var keys = Object.keys(block.rows);
    for (var i = 0; i < names.length; i++) {
      var want = names[i].toLowerCase();
      for (var j = 0; j < keys.length; j++) {
        if (keys[j].toLowerCase().indexOf(want) === 0) return block.rows[keys[j]];
      }
    }
    for (var k = 0; k < names.length; k++) {
      var w = names[k].toLowerCase();
      for (var m = 0; m < keys.length; m++) {
        if (keys[m].toLowerCase().indexOf(w) !== -1) return block.rows[keys[m]];
      }
    }
    return null;
  }
  function slope(a) {
    var c = clean(a); if (c.length < 3) return null;
    var half = Math.floor(c.length / 2);
    var early = c.slice(0, half).reduce(function (s, v) { return s + v; }, 0) / half;
    var late = c.slice(-half).reduce(function (s, v) { return s + v; }, 0) / half;
    if (!early) return null;
    return late / early - 1;
  }

  /* ---------- the analysis ---------- */
  function analyse(d) {
    var pl = d.profitLoss, bs = d.balanceSheet, cf = d.cashFlow,
        ra = d.ratios, sh = d.shareholding;
    var sales = rowOf(pl, ["sales", "revenue"]);
    var opProfit = rowOf(pl, ["operating profit"]);
    var opm = rowOf(pl, ["opm"]);
    var netProfit = rowOf(pl, ["net profit"]);
    var interest = rowOf(pl, ["interest"]);
    var otherIncome = rowOf(pl, ["other income"]);
    var borrowings = rowOf(bs, ["borrowings"]);
    var reserves = rowOf(bs, ["reserves"]);
    var equityCap = rowOf(bs, ["equity capital"]);
    var fixedAssets = rowOf(bs, ["fixed assets"]);
    var cwip = rowOf(bs, ["cwip"]);
    var cfo = rowOf(cf, ["cash from operating"]);
    var cfi = rowOf(cf, ["cash from investing"]);
    var debtorDays = rowOf(ra, ["debtor days"]);
    var inventoryDays = rowOf(ra, ["inventory days"]);
    var ccc = rowOf(ra, ["cash conversion"]);
    var roce = rowOf(ra, ["roce"]);
    var promoters = rowOf(sh, ["promoter"]);
    var fii = rowOf(sh, ["fii"]);
    var dii = rowOf(sh, ["dii"]);

    var risks = [], strengths = [];
    function risk(sev, title, finding, why) { risks.push({ sev:sev, title:title, finding:finding, why:why }); }

    /* 1. Where the money comes from — and whether it is real */
    var patSum = clean(netProfit && netProfit.slice ? netProfit.slice(-5) : []).reduce(function (s,v){return s+v;},0);
    var cfoSum = clean(cfo ? cfo.slice(-5) : []).reduce(function (s,v){return s+v;},0);
    var cashConv = patSum > 0 ? cfoSum / patSum : null;
    if (cashConv != null) {
      if (cashConv < 0.6) risk("high", "Profit is not turning into cash",
        "Over five years the company reported " + cr(patSum) + " of profit but collected only " +
        cr(cfoSum) + " from operations (" + Math.round(cashConv * 100) + "%).",
        "Profit you never receive in cash is an accounting entry. This is the single most reliable " +
        "early warning of aggressive revenue recognition or a business that funds its customers.");
      else if (cashConv > 0.85) strengths.push("Profits convert to cash — " +
        Math.round(cashConv * 100) + "% of five-year profit arrived as operating cash flow.");
    }

    var otherShare = lastOf(otherIncome) && lastOf(netProfit)
      ? lastOf(otherIncome) / Math.abs(lastOf(netProfit)) : null;
    if (otherShare != null && otherShare > 0.35) risk("medium", "Profit leans on non-operating income",
      "Other income is " + Math.round(otherShare * 100) + "% the size of net profit.",
      "Treasury gains, one-off sales and forex swings are not the business. Strip them out before " +
      "paying a multiple for the earnings.");

    /* 2. Margins — pricing power vs input costs */
    var opmTrend = slope(opm);
    if (opmTrend != null) {
      if (opmTrend < -0.15) risk("medium", "Margins are compressing",
        "Operating margin has fallen about " + Math.round(Math.abs(opmTrend) * 100) +
        "% from its earlier average (now " + num(lastOf(opm), 1) + "%).",
        "Either input costs are rising faster than the company can pass on, or competition is " +
        "taking the price. Both mean the business has less pricing power than it used to.");
      else if (opmTrend > 0.15) strengths.push("Operating margin has expanded about " +
        Math.round(opmTrend * 100) + "% versus its earlier average — evidence of pricing power or scale.");
    }

    /* 3. Debt and its cost */
    var netWorth = (lastOf(equityCap) || 0) + (lastOf(reserves) || 0);
    var debt = lastOf(borrowings);
    var de = netWorth > 0 && debt != null ? debt / netWorth : null;
    var cover = lastOf(interest) ? (lastOf(opProfit) || 0) / lastOf(interest) : null;
    var debtTrend = slope(borrowings);
    if (de != null && de > 1.5) risk(de > 3 ? "high" : "medium", "Heavily indebted",
      "Borrowings of " + cr(debt) + " against net worth of " + cr(netWorth) +
      " — debt to equity " + num(de, 2) + ".",
      "Debt turns an ordinary bad year into an existential one, because interest does not wait " +
      "for the cycle to turn.");
    if (cover != null && cover < 3) risk(cover < 1.5 ? "high" : "medium", "Interest cover is thin",
      "Operating profit covers interest only " + num(cover, 1) + " times.",
      "Below about 3× there is little room for a demand slowdown or a rate rise before profit " +
      "goes to lenders instead of owners.");
    if (debtTrend != null && debtTrend > 0.4 && (opmTrend == null || opmTrend < 0.05))
      risk("medium", "Debt is growing without matching returns",
        "Borrowings are up roughly " + Math.round(debtTrend * 100) + "% versus the earlier period " +
        "while margins have not improved.",
        "Borrowing to stand still is how balance sheets quietly deteriorate.");
    if (de != null && de < 0.3) strengths.push("Low debt — borrowings are " + num(de, 2) +
      "× net worth, so the company controls its own fate in a downturn.");

    /* 4. Working capital — the cash trap */
    var ddTrend = slope(debtorDays), cccLast = lastOf(ccc);
    if (ddTrend != null && ddTrend > 0.3) risk("medium", "Customers are taking longer to pay",
      "Debtor days have risen about " + Math.round(ddTrend * 100) + "% (now " +
      num(lastOf(debtorDays), 0) + " days).",
      "Receivables ballooning faster than sales is the classic signature of channel stuffing or " +
      "a weakening customer base — and it consumes the cash growth was supposed to produce.");
    if (cccLast != null && cccLast > 120) risk("medium", "Cash is locked in the working cycle",
      "Cash conversion cycle is " + num(cccLast, 0) + " days.",
      "Every rupee of growth needs a rupee of working capital first. Long cycles make growth " +
      "expensive and leave the company dependent on lenders.");

    /* 5. Growth runway — is it reinvesting, and does reinvestment pay? */
    var capex = cfi ? clean(cfi.slice(-3)).reduce(function (s,v){return s+v;},0) : null;
    var cfoRecent = cfo ? clean(cfo.slice(-3)).reduce(function (s,v){return s+v;},0) : null;
    var reinvest = capex != null && cfoRecent ? Math.abs(capex) / cfoRecent : null;
    var roceNow = lastOf(roce), roceTrend = slope(roce);
    var cwipNow = lastOf(cwip);
    var runway = [];
    if (reinvest != null) runway.push("Reinvesting about " + Math.round(reinvest * 100) +
      "% of operating cash flow back into the business over the last three years.");
    if (cwipNow) runway.push("Capital work in progress of " + cr(cwipNow) +
      " — capacity being built now that has not yet earned anything.");
    if (roceNow != null) runway.push("Return on capital employed is " + num(roceNow, 1) + "%" +
      (roceTrend != null ? " and has " + (roceTrend > 0.1 ? "improved" : roceTrend < -0.1 ? "deteriorated" : "held steady") +
       " versus the earlier period" : "") + ".");
    if (roceNow != null && roceNow < 12) risk("medium", "Returns barely beat the cost of capital",
      "ROCE of " + num(roceNow, 1) + "% against a cost of capital that is realistically 11–13% in India.",
      "A business that cannot earn more than its funding cost destroys value as it grows. Growth " +
      "is only good news above the hurdle.");
    if (roceNow != null && roceNow > 20 && reinvest != null && reinvest > 0.4)
      strengths.push("High returns AND heavy reinvestment (" + num(roceNow, 1) + "% ROCE, " +
        Math.round(reinvest * 100) + "% of cash flow redeployed) — the compounding combination.");

    /* 6. Ownership and governance */
    var promLast = lastOf(promoters), promTrend = slope(promoters);
    if (promLast != null) {
      if (promTrend != null && promTrend < -0.08) risk("high", "Promoters are selling down",
        "Promoter holding has fallen to " + num(promLast, 1) + "% from a higher earlier average.",
        "The people who know the business best reducing their stake deserves an explanation " +
        "before you increase yours.");
      else if (promLast < 26) risk("medium", "Low promoter holding",
        "Promoters hold " + num(promLast, 1) + "%.",
        "Below about a quarter, control is contestable and management's interests are less " +
        "aligned with yours.");
      else strengths.push("Promoters hold " + num(promLast, 1) + "% — skin in the game.");
    }
    var fiiTrend = slope(fii), diiTrend = slope(dii);

    /* 7. Concentration and disclosure gaps that need the annual report */
    var needsReport = [
      "Contingent liabilities and pending litigation — the notes to accounts list every material " +
      "case, tax dispute and guarantee. A large contingent liability relative to net worth can " +
      "wipe out years of profit.",
      "Customer and geography concentration — how much revenue comes from the top five customers " +
      "or one country.",
      "Related-party transactions — money moving between the listed company and entities the " +
      "promoter owns.",
      "Pledged promoter shares — pledging is disclosed to the exchanges and is the fastest-moving " +
      "governance red flag there is.",
      "Auditor's remarks, qualifications and any auditor change in the last three years."
    ];

    return {
      sales: sales, opm: opm, netProfit: netProfit, cfo: cfo, borrowings: borrowings,
      periods: pl ? pl.periods : [],
      salesCagr3: cagr(sales, 3), salesCagr5: cagr(sales, 5),
      profitCagr3: cagr(netProfit, 3), profitCagr5: cagr(netProfit, 5),
      opmNow: lastOf(opm), opmTrend: opmTrend,
      cashConv: cashConv, de: de, cover: cover, roceNow: roceNow,
      promLast: promLast, fiiTrend: fiiTrend, diiTrend: diiTrend,
      reinvest: reinvest, risks: risks, strengths: strengths, runway: runway,
      needsReport: needsReport
    };
  }

  /* ---------- rendering ---------- */
  function sevPill(s) {
    return s === "high" ? '<span class="pill down">Serious</span>'
      : s === "medium" ? '<span class="pill warn">Watch</span>'
      : '<span class="pill mut">Minor</span>';
  }

  function miniChart(series, periods, label, colour) {
    var c = clean(series);
    if (c.length < 2) return "";
    var max = Math.max.apply(null, c), min = Math.min.apply(null, c.concat([0]));
    var span = max - min || 1;
    var bars = c.slice(-10).map(function (v, i, arr) {
      var h = Math.max(2, ((v - min) / span) * 60);
      return '<div style="flex:1;display:flex;flex-direction:column;justify-content:flex-end;' +
        'align-items:center;gap:3px"><div style="width:100%;height:' + h + 'px;background:' +
        colour + ';border-radius:2px 2px 0 0" title="' + num(v) + '"></div></div>';
    }).join("");
    return '<div style="margin-bottom:14px"><div class="lbl">' + esc(label) + '</div>' +
      '<div style="display:flex;align-items:flex-end;gap:3px;height:64px">' + bars + '</div>' +
      '<div class="muted" style="display:flex;justify-content:space-between;font-size:11px;margin-top:4px">' +
      '<span>' + esc((periods || [])[Math.max(0, periods.length - Math.min(10, c.length))] || "") + '</span>' +
      '<span>' + esc((periods || [])[periods.length - 1] || "latest") + '</span></div></div>';
  }

  function render(d, a) {
    var sec = sectorFor(d.symbol, d.name);
    var body = el("deepBody");

    var html = '<div class="card" style="margin-bottom:16px">' +
      '<h2 style="margin-top:0">' + esc(d.name) + '</h2>' +
      (d.about ? '<p class="muted">' + esc(d.about.slice(0, 420)) + '</p>' : "") +
      '<p class="muted">Figures are ' + esc(d.basis) + '. Sector read: <strong>' +
      esc(sec.label) + '</strong>.</p></div>';

    /* headline numbers */
    html += '<div class="stats" style="margin-bottom:18px">' +
      statBox("Sales growth (5y)", pctv(a.salesCagr5), "per year, compounded") +
      statBox("Profit growth (5y)", pctv(a.profitCagr5), "per year, compounded") +
      statBox("Operating margin", a.opmNow == null ? "—" : num(a.opmNow, 1) + "%",
        a.opmTrend == null ? "" : (a.opmTrend > 0.1 ? "widening" : a.opmTrend < -0.1 ? "narrowing" : "steady"),
        "", "opmargin") +
      statBox("Cash conversion", a.cashConv == null ? "—" : Math.round(a.cashConv * 100) + "%",
        "of 5y profit collected in cash",
        a.cashConv == null ? "" : a.cashConv < 0.6 ? "bad" : a.cashConv > 0.85 ? "good" : "warnb",
        "cashconv") +
      statBox("Debt / equity", num(a.de, 2), a.de == null ? "" : a.de > 1.5 ? "leveraged" : "conservative",
        a.de == null ? "" : a.de > 1.5 ? "bad" : "good", "de") +
      statBox("Return on capital", a.roceNow == null ? "—" : num(a.roceNow, 1) + "%",
        "against a ~12% cost of capital",
        a.roceNow == null ? "" : a.roceNow > 18 ? "good" : a.roceNow < 12 ? "bad" : "warnb", "roce") +
      '</div>';

    /* trends */
    html += '<div class="grid2" style="margin-bottom:18px"><div class="card">' +
      '<h2 style="margin-top:0">The record</h2>' +
      miniChart(a.sales, a.periods, "Sales (₹ Cr)", "var(--accent)") +
      miniChart(a.netProfit, a.periods, "Net profit (₹ Cr)", "var(--up)") +
      miniChart(a.cfo, a.periods, "Cash from operations (₹ Cr)", "var(--sky)") +
      '</div><div class="card"><h2 style="margin-top:0">What the business runs on</h2>' +
      '<div class="lbl">Inputs and supply</div><ul style="margin:0 0 14px;padding-left:19px">' +
      sec.inputs.map(function (i) { return "<li>" + esc(i) + "</li>"; }).join("") + '</ul>' +
      '<div class="lbl">Government policy that moves this business</div>' +
      '<ul style="margin:0 0 14px;padding-left:19px">' +
      sec.policy.map(function (i) { return "<li>" + esc(i) + "</li>"; }).join("") + '</ul>' +
      '<div class="lbl">Structural risks of the industry</div>' +
      '<ul style="margin:0;padding-left:19px">' +
      sec.structural.map(function (i) { return "<li>" + esc(i) + "</li>"; }).join("") + '</ul>' +
      '</div></div>';

    /* risk register */
    html += '<h2>Risk register — what could go wrong</h2>';
    html += a.risks.length ? '<div class="card tight"><div class="tablewrap"><table>' +
      '<thead><tr><th>Severity</th><th>Risk</th><th>What the numbers show</th>' +
      '<th>Why it matters</th></tr></thead><tbody>' +
      a.risks.sort(function (x, y) {
        var o = { high:0, medium:1, low:2 }; return o[x.sev] - o[y.sev];
      }).map(function (r) {
        return '<tr><td>' + sevPill(r.sev) + '</td>' +
          '<td style="white-space:normal"><strong>' + esc(r.title) + '</strong></td>' +
          '<td style="white-space:normal">' + esc(r.finding) + '</td>' +
          '<td style="white-space:normal" class="muted">' + esc(r.why) + '</td></tr>';
      }).join("") + '</tbody></table></div></div>'
      : '<div class="notice info">No red flags in the numbers we can compute. That is not the ' +
        'same as no risk — see the annual-report checklist below.</div>';

    /* strengths + runway */
    html += '<div class="grid2" style="margin-top:18px"><div class="card">' +
      '<h2 style="margin-top:0">What is working</h2>' +
      (a.strengths.length ? '<ul style="margin:0;padding-left:19px">' +
        a.strengths.map(function (s) { return "<li>" + esc(s) + "</li>"; }).join("") + '</ul>'
        : '<p class="muted">Nothing stands out as a durable strength in the numbers.</p>') +
      (d.pros && d.pros.length ? '<div class="lbl" style="margin-top:14px">Also noted by the data source</div>' +
        '<ul style="margin:0;padding-left:19px" class="muted">' +
        d.pros.slice(0, 4).map(function (p) { return "<li>" + esc(p) + "</li>"; }).join("") + '</ul>' : "") +
      '</div><div class="card"><h2 style="margin-top:0">Room to grow</h2>' +
      (a.runway.length ? '<ul style="margin:0 0 12px;padding-left:19px">' +
        a.runway.map(function (r) { return "<li>" + esc(r) + "</li>"; }).join("") + '</ul>' : "") +
      '<div class="lbl">What has to go right</div><ul style="margin:0;padding-left:19px">' +
      sec.growth.map(function (g) { return "<li>" + esc(g) + "</li>"; }).join("") + '</ul>' +
      '</div></div>';

    /* annual report checklist */
    html += '<h2>What the numbers cannot tell you</h2>' +
      '<div class="notice warnn"><span class="k">Read these in the annual report before you buy</span>' +
      'Screens work with what is published as data. Litigation, concentration and related-party ' +
      'risk live in the notes — and they are where most permanent losses come from.</div>' +
      '<div class="card"><ul style="margin:0;padding-left:19px">' +
      a.needsReport.map(function (n) { return "<li style='margin-bottom:7px'>" + esc(n) + "</li>"; }).join("") +
      '</ul><p class="muted" style="margin:14px 0 0">Annual reports, filings and concall ' +
      'transcripts: <a href="' + esc(d.documentsUrl) + '" target="_blank" rel="noopener">' +
      'open the company\'s document list</a>.</p></div>';

    html += '<p class="muted" style="margin-top:18px">Analysis is computed from published ' +
      'financial statements. Decision-support only, not investment advice.</p>';

    body.innerHTML = html;
  }

  function statBox(k, v, s, cls, infoKey) {
    return '<div class="stat ' + (cls || "") + '"><div class="k">' + esc(k) +
      (infoKey ? '<span data-info="' + infoKey + '"></span>' : "") + '</div>' +
      '<div class="v">' + v + '</div><div class="s">' + esc(s || "") + '</div></div>';
  }

  /* ---------- wiring ---------- */
  function run() {
    var sym = (el("deepSym").value || "").trim().toUpperCase();
    if (!sym) return;
    var st = el("deepStatus");
    st.innerHTML = '<span class="spin"></span>Reading the financials…';
    el("deepBody").innerHTML = "";
    fetch("/api/deepdive?symbol=" + encodeURIComponent(sym))
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (d.error) {
          st.textContent = "";
          el("deepBody").innerHTML = '<div class="notice err"><strong>' + esc(d.error) + '.</strong> ' +
            esc(d.hint || "") + '</div>';
          return;
        }
        st.textContent = "";
        render(d, analyse(d));
      })
      .catch(function (e) {
        st.textContent = "";
        el("deepBody").innerHTML = '<div class="notice err">Could not load: ' + esc(e.message) + '</div>';
      });
  }
  el("loadDeep").addEventListener("click", run);
  el("deepSym").addEventListener("keydown", function (ev) { if (ev.key === "Enter") run(); });

  var list = el("deepList");
  ["RELIANCE","TCS","HDFCBANK","ICICIBANK","INFY","LT","BHARTIARTL","ITC","SBIN","TITAN",
   "SUNPHARMA","AXISBANK","MARUTI","ASIANPAINT","BAJFINANCE","HCLTECH","ULTRACEMCO",
   "NESTLEIND","KOTAKBANK","TATAMOTORS","TATASTEEL","JSWSTEEL","DRREDDY","CIPLA","WIPRO"]
    .forEach(function (s) {
      var o = document.createElement("option"); o.value = s; list.appendChild(o);
    });
})();
