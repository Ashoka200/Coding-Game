/* Explain every feature. `data-info="key"` on any element renders an ⓘ marker
   that opens a plain-language explanation. Terms are written for someone who
   knows their own money but not the jargon. */
(function () {
  "use strict";

  var G = {
    /* ---- price & trend ---- */
    price: ["Price", "The last traded price. End-of-day here — during market hours your broker will show a slightly different number."],
    day: ["Day change", "How much the price moved since <em>yesterday's</em> close. A normal day is under 2%; anything past 5% means news, results, or a corporate action."],
    trend: ["Trend stage", "Where the share sits in its long cycle, using Stan Weinstein's four stages.<br><br><strong>Uptrend</strong> — above its 200-day average and that average is rising. The only stage this advisor buys.<br><strong>Basing</strong> — recovering, but the long trend hasn't turned up yet.<br><strong>Topping</strong> — still high, but the trend has stopped rising.<br><strong>Downtrend</strong> — below a falling 200-day average. Cheap here usually gets cheaper."],
    rsi: ["RSI (14 day)", "A momentum meter from 0 to 100 that compares recent gains with recent losses.<br><br>Above 70 the share has been bought hard and may be stretched; below 30 it has been sold hard. But in a strong uptrend RSI can sit high for months — it is a thermometer, not a sell signal."],
    from52: ["Distance from 52-week high", "How far below the highest price of the last year. Near zero means it is making new highs — which sounds late but historically tends to continue, because there is no one holding a loss waiting to sell.<br><br>Deeply negative means a real fall that needs explaining."],
    mom6m: ["6-month move", "Return over roughly the last six months. Momentum is the most persistent pattern in markets: what has done well over 6–12 months tends to keep doing well for a while. It also reverses violently at turning points."],
    volatility: ["Volatility (ATR)", "The average daily trading range as a percentage of price. Around 1–2% is calm; above 4% the share swings hard.<br><br>This drives your position size: the wilder the share, the fewer you buy, so a normal bad day costs the same rupees either way."],
    score: ["Technical score", "0–100, combining trend stage (40 points), six-month momentum (15), closeness to its 52-week high (15), position above its averages (20) and orderly volatility (10).<br><br>It ranks candidates. It is <em>not</em> a buy signal — that needs a setup and the right market conditions."],

    /* ---- suggestions ---- */
    setup: ["Setup", "The specific pattern that fired today.<br><br><strong>New 52-week high</strong> — breaking to fresh highs on strength.<br><strong>Pullback to trend</strong> — an established uptrend resting on its 50-day average.<br><strong>Pushing toward highs</strong> — climbing back toward its peak.<br><br>No setup means no suggestion. A stock can score well and still not be actionable today."],
    buyzone: ["Buy zone", "The price range where the plan makes sense. Above it, your stop is too far away and the trade's maths stops working — wait for the next setup rather than chasing."],
    stop: ["Stop / exit price", "The price at which the reason for owning it is proven wrong. Placed below the recent swing low <em>and</em> at least two average daily ranges away, so ordinary noise does not throw you out.<br><br>If the structural stop would risk too much, the answer is fewer shares — never a wider stop."],
    target: ["Targets", "Target 1 is 1.5× your risk, Target 2 is 2.5×. The plan is to sell half at Target 1, move the stop to your entry price so the trade can no longer lose, and let the rest run."],
    rr: ["Risk to reward", "What you stand to make against what you stand to lose. At 1:2.5 you can be right only 4 times in 10 and still finish ahead — which is the whole point of trading with defined levels."],

    /* ---- market regime ---- */
    regime: ["Market state", "The whole market's condition, which decides whether new buying is allowed at all.<br><br><strong>Expansion</strong> — normal, full programme.<br><strong>Caution</strong> — sizes cut, build a shopping list.<br><strong>Stress</strong> — no new trading longs.<br><strong>Crisis</strong> — buy only by the staged plan written when you were calm.<br><br>Most breakouts fail in weak markets. This filter is worth more than any entry pattern."],

    /* ---- fundamentals ---- */
    fscore: ["Fundamental score", "0–100 from the business itself: quality 40 (profitability, margins, debt), growth 25, valuation 25, balance-sheet safety 10.<br><br>Anything the data source does not provide scores neutral and is listed as a gap — never quietly treated as good news."],
    pe: ["P/E ratio", "Price divided by earnings per share — the years of current profit you are paying for one share.<br><br>Only meaningful against the company's own history and its sector. A low P/E on a cyclical business at peak profits is a trap, not a bargain."],
    pb: ["P/B ratio", "Price against book value (assets minus liabilities). Most useful for banks and lenders, where the book <em>is</em> the earning machine, and nearly meaningless for asset-light businesses."],
    roe: ["Return on equity", "Profit as a percentage of shareholders' money. Above 15% sustained is genuinely good — but check whether it comes from a strong business or simply from borrowing a lot."],
    roce: ["Return on capital employed", "Profit against all the capital in the business, debt included. Harder to flatter than ROE. Compare it with a realistic 11–13% cost of capital in India: below that, growth destroys value."],
    opmargin: ["Operating margin", "What is left of each rupee of sales after running costs, before interest and tax. Its <em>trend</em> matters more than its level — a falling margin means input costs are rising faster than prices, or competition is taking the difference."],
    de: ["Debt to equity", "Borrowings against shareholders' money. Under 0.5 is comfortable; above 1.5 means an ordinary bad year can become an existential one, because interest does not wait for the cycle to turn."],
    revgrowth: ["Revenue growth", "How fast sales are compounding. Profit growth without sales growth is cost-cutting, which has a floor."],

    /* ---- castle ---- */
    castle: ["Castle score", "How much of the price is resting on crowd enthusiasm rather than earnings — built from how far the price is stretched above its long-term trend, its six-month run, whether it is pinned at its highs, and how agitated its daily range is.<br><br>High is not automatically bad. It means that if the crowd's mood changes, there is little underneath to catch the price."],
    firm: ["Firm foundation", "The fundamental score used as Malkiel's other pole: how much of the price the business's own earnings and assets actually support."],
    quadrant: ["The four quadrants", "<strong>Firm ground</strong> — value, crowd absent. Usually the best-paid patience.<br><strong>Well-founded castle</strong> — good business <em>and</em> an excited crowd. Comfortable, and the easiest place to overstay.<br><strong>Castle in the air</strong> — the crowd is doing the lifting. You are relying on someone paying more than you did.<br><strong>Neglected</strong> — neither supports it. Cheap alone is not a reason."],
    stretch: ["Stretch above trend", "How far the price sits above its 200-day average. Beyond about 25% the gap has historically closed by the price falling rather than the trend catching up."],

    /* ---- F&O ---- */
    iv: ["Implied volatility", "How much movement option <em>prices</em> currently assume. It is the price of the option, more than direction is.<br><br>High IV: you are paid well to sell options. Low IV: buying them is cheap. This is why the advisor checks volatility before it checks direction."],
    realisedvol: ["Realised volatility", "How much the share has actually moved, annualised. Comparing it with implied volatility tells you whether options are expensive or cheap relative to reality."],
    pcr: ["Put/Call ratio", "Put open interest divided by call open interest. Above ~1.3 the crowd is heavily hedged or bearish; below ~0.7 it is complacent. Extremes are contrarian hints, never signals on their own."],
    maxpain: ["Max pain", "The strike where option buyers collectively lose the most — and therefore writers gain the most. Prices sometimes drift toward it near expiry. Treat it as folklore worth knowing, not physics."],
    spread: ["Spread structures", "Two legs: one bought, one sold. The sold leg pays for part of the trade; the bought leg caps the loss.<br><br>This advisor only ever suggests structures whose worst case is known before you enter. Naked short options — where the loss has no limit — are permanently excluded."],
    maxloss: ["Max loss per lot", "The most this structure can cost you, per lot, whatever the market does. This is your real risk. The margin your broker blocks is <em>not</em> your risk — confusing the two is how F&O accounts die."],
    underlyingtarget: ["Target &amp; stop on the underlying", "Options move for reasons other than direction, so the plan is expressed on the share or index itself — the thing you can actually watch. Reaching the target is your cue to take profit; the stop is your cue to leave."],

    /* ---- deep dive ---- */
    cashconv: ["Cash conversion", "Five years of operating cash flow against five years of reported profit. Below about 60% means profit is being booked but not collected.<br><br>This is the most reliable early warning there is: accounting profit is an opinion, cash is a fact."],
    intcover: ["Interest cover", "How many times operating profit covers the interest bill. Below 3× there is little room for a slowdown before profit goes to lenders instead of owners."],
    debtordays: ["Debtor days", "How long customers take to pay. Rising faster than sales is the classic signature of pushing goods into the channel or of customers in trouble — and it eats the cash that growth was supposed to produce."],
    reinvest: ["Reinvestment rate", "How much operating cash flow goes back into the business. High reinvestment plus high returns is the compounding combination; high reinvestment at low returns quietly destroys value."],
    promoter: ["Promoter holding", "The founding family's stake. High is alignment. A falling stake deserves an explanation before you increase yours — and pledged shares are the fastest-moving governance red flag in Indian markets."],

    /* ---- invest flow ---- */
    core: ["Core", "Index funds — the part of the portfolio that quietly compounds without needing you to be right about any single company."],
    satellite: ["Stock picks", "Individual companies chosen by the screens. Higher potential, higher risk, and every one carries an exit price."],
    cashsleeve: ["Cash", "Deliberately held back, not left over. Cash is what lets you buy when everything is on sale — which only happens when it feels worst."],
    badmonth: ["Worst normal month", "A realistic bad month for this plan — the index sleeve falling with the market, plus the stock sleeve taking the worse of its stop distance or a market shock.<br><br>It deliberately refuses to credit stop-losses fully, because in the month that actually matters, prices gap straight through them."]
  };

  function popover(key, anchor) {
    document.querySelectorAll(".infopop").forEach(function (p) { p.remove(); });
    var g = G[key];
    if (!g) return;
    var pop = document.createElement("div");
    pop.className = "infopop";
    pop.innerHTML = '<strong>' + g[0] + '</strong><p>' + g[1] + '</p>';
    document.body.appendChild(pop);
    var r = anchor.getBoundingClientRect();
    var top = r.bottom + window.scrollY + 8;
    var left = Math.min(r.left + window.scrollX - 10,
                        window.scrollX + document.documentElement.clientWidth - pop.offsetWidth - 14);
    pop.style.top = top + "px";
    pop.style.left = Math.max(window.scrollX + 8, left) + "px";
    setTimeout(function () {
      document.addEventListener("click", function close(ev) {
        if (!pop.contains(ev.target) && ev.target !== anchor) {
          pop.remove(); document.removeEventListener("click", close);
        }
      });
    }, 0);
  }

  function decorate(root) {
    (root || document).querySelectorAll("[data-info]").forEach(function (node) {
      if (node.dataset.infoDone) return;
      node.dataset.infoDone = "1";
      var key = node.dataset.info;
      var b = document.createElement("button");
      b.type = "button"; b.className = "i"; b.textContent = "i";
      b.setAttribute("aria-label", "What is " + ((G[key] || [key])[0]) + "?");
      b.addEventListener("click", function (ev) {
        ev.stopPropagation(); popover(key, b);
      });
      node.appendChild(b);
    });
  }

  window.ADV_INFO = { decorate: decorate, terms: G,
    mark: function (key) { return ' <span data-info="' + key + '"></span>'; } };

  document.addEventListener("DOMContentLoaded", function () { decorate(); });
  decorate();
  // re-decorate whenever tables are re-rendered
  new MutationObserver(function () { decorate(); })
    .observe(document.documentElement, { childList: true, subtree: true });
})();

