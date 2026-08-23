// GET /api/news?symbol=RELIANCE        — company news
// GET /api/news?market=1               — market-wide news
// Source: Google News RSS (India edition) — reliable from cloud IPs, unlike the
// exchange APIs. Headlines are classified into event types and scored for
// direction, so the verdict engine can reason about them rather than just list them.

import { jsonResponse, stripTags } from "./_lib.mjs";

const FEEDS = {
  market: "https://news.google.com/rss/search?q=" +
    encodeURIComponent("Nifty OR Sensex stock market India when:3d") +
    "&hl=en-IN&gl=IN&ceid=IN:en",
};

function companyFeed(symbol, name) {
  const q = `"${name || symbol}" (share OR stock OR results OR NSE) when:14d`;
  return "https://news.google.com/rss/search?q=" + encodeURIComponent(q) +
    "&hl=en-IN&gl=IN&ceid=IN:en";
}

/* Event taxonomy. Weight is the direction and force of the event, -3..+3.
   Order matters: the first pattern that matches wins, so specific beats generic. */
const EVENTS = [
  { k: "fraud",        w: -3, re: /\b(fraud|scam|siphon|forensic audit|sebi bars|insider trading|money launder)/i,
    label: "Fraud or investigation" },
  { k: "default",      w: -3, re: /\b(default|insolven|nclt|bankrupt|debt restructur|credit rating cut|downgrade[ds]? to)/i,
    label: "Credit or solvency event" },
  { k: "regulator",    w: -2, re: /\b(sebi (?:notice|order|penalt)|rbi (?:action|penalt|restrict)|usfda (?:warning|import alert|observation)|show cause|penalt)/i,
    label: "Regulatory action" },
  { k: "litigation",   w: -2, re: /\b(lawsuit|litigation|court (?:order|case)|tribunal|arbitration|tax demand|gst notice)/i,
    label: "Litigation or tax demand" },
  { k: "pledge",       w: -2, re: /\b(pledg|promoter (?:stake sale|sells|selling|offload))/i,
    label: "Promoter selling or pledging" },
  { k: "downgrade",    w: -2, re: /\b(downgrade|cuts? target|slash(?:es)? target|underperform|reduce rating|sell rating)/i,
    label: "Analyst downgrade" },
  { k: "profitfall",   w: -2, re: /\b(profit (?:falls|drops|declines|slumps|plunges)|loss widens|posts loss|misses estimates|weak (?:results|quarter))/i,
    label: "Weak results" },
  { k: "exit",         w: -2, re: /\b(resigns|steps down|quits|ceo exit|cfo exit|auditor resign)/i,
    label: "Senior management exit" },
  { k: "upgrade",      w: 2,  re: /\b(upgrade|raises? target|hikes? target|outperform|buy rating|top pick)/i,
    label: "Analyst upgrade" },
  { k: "profitrise",   w: 2,  re: /\b(profit (?:rises|jumps|surges|soars|up \d)|beats estimates|strong (?:results|quarter)|record (?:profit|revenue))/i,
    label: "Strong results" },
  { k: "order",        w: 2,  re: /\b(order win|order book|(?:bags?|wins?|secures?|receives?)\b[^.]{0,45}?\b(?:order|contract|deal|mandate|tender))/i,
    label: "Order or contract win" },
  { k: "expansion",    w: 1,  re: /\b(capex|new plant|capacity expansion|acquisition|acquires|merger|joint venture|stake buy)/i,
    label: "Expansion or M&A" },
  { k: "policy",       w: 1,  re: /\b(government|policy|pli|subsid|budget|duty|tariff|gst rate|rbi (?:policy|rate)|repo rate)/i,
    label: "Policy or government action" },
  { k: "payout",       w: 1,  re: /\b(dividend|buyback|bonus issue|stock split)/i,
    label: "Shareholder payout" },
  { k: "results",      w: 0,  re: /\b(q[1-4] results|quarterly results|earnings|board meeting)/i,
    label: "Results scheduled or reported" },
];

function classify(title) {
  for (const e of EVENTS) if (e.re.test(title)) return e;
  return { k: "general", w: 0, label: "General coverage" };
}

function parseRss(xml, limit) {
  const items = [];
  for (const m of xml.matchAll(/<item>([\s\S]*?)<\/item>/g)) {
    const block = m[1];
    const title = stripTags((block.match(/<title>([\s\S]*?)<\/title>/) || [, ""])[1]);
    if (!title) continue;
    const link = stripTags((block.match(/<link>([\s\S]*?)<\/link>/) || [, ""])[1]);
    const pub = stripTags((block.match(/<pubDate>([\s\S]*?)<\/pubDate>/) || [, ""])[1]);
    const src = stripTags((block.match(/<source[^>]*>([\s\S]*?)<\/source>/) || [, ""])[1]);
    const ev = classify(title);
    const ageDays = pub ? (Date.now() - new Date(pub).getTime()) / 86400000 : null;
    items.push({
      title, link, published: pub, source: src || "news",
      ageDays: ageDays == null ? null : +ageDays.toFixed(1),
      event: ev.k, eventLabel: ev.label, weight: ev.w,
    });
    if (items.length >= (limit || 25)) break;
  }
  return items;
}

/** Net news pressure: recent and strong events count for more. */
function pressure(items) {
  let score = 0, weighted = 0;
  items.forEach((i) => {
    if (!i.weight) return;
    const decay = i.ageDays == null ? 0.5 : Math.max(0.15, 1 - i.ageDays / 14);
    score += i.weight * decay;
    weighted += Math.abs(i.weight) * decay;
  });
  return {
    net: +score.toFixed(2),
    intensity: +weighted.toFixed(2),
    tone: score > 1.5 ? "positive" : score < -1.5 ? "negative" : "mixed",
  };
}

export default async (req) => {
  const url = new URL(req.url);
  const symbol = (url.searchParams.get("symbol") || "").toUpperCase().trim();
  const name = url.searchParams.get("name") || "";
  const market = url.searchParams.get("market");

  if (!market && !/^[A-Z0-9&.-]{1,20}$/.test(symbol)) {
    return jsonResponse({ error: "bad symbol" }, { status: 400, maxAge: 60 });
  }
  const feed = market ? FEEDS.market : companyFeed(symbol, name);
  try {
    const r = await fetch(feed, {
      headers: { "User-Agent": "Mozilla/5.0 (advisor-360 personal console)",
                 "Accept": "application/rss+xml, application/xml, text/xml" },
    });
    if (!r.ok) throw new Error(`feed ${r.status}`);
    const items = parseRss(await r.text(), market ? 18 : 20);
    return jsonResponse({
      symbol: market ? "MARKET" : symbol,
      items,
      pressure: pressure(items),
      materialCount: items.filter((i) => Math.abs(i.weight) >= 2).length,
    }, { maxAge: 900 });
  } catch (e) {
    return jsonResponse({ symbol: symbol || "MARKET", error: "news unavailable",
                          detail: e.message, items: [] }, { maxAge: 120 });
  }
};

export const config = { path: "/api/news" };
