// SEC EDGAR — the official source, and the reason the US side can be stricter
// about evidence than the India side.
//
// EDGAR publishes every XBRL fact a company has ever filed, free, keyless, with
// the filing date attached to each number. That last part matters more than it
// sounds: it means a figure can be used *point-in-time* — as it was known on the
// day it was filed — instead of the restated version visible today. Backtests
// built on restated fundamentals are the classic way to discover an edge that
// never existed.
//
// The SEC asks for two things in return, and both are honoured here: a
// User-Agent naming the app and a contact address, and no more than 10 requests
// a second. Missing the User-Agent is the usual cause of a 403.

const UA = process.env.SEC_CONTACT
  ? `Astraveda Wealth Management ${process.env.SEC_CONTACT}`
  : "Astraveda Wealth Management (personal research console) contact@astraveda.invalid";

export const secHeaders = () => ({
  "User-Agent": UA,
  "Accept": "application/json",
  "Accept-Encoding": "gzip, deflate",
  "Host": "data.sec.gov",
});

/* ---------------- ticker → CIK ---------------- */
// The SEC keys everything by CIK, never by ticker. This map is small and
// changes rarely, so one fetch serves the life of the function instance.
let tickerMap = { at: 0, map: null };
const MAP_TTL = 24 * 60 * 60 * 1000;

export async function cikFor(ticker) {
  if (!tickerMap.map || Date.now() - tickerMap.at > MAP_TTL) {
    const r = await fetch("https://www.sec.gov/files/company_tickers.json",
      { headers: { ...secHeaders(), Host: "www.sec.gov" } });
    if (!r.ok) throw new Error(`ticker map http ${r.status}`);
    const j = await r.json();
    const map = new Map();
    for (const k of Object.keys(j)) {
      const row = j[k];
      if (row?.ticker) map.set(String(row.ticker).toUpperCase(),
        { cik: String(row.cik_str).padStart(10, "0"), name: row.title });
    }
    if (!map.size) throw new Error("ticker map parsed to nothing");
    tickerMap = { at: Date.now(), map };
  }
  const hit = tickerMap.map.get(ticker.toUpperCase());
  if (!hit) throw new Error(`${ticker} is not in the SEC ticker map`);
  return hit;
}

/* ---------------- reading the facts ---------------- */
// A concept can be reported under several tag names depending on the filer's
// taste and the year. Try them in order of how specific they are.
export const TAGS = {
  revenue: ["RevenueFromContractWithCustomerExcludingAssessedTax",
            "RevenueFromContractWithCustomerIncludingAssessedTax",
            "Revenues", "SalesRevenueNet", "SalesRevenueGoodsNet"],
  netIncome: ["NetIncomeLoss", "ProfitLoss"],
  operatingIncome: ["OperatingIncomeLoss"],
  assets: ["Assets"],
  currentAssets: ["AssetsCurrent"],
  currentLiabilities: ["LiabilitiesCurrent"],
  equity: ["StockholdersEquity",
           "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"],
  debtLong: ["LongTermDebtNoncurrent", "LongTermDebt"],
  debtShort: ["LongTermDebtCurrent", "DebtCurrent"],
  cash: ["CashAndCashEquivalentsAtCarryingValue", "CashCashEquivalentsAndShortTermInvestments"],
  interest: ["InterestExpense", "InterestIncomeExpenseNet", "InterestExpenseNonoperating"],
  eps: ["EarningsPerShareDiluted", "EarningsPerShareBasicAndDiluted"],
  shares: ["WeightedAverageNumberOfDilutedSharesOutstanding",
           "WeightedAverageNumberOfSharesOutstandingBasic"],
  operatingCash: ["NetCashProvidedByUsedInOperatingActivities",
                  "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"],
  capex: ["PaymentsToAcquirePropertyPlantAndEquipment",
          "PaymentsToAcquireProductiveAssets"],
  dividendsPaid: ["PaymentsOfDividendsCommonStock", "PaymentsOfDividends"],
};

/**
 * Annual series for one concept, newest last.
 * Only 10-K figures are taken: mixing annual and quarterly is how a revenue
 * line silently drops by three quarters.
 */
export function annualSeries(facts, names) {
  const gaap = facts?.facts?.["us-gaap"] || {};
  for (const name of names) {
    const units = gaap[name]?.units;
    if (!units) continue;
    const rows = units.USD || units["USD/shares"] || units.shares ||
                 units[Object.keys(units)[0]];
    if (!rows) continue;

    // One value per fiscal year: the 10-K, and if a year was amended the
    // latest filing of it wins.
    const byYear = new Map();
    for (const r of rows) {
      if (r.form !== "10-K" && r.form !== "10-K/A") continue;
      if (r.fp && r.fp !== "FY") continue;
      // A duration fact must cover a full year; a 90-day slice is a quarter
      // mislabelled, and including it understates the year badly.
      if (r.start && r.end) {
        const days = (new Date(r.end) - new Date(r.start)) / 86400000;
        if (days < 300 || days > 400) continue;
      }
      const y = r.fy;
      if (y == null) continue;
      const prev = byYear.get(y);
      if (!prev || new Date(r.filed) > new Date(prev.filed)) {
        byYear.set(y, { year: y, value: r.val, filed: r.filed, end: r.end, form: r.form });
      }
    }
    if (byYear.size) {
      return { tag: name, series: [...byYear.values()].sort((a, b) => a.year - b.year) };
    }
  }
  return null;
}

export const latest = (s) => (s && s.series.length ? s.series[s.series.length - 1] : null);
export const priorTo = (s, n = 1) =>
  (s && s.series.length > n ? s.series[s.series.length - 1 - n] : null);

/** Compound annual growth across the series, or null when it cannot be trusted. */
export function cagr(s, years = 3) {
  if (!s || s.series.length < 2) return null;
  const end = s.series[s.series.length - 1];
  const startIdx = Math.max(0, s.series.length - 1 - years);
  const start = s.series[startIdx];
  const n = end.year - start.year;
  // A sign change makes a growth rate meaningless — a loss narrowing to a
  // smaller loss is not "growth", and a negative base produces nonsense.
  if (n <= 0 || start.value <= 0 || end.value <= 0) return null;
  return Math.pow(end.value / start.value, 1 / n) - 1;
}
