// The tradeable universe. NSE's constituent CSV is tried first; when it refuses
// (it often does from cloud IPs) this curated list of liquid NSE names is used,
// and the store records WHICH source supplied it — never a silent substitution.

export const FALLBACK_UNIVERSE = [
  "RELIANCE","TCS","HDFCBANK","ICICIBANK","INFY","HINDUNILVR","ITC","SBIN","BHARTIARTL",
  "LT","KOTAKBANK","AXISBANK","BAJFINANCE","ASIANPAINT","MARUTI","TITAN","SUNPHARMA",
  "ULTRACEMCO","NESTLEIND","WIPRO","HCLTECH","TECHM","POWERGRID","NTPC","TATAMOTORS",
  "TATASTEEL","JSWSTEEL","HINDALCO","COALINDIA","ONGC","BPCL","IOC","GAIL","ADANIPORTS",
  "GRASIM","DRREDDY","CIPLA","DIVISLAB","LUPIN","AUROPHARMA","BRITANNIA","DABUR",
  "GODREJCP","MARICO","COLPAL","PIDILITIND","BERGEPAINT","HAVELLS","VOLTAS","SIEMENS",
  "ABB","BEL","BHEL","INDUSINDBK","BAJAJFINSV","BAJAJ-AUTO","HEROMOTOCO","EICHERMOT",
  "M&M","TVSMOTOR","ASHOKLEY","SHREECEM","AMBUJACEM","ACC","DALBHARAT","JINDALSTEL",
  "SAIL","NMDC","VEDL","HINDZINC","UPL","SRF","TATACHEM","DEEPAKNTR","AARTIIND",
  "APOLLOHOSP","MAXHEALTH","FORTIS","TORNTPHARM","ALKEM","ZYDUSLIFE","BIOCON",
  "INDIGO","TRENT","DMART","JUBLFOOD","PAGEIND","BATAINDIA","PETRONET","IGL",
  "MGL","TATAPOWER","ADANIENT","ADANIGREEN","LTIM","PERSISTENT","COFORGE","MPHASIS",
  "OFSS","NAUKRI","ZOMATO","PAYTM","POLICYBZR","IRCTC","CONCOR","BANKBARODA",
  "PNB","CANBK","IDFCFIRSTB","FEDERALBK","AUBANK","BANDHANBNK","CHOLAFIN","MUTHOOTFIN",
  "SBICARD","HDFCLIFE","SBILIFE","ICICIPRULI","ICICIGI","LICI","PFC","RECLTD",
  "NIFTYBEES","JUNIORBEES",
];

export const INDEX_SYMBOLS = ["^NSEI", "^NSEBANK"];

export async function fetchNseUniverse() {
  const url = "https://nsearchives.nseindia.com/content/indices/ind_nifty500list.csv";
  const resp = await fetch(url, {
    headers: {
      "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 " +
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
      "Accept": "text/csv,*/*",
      "Referer": "https://www.nseindia.com/",
    },
  });
  if (!resp.ok) throw new Error(`NSE constituent list: http ${resp.status}`);
  const text = await resp.text();
  const lines = text.trim().split(/\r?\n/);
  const header = lines[0].split(",").map((h) => h.trim().toLowerCase());
  const symIdx = header.indexOf("symbol");
  if (symIdx < 0) throw new Error("NSE constituent list: no symbol column");
  const symbols = lines.slice(1)
    .map((l) => (l.split(",")[symIdx] || "").trim().toUpperCase())
    .filter((s) => /^[A-Z0-9&.-]{1,20}$/.test(s));
  if (symbols.length < 100) throw new Error("NSE constituent list: implausibly short");
  return symbols;
}

/** Returns { symbols, source, note } — source is always stated. */
export async function resolveUniverse() {
  try {
    const symbols = await fetchNseUniverse();
    return { symbols, source: "NSE Nifty 500 constituent list", note: null };
  } catch (err) {
    return {
      symbols: FALLBACK_UNIVERSE,
      source: "curated liquid-NSE list (built in)",
      note: `NSE constituent list unavailable (${err.message}), so the built-in ` +
            `list of ${FALLBACK_UNIVERSE.length} liquid names was used instead.`,
    };
  }
}
