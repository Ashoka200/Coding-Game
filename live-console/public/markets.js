/* Two markets, one doctrine.

   The analysis engine does not care which country a company trades in: a
   business with widening margins and falling debt is the same finding in
   Mumbai and in New York. What genuinely differs is plumbing and law — the
   trading clock, the currency, where the statements come from, and the rules
   that decide what an investment actually nets you.

   So everything market-specific lives here and nowhere else. Adding a third
   market should mean adding an entry to this file, not editing screens. */
(function () {
  "use strict";

  var KEY = "astraveda-market";

  var MARKETS = {
    in: {
      id: "in", label: "India", short: "IN", flag: "🇮🇳",
      currency: "INR", symbol: "₹", locale: "en-IN",
      exchange: "NSE", clockLabel: "IST",
      indexKeys: ["NIFTY50", "BANKNIFTY"],

      api: {
        quotes:  function (syms) { return "/api/quotes?symbols=" + syms; },
        live:    function (syms) { return "/api/live?index=1&symbols=" + syms; },
        fund:    function (syms) { return "/api/fundamentals?symbols=" + syms; },
        news:    function (sym)  { return "/api/news?symbol=" + sym; },
        deep:    function (sym)  { return "/api/deepdive?symbol=" + sym; },
        own:     function (sym)  { return "/api/ownership?symbol=" + sym; },
      },

      universe: ["RELIANCE","TCS","HDFCBANK","ICICIBANK","INFY","LT","BHARTIARTL",
        "ITC","SBIN","TITAN","SUNPHARMA","AXISBANK","MARUTI","ASIANPAINT","BAJFINANCE",
        "HCLTECH","ULTRACEMCO","NESTLEIND","KOTAKBANK","TATAMOTORS","TATASTEEL","WIPRO"],
      core: [{ symbol:"NIFTYBEES", desc:"Nifty 50 index fund", share:0.70 },
             { symbol:"JUNIORBEES", desc:"Nifty Next 50 index fund", share:0.30 }],

      /* Round lots do not exist in Indian cash equity; a single share is fine. */
      minQty: 1,
      notes: [],
    },

    us: {
      id: "us", label: "United States", short: "US", flag: "🇺🇸",
      currency: "USD", symbol: "$", locale: "en-US",
      exchange: "NYSE / Nasdaq", clockLabel: "ET",
      indexKeys: ["^GSPC", "^NDX", "^VIX"],

      api: {
        quotes:  function (syms) { return "/api/quotes?market=us&symbols=" + syms; },
        live:    function (syms) { return "/api/us-live?index=1&symbols=" + syms; },
        fund:    function (syms, price) {
          return "/api/us-fundamentals?symbols=" + syms + (price ? "&price=" + price : "");
        },
        news:    function (sym)  { return "/api/news?market=us&symbol=" + sym; },
        deep:    null,          // the Indian sector map does not transfer
        own:     null,          // 13F/Form 4 ingestion is not built yet
      },

      universe: ["AAPL","MSFT","NVDA","GOOGL","AMZN","META","AVGO","TSLA","LLY","JPM",
        "V","UNH","XOM","MA","COST","HD","PG","JNJ","ABBV","MRK","AMD","CRM"],
      core: [{ symbol:"VOO",  desc:"S&P 500 index fund", share:0.70 },
             { symbol:"QQQM", desc:"Nasdaq 100 index fund", share:0.30 }],

      minQty: 1,

      /* The part no US retail app shows an Indian investor: what the money
         actually costs to send, and what the gain actually nets after two tax
         authorities have had their say. Figures are the position for FY 2026-27
         and tax law moves every Budget — the page says so, and says to confirm
         with a chartered accountant before acting. */
      notes: [
        { k: "Sending the money",
          t: "Under the Liberalised Remittance Scheme you may remit up to $250,000 " +
             "per financial year. TCS is nil up to ₹10 lakh of LRS remittances in a " +
             "year (raised from ₹7 lakh on 1 April 2026) and 20% above that. TCS is " +
             "not a cost — it is credited against your tax liability or refunded, " +
             "though it does tie up the cash until you file." },
        { k: "Dividends",
          t: "The US withholds 25% on dividends paid to Indian residents, and the " +
             "India–US treaty does not reduce it below that for ordinary investors. " +
             "You can claim it as a foreign tax credit in India — but Form 67 must be " +
             "filed before your return, or the credit is lost." },
        { k: "Capital gains",
          t: "Section 111A does not apply to shares listed outside India, so the " +
             "familiar 20% short-term rate is not available here. Gains on holdings " +
             "of 24 months or less are added to your income and taxed at your slab " +
             "rate. Beyond 24 months they are long-term at 12.5% without indexation. " +
             "Holding past the 24-month mark is often worth more than the trade you " +
             "were considering." },
        { k: "Disclosure",
          t: "Foreign shares must be reported in Schedule FA of your ITR whether or " +
             "not they produced income. Omission is penalised under the Black Money " +
             "Act, which is a far worse outcome than the tax itself." },
        { k: "The currency is part of the return",
          t: "You buy in dollars and spend in rupees, so USD/INR is a second " +
             "position you hold whether you meant to or not. A rupee that weakens 5% " +
             "adds 5% to your return in rupees; one that strengthens takes it away." },
        { k: "Day trading is restricted",
          t: "In a US margin account under $25,000, more than three day trades in " +
             "five business days marks you a pattern day trader and the account is " +
             "restricted for 90 days. Cash accounts avoid the rule but must wait for " +
             "T+1 settlement before the money can be used again." },
        { k: "Halts work differently",
          t: "Individual stocks are halted by limit-up/limit-down bands, and the " +
             "whole market halts at 7%, 13% and 20% falls. A halted stock cannot be " +
             "exited at any price, which is why position size matters more here than " +
             "a stop-loss does." },
        { k: "Extended hours are not the price",
          t: "Pre-market and after-hours trades are real but thin, and the gap they " +
             "show frequently does not survive the opening auction. This app labels " +
             "them and refuses to treat them as the day's price." },
      ],
      disclaimer: "Tax positions are as understood for FY 2026-27 and change with " +
        "every Budget. Confirm with a chartered accountant before you act on any of it.",
    },
  };

  var current = "in";
  try {
    var saved = localStorage.getItem(KEY);
    if (saved && MARKETS[saved]) current = saved;
  } catch (e) {}

  var subs = [];

  var M = {
    all: MARKETS,
    get: function (id) { return MARKETS[id] || MARKETS.in; },
    current: function () { return MARKETS[current]; },
    id: function () { return current; },
    set: function (id) {
      if (!MARKETS[id] || id === current) return false;
      current = id;
      try { localStorage.setItem(KEY, id); } catch (e) {}
      subs.forEach(function (fn) { try { fn(MARKETS[id]); } catch (e) {} });
      return true;
    },
    onChange: function (fn) { subs.push(fn); },

    /* Money in the current market's own currency and digit grouping. Indian
       lakh/crore grouping applied to dollars would be a small daily lie. */
    money: function (n, d) {
      var m = MARKETS[current];
      if (n == null || isNaN(n)) return "—";
      return m.symbol + Number(n).toLocaleString(m.locale,
        { maximumFractionDigits: d == null ? 0 : d,
          minimumFractionDigits: d == null ? 0 : d });
    },
    number: function (n, d) {
      var m = MARKETS[current];
      if (n == null || isNaN(n)) return "—";
      return Number(n).toLocaleString(m.locale,
        { maximumFractionDigits: d == null ? 2 : d,
          minimumFractionDigits: d == null ? 2 : d });
    },

    /* Holdings are per market — the same ticker can name different companies,
       and mixing currencies in one total would be meaningless. */
    holdingsKey: function () { return current === "in" ? "holdings" : "holdings:" + current; },
    capitalKey: function () { return current === "in" ? "startCapital" : "startCapital:" + current; },
  };

  window.ADV_MARKETS = M;
})();