/* ---- the Guide tab: the same glossary, browsable in one place ---- */
(function () {
  "use strict";
  var GROUPS = [
    ["Price and trend", ["price","day","trend","rsi","from52","mom6m","volatility","score"]],
    ["Trade suggestions", ["setup","buyzone","stop","target","rr"]],
    ["Market conditions", ["regime"]],
    ["Fundamentals", ["fscore","pe","pb","roe","roce","opmargin","de","revgrowth"]],
    ["Castle in the Air", ["castle","firm","quadrant","stretch"]],
    ["Futures and options", ["iv","realisedvol","pcr","maxpain","spread","maxloss","underlyingtarget"]],
    ["Reading a company", ["cashconv","intcover","debtordays","reinvest","promoter"]],
    ["Building a portfolio", ["core","satellite","cashsleeve","badmonth"]]
  ];
  function build() {
    var host = document.getElementById("guideBody");
    if (!host || host.dataset.built) return;
    var G = window.ADV_INFO && window.ADV_INFO.terms;
    if (!G) return;
    host.dataset.built = "1";
    host.innerHTML = GROUPS.map(function (grp) {
      var items = grp[1].filter(function (k) { return G[k]; }).map(function (k) {
        return '<div style="padding:13px 0;border-bottom:1px solid var(--surface2)">' +
          '<strong style="font-family:Archivo,sans-serif;font-size:14px">' + G[k][0] + '</strong>' +
          '<p style="margin:5px 0 0;color:var(--muted);font-size:13.5px;line-height:1.55">' +
          G[k][1] + '</p></div>';
      }).join("");
      return '<h2>' + grp[0] + '</h2><div class="card" style="padding:6px 20px">' + items + '</div>';
    }).join("");
  }
  document.addEventListener("click", function (ev) {
    var t = ev.target.closest ? ev.target.closest("nav button") : null;
    if (t && t.dataset.tab === "guide") setTimeout(build, 0);
  });
})();
