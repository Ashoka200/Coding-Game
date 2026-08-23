// Shared scraping + parsing helpers for the data functions.

export const BROWSER_UA =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 " +
  "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36";

export function browserHeaders(extra = {}) {
  return {
    "User-Agent": BROWSER_UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-IN,en-GB;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate",
    "Cache-Control": "no-cache",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Upgrade-Insecure-Requests": "1",
    ...extra,
  };
}

/** Collect Set-Cookie pairs from a response into a request-ready cookie string. */
export function harvestCookies(resp, existing = "") {
  const jar = new Map();
  existing.split(";").forEach((c) => {
    const [k, ...v] = c.trim().split("=");
    if (k && v.length) jar.set(k, v.join("="));
  });
  const raw = typeof resp.headers.getSetCookie === "function"
    ? resp.headers.getSetCookie()
    : (resp.headers.get("set-cookie") || "").split(/,(?=[^;]+=[^;]+)/);
  raw.filter(Boolean).forEach((line) => {
    const [pair] = line.split(";");
    const [k, ...v] = pair.trim().split("=");
    if (k && v.length) jar.set(k, v.join("="));
  });
  return [...jar.entries()].map(([k, v]) => `${k}=${v}`).join("; ");
}

export function stripTags(html) {
  return html
    .replace(/<script[\s\S]*?<\/script>/gi, " ")
    .replace(/<[^>]+>/g, " ")
    .replace(/&nbsp;/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&#39;|&rsquo;/g, "'")
    .replace(/&quot;/g, '"')
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/\s+/g, " ")
    .trim();
}

/** "1,234.5" -> 1234.5 ; "12%" -> 12 ; "-" -> null */
export function toNum(text) {
  if (text == null) return null;
  const cleaned = String(text).replace(/[,%₹\s]/g, "").replace(/[^0-9.\-]/g, "");
  if (!cleaned || cleaned === "-" || cleaned === ".") return null;
  const n = Number(cleaned);
  return Number.isFinite(n) ? n : null;
}

/**
 * Parse the first <table> inside an HTML fragment into
 * { headers: [...], rows: [{ label, values: [...] }] }.
 */
export function parseTable(fragment) {
  const tableMatch = fragment.match(/<table[\s\S]*?<\/table>/i);
  if (!tableMatch) return null;
  const table = tableMatch[0];

  const headRow = table.match(/<thead[\s\S]*?<\/thead>/i);
  let headers = [];
  if (headRow) {
    headers = [...headRow[0].matchAll(/<th[^>]*>([\s\S]*?)<\/th>/gi)]
      .map((m) => stripTags(m[1]));
  }

  const bodyPart = table.match(/<tbody[\s\S]*?<\/tbody>/i);
  const body = bodyPart ? bodyPart[0] : table;
  const rows = [];
  for (const tr of body.matchAll(/<tr[^>]*>([\s\S]*?)<\/tr>/gi)) {
    const cells = [...tr[1].matchAll(/<t[dh][^>]*>([\s\S]*?)<\/t[dh]>/gi)]
      .map((m) => stripTags(m[1]));
    if (!cells.length) continue;
    const label = cells[0].replace(/\s*\+\s*$/, "").trim();
    if (!label) continue;
    rows.push({ label, values: cells.slice(1).map(toNum), raw: cells.slice(1) });
  }
  return { headers, rows };
}

/** Find a row whose label starts with / contains any of the given names. */
export function findRow(table, names) {
  if (!table) return null;
  const lowered = names.map((n) => n.toLowerCase());
  for (const row of table.rows) {
    const l = row.label.toLowerCase();
    if (lowered.some((n) => l === n || l.startsWith(n) || l.includes(n))) return row;
  }
  return null;
}

/** Extract <section id="..."> ... </section> by id. */
export function section(html, id) {
  const re = new RegExp(`<section[^>]*id=["']${id}["'][\\s\\S]*?<\\/section>`, "i");
  const m = html.match(re);
  return m ? m[0] : null;
}

export function pctChange(series) {
  const clean = (series || []).filter((v) => v != null && Number.isFinite(v));
  if (clean.length < 2) return null;
  const first = clean[0], last = clean[clean.length - 1];
  if (!first || first <= 0) return null;
  return Math.pow(last / first, 1 / (clean.length - 1)) - 1;   // CAGR per period
}

export function jsonResponse(body, { status = 200, maxAge = 3600 } = {}) {
  return Response.json(body, {
    status,
    headers: {
      "Cache-Control": `public, max-age=${maxAge}, stale-while-revalidate=${maxAge * 6}`,
      "Access-Control-Allow-Origin": "*",
    },
  });
}
