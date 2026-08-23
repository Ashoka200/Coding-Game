/* The decision engine: turns evidence into one action, through a fixed sequence
   of gates. The sequence matters more than any single rule — it is what makes
   the answer reproducible instead of a vibe.

   Stage 0  Evidence inventory      what do we actually know? sets the confidence ceiling
   Stage 1  Hard vetoes             fraud, default, ruinous leverage — override everything
   Stage 2  Position state          a breached exit price is already a decision you made
   Stage 3  Business quality        is it still the company you thought you owned?
   Stage 4  Valuation               what are you paying for that business?
   Stage 5  News overlay            has anything material changed in the last two weeks?
   Stage 6  Trend and timing        what is price actually doing?
   Stage 7  Market regime           is this a market that rewards new risk?
   Stage 8  Horizon                 is the case long-term (business) or short-term (momentum)?
   Stage 9  Synthesis               action, conviction, levels, and the reasoning chain
*/
(function () {
  "use strict";

  function el(id) { return document.getElementById(id); }
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
    return { "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;" }[c]; }); }
  function num(n, d) { return n == null || isNaN(n) ? "—" :
    Number(n).toLocaleString("en-IN", { maximumFractionDigits: d == null ? 2 : d,
                                        minimumFractionDigits: d == null ? 2 : d }); }
  function pct(x, d) { return x == null || isNaN(x) ? "—" :
    (x >= 0 ? "+" : "") + (x * 100).toFixed(d == null ? 1 : d) + "%"; }

  var ACTIONS = {
    SELL:        { label: "Sell", cls: "down", order: 0 },
    TRIM:        { label: "Trim", cls: "warn", order: 1 },
    HOLD:        { label: "Hold", cls: "mut", order: 2 },
    WATCH:       { label: "Watch, don't buy yet", cls: "mut", order: 3 },
    AVOID:       { label: "Avoid", cls: "down", order: 4 },
    ACCUMULATE:  { label: "Buy on dips", cls: "sky", order: 5 },
    BUY:         { label: "Buy", cls: "up", order: 6 },
    HEDGE:       { label: "Hedge, don't short", cls: "warn", order: 7 }
  };

  /* ---------- the engine ---------- */
  function decide(input) {
    var q = input.quote, f = input.fundamentals, news = input.news,
        held = input.held, regimeRiskOn = input.regimeRiskOn;
    var chain = [];           // the reasoning, in the order it was applied
    var conviction = 50;      // 0-100, adjusted by each stage
    var action = null, horizon = null;

    function step(stage, finding) { chain.push({ stage: stage, finding: finding }); }

    /* -- Stage 0: evidence inventory -- */
    var have = { price: !!q, fundamentals: !!f && !f.error, news: !!news && !news.error };
    var ceiling = 60 + (have.fundamentals ? 20 : 0) + (have.news ? 20 : 0);
    step("Evidence", "Working from " +
      [have.price ? "price and trend" : null,
       have.fundamentals ? "financials" : "no financials",
       have.news ? "recent news" : "no news feed"].filter(Boolean).join(", ") +
      ". Confidence is capped at " + ceiling + " because of what is missing.");

    /* -- Stage 1: hard vetoes -- */
    var veto = null;
    if (have.news) {
      var grave = (news.items || []).filter(function (i) {
        return i.weight <= -3 && (i.ageDays == null || i.ageDays <= 21); });
      if (grave.length) veto = "A grave event is in the news: " + grave[0].eventLabel.toLowerCase() +
        " — “" + grave[0].title.slice(0, 110) + "”";
    }
    if (!veto && have.fundamentals && f.debtToEquity != null && f.debtToEquity > 3 &&
        f.interestCover != null && f.interestCover < 1.5) {
      veto = "Debt is " + num(f.debtToEquity) + "× equity and operating profit covers interest only " +
        num(f.interestCover, 1) + "× — the balance sheet, not the business, now decides the outcome.";
    }
    if (veto) {
      step("Veto", veto);
      return finish(held ? "SELL" : "AVOID", 85,
        "long-term risk — this is about survival, not price", chain, input);
    }
    step("Veto check", "No fraud, default or ruinous-leverage flag.");

    /* -- Stage 2: position state (holdings only) -- */
    if (held) {
      if (held.stop && q && q.last <= held.stop) {
        step("Position", "Price " + num(q.last) + " is at or below the exit price of " +
          num(held.stop) + " you set when you bought.");
        return finish("SELL", 90,
          "the decision was made when you were calm; this is only the execution", chain, input);
      }
      if (held.weight != null && held.weight > 0.15) {
        step("Position", "This position is " + pct(held.weight, 0) +
          " of the portfolio — past the 15% concentration limit.");
        action = "TRIM";
      }
    }

    /* -- Stage 3: business quality -- */
    var quality = null;
    if (have.fundamentals && input.fundScore != null) {
      quality = input.fundScore;
      step("Business", "Fundamental score " + quality + "/100" +
        (f.roce != null ? ", ROCE " + pct(f.roce) : f.roe != null ? ", ROE " + pct(f.roe) : "") +
        (f.debtToEquity != null ? ", debt/equity " + num(f.debtToEquity) : "") + ".");
      conviction += quality >= 70 ? 12 : quality >= 55 ? 4 : quality >= 40 ? -6 : -18;
    } else {
      step("Business", "No financials available, so nothing here can be a long-term call.");
    }

    /* -- Stage 4: valuation -- */
    var valuation = "unknown";
    if (have.fundamentals && f.pe != null && f.pe > 0) {
      valuation = f.pe < 18 ? "cheap" : f.pe < 35 ? "fair" : f.pe < 60 ? "rich" : "extreme";
      step("Valuation", "P/E of " + num(f.pe, 1) + " — " + valuation + ".");
      conviction += valuation === "cheap" ? 10 : valuation === "fair" ? 3
        : valuation === "rich" ? -6 : -14;
    }

    /* -- Stage 5: news overlay -- */
    var newsTone = "none";
    if (have.news && news.pressure) {
      newsTone = news.pressure.tone;
      var material = (news.items || []).filter(function (i) { return Math.abs(i.weight) >= 2; });
      step("News", material.length
        ? material.length + " material item(s) in the last two weeks; net tone " + newsTone +
          ". Most significant: “" + material[0].title.slice(0, 100) + "”"
        : "Nothing material in the last two weeks.");
      conviction += news.pressure.net > 1.5 ? 8 : news.pressure.net < -1.5 ? -12 : 0;
    }

    /* -- Stage 6: trend and timing -- */
    var st = input.stage, trendWord = { 2:"uptrend", 1:"basing", 3:"topping", 4:"downtrend" }[st];
    step("Trend", "Price is in a " + trendWord +
      (q && q.rsi14 != null ? ", RSI " + num(q.rsi14, 0) : "") +
      (q && q.high52 ? ", " + pct(q.last / q.high52 - 1) + " from its 52-week high" : "") + ".");
    conviction += st === 2 ? 10 : st === 1 ? 0 : st === 3 ? -8 : -16;
    var overbought = q && q.rsi14 != null && q.rsi14 > 78;
    var oversold = q && q.rsi14 != null && q.rsi14 < 25;

    /* -- Stage 7: regime -- */
    if (!regimeRiskOn) {
      step("Market", "The market is not in a clean uptrend, so new buying is restrained " +
        "regardless of how good the stock looks.");
      conviction -= 8;
    }

    /* -- Stage 8: horizon -- */
    if (quality != null && quality >= 60 && valuation !== "extreme") {
      horizon = "Long term — the case rests on the business compounding, so measure it in years";
    } else if (st === 2 && (quality == null || quality >= 40)) {
      horizon = "Short term — the case rests on the trend, so it lives and dies by the exit price";
    } else {
      horizon = "No horizon qualifies — neither the business nor the trend supports a position";
    }
    step("Horizon", horizon);

    /* -- Stage 9: synthesis -- */
    if (!action) {
      var badBusiness = quality != null && quality < 45;
      var goodBusiness = quality != null && quality >= 65;
      if (st === 4 && (badBusiness || newsTone === "negative")) {
        action = held ? "SELL" : "AVOID";
      } else if (st === 4) {
        action = held ? "HOLD" : "WATCH";
      } else if (held) {
        if (newsTone === "negative" && badBusiness) action = "SELL";
        else if (overbought && valuation === "extreme") action = "TRIM";
        else action = "HOLD";
      } else {
        if (goodBusiness && st === 2 && regimeRiskOn && !overbought) action = "BUY";
        else if (goodBusiness && (valuation === "cheap" || oversold)) action = "ACCUMULATE";
        else if (st === 2 && regimeRiskOn && quality == null) action = "BUY";
        else if (badBusiness) action = "AVOID";
        else action = "WATCH";
      }
    }

    // The "short it" question, answered honestly rather than ignored.
    var shortCase = (st === 4 && (newsTone === "negative" || (quality != null && quality < 40)));
    if (shortCase && !held) {
      step("Short?", "The bear case is real, but a naked short has unlimited loss and, in India, " +
        "cash-market shorts must be squared off the same day. If you want this exposure, use a " +
        "defined-risk bear put spread sized to 0.5–1% of capital — never a naked short.");
    }

    return finish(action, Math.round(Math.max(5, Math.min(ceiling, conviction))),
      horizon, chain, input, shortCase);
  }

  function finish(action, conviction, horizon, chain, input, shortCase) {
    var q = input.quote, levels = null;
    if (q && q.atr14) {
      var stop = Math.max(q.swingLow20 || 0, q.last - 2 * q.atr14);
      if (stop >= q.last) stop = q.last - 2 * q.atr14;
      var risk = q.last - stop;
      levels = { entry: q.last, stop: stop, t1: q.last + 1.5 * risk, t2: q.last + 2.5 * risk,
                 addBelow: q.last * 0.94 };
    }
    return { action: action, conviction: conviction, horizon: horizon,
             chain: chain, levels: levels, shortCase: !!shortCase, symbol: input.symbol };
  }

  window.ADV_VERDICT = { decide: decide, ACTIONS: ACTIONS };

  /* ---------- rendering ---------- */
  function card(v, extra) {
    var a = ACTIONS[v.action] || ACTIONS.WATCH;
    var lv = v.levels;
    return '<div class="card" style="margin-bottom:14px">' +
      '<div style="display:flex;align-items:baseline;gap:12px;flex-wrap:wrap;margin-bottom:8px">' +
      '<span class="sym" style="font-size:17px">' + esc(v.symbol) + '</span>' +
      '<span class="pill ' + a.cls + '" style="font-size:12px;padding:5px 12px">' + a.label + '</span>' +
      '<span class="muted">conviction ' + v.conviction + '/100</span>' +
      (extra ? '<span class="muted">' + extra + '</span>' : "") + '</div>' +
      '<p style="margin:0 0 10px"><strong>' + esc(v.horizon) + '</strong></p>' +
      '<details><summary style="cursor:pointer;font-family:Archivo,sans-serif;font-weight:700;' +
      'font-size:12.5px;color:var(--muted)">How this was decided — ' + v.chain.length +
      ' steps</summary><ol style="margin:10px 0 0;padding-left:20px;font-size:13.5px">' +
      v.chain.map(function (c) {
        return '<li style="margin-bottom:6px"><strong>' + esc(c.stage) + ':</strong> ' +
          esc(c.finding) + '</li>'; }).join("") + '</ol></details>' +
      (lv ? '<div class="rowline" style="margin-top:12px;gap:18px;font-size:13px">' +
        '<span class="muted">Exit price <strong class="mono" style="color:var(--down)">' +
        num(lv.stop) + '</strong></span>' +
        '<span class="muted">Target <strong class="mono" style="color:var(--up)">' +
        num(lv.t1) + '</strong> then <strong class="mono" style="color:var(--up)">' +
        num(lv.t2) + '</strong></span>' +
        (v.action === "ACCUMULATE" ? '<span class="muted">Add below <strong class="mono">' +
          num(lv.addBelow) + '</strong></span>' : "") + '</div>' : "") +
      (v.shortCase ? '<div class="notice warnn" style="margin-top:10px">The bear case is real. ' +
        'If you want to act on it, use a defined-risk bear put spread — never a naked short.</div>' : "") +
      '</div>';
  }
  window.ADV_VERDICT.card = card;
})();
