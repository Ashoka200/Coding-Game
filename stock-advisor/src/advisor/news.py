"""News ingestion and event classification (mirrors live-console/news.mjs).

Headlines are third-party claims, not verified fact. This module classifies and
weights them so downstream logic can *reason* about them; it never treats a
headline as a figure.
"""
from __future__ import annotations

import re
import urllib.parse
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import requests

FEED = ("https://news.google.com/rss/search?q={q}&hl=en-IN&gl=IN&ceid=IN:en")
TIMEOUT = 20

# (key, weight, label, pattern) — order matters: specific before generic.
EVENTS = [
    ("fraud", -3, "Fraud or investigation",
     r"\b(fraud|scam|siphon|forensic audit|sebi bars|insider trading|money launder)"),
    ("default", -3, "Credit or solvency event",
     r"\b(default|insolven|nclt|bankrupt|debt restructur|rating cut|downgraded to)"),
    ("regulator", -2, "Regulatory action",
     r"\b(sebi (notice|order|penalt)|rbi (action|penalt|restrict)|"
     r"usfda (warning|import alert|observation)|show cause|penalt)"),
    ("litigation", -2, "Litigation or tax demand",
     r"\b(lawsuit|litigation|court (order|case)|tribunal|arbitration|tax demand|gst notice)"),
    ("pledge", -2, "Promoter selling or pledging",
     r"\b(pledg|promoter (stake sale|sells|selling|offload))"),
    ("downgrade", -2, "Analyst downgrade",
     r"\b(downgrade|cuts? target|slash(es)? target|underperform|sell rating)"),
    ("profitfall", -2, "Weak results",
     r"\b(profit (falls|drops|declines|slumps|plunges)|loss widens|posts loss|"
     r"misses estimates|weak (results|quarter))"),
    ("exit", -2, "Senior management exit",
     r"\b(resigns|steps down|quits|ceo exit|cfo exit|auditor resign)"),
    ("upgrade", 2, "Analyst upgrade",
     r"\b(upgrade|raises? target|hikes? target|outperform|buy rating|top pick)"),
    ("profitrise", 2, "Strong results",
     r"\b(profit (rises|jumps|surges|soars)|beats estimates|strong (results|quarter)|"
     r"record (profit|revenue))"),
    ("order", 2, "Order or contract win",
     r"\b(order win|order book|(bags?|wins?|secures?|receives?)\b[^.]{0,45}?"
     r"\b(order|contract|deal|mandate|tender))"),
    ("expansion", 1, "Expansion or M&A",
     r"\b(capex|new plant|capacity expansion|acquisition|acquires|merger|joint venture)"),
    ("policy", 1, "Policy or government action",
     r"\b(government|policy|pli|subsid|budget|duty|tariff|gst rate|repo rate)"),
    ("payout", 1, "Shareholder payout", r"\b(dividend|buyback|bonus issue|stock split)"),
    ("results", 0, "Results scheduled or reported",
     r"\b(q[1-4] results|quarterly results|earnings|board meeting)"),
]
COMPILED = [(k, w, l, re.compile(p, re.I)) for k, w, l, p in EVENTS]


@dataclass
class NewsItem:
    title: str
    link: str
    source: str
    published: str | None
    age_days: float | None
    event: str
    event_label: str
    weight: int

    def to_dict(self) -> dict:
        return asdict(self)


def classify(title: str) -> tuple[str, int, str]:
    for key, weight, label, pattern in COMPILED:
        if pattern.search(title):
            return key, weight, label
    return "general", 0, "General coverage"


def _strip(x: str) -> str:
    return re.sub(r"<[^>]+>", " ", x).replace("&amp;", "&").replace("&#39;", "'").strip()


def fetch_news(symbol: str, name: str | None = None, days: int = 14,
               limit: int = 20) -> list[NewsItem]:
    """Company news. Returns [] when the feed is unreachable — never invents items."""
    query = f'"{name or symbol}" (share OR stock OR results OR NSE) when:{days}d'
    url = FEED.format(q=urllib.parse.quote(query))
    resp = requests.get(url, timeout=TIMEOUT,
                        headers={"User-Agent": "advisor-360/1.0",
                                 "Accept": "application/rss+xml, application/xml"})
    resp.raise_for_status()
    items: list[NewsItem] = []
    now = datetime.now(timezone.utc)
    for block in re.findall(r"<item>(.*?)</item>", resp.text, re.S)[:limit]:
        title = _strip(re.search(r"<title>(.*?)</title>", block, re.S).group(1)) \
            if re.search(r"<title>(.*?)</title>", block, re.S) else ""
        if not title:
            continue
        link_m = re.search(r"<link>(.*?)</link>", block, re.S)
        pub_m = re.search(r"<pubDate>(.*?)</pubDate>", block, re.S)
        src_m = re.search(r"<source[^>]*>(.*?)</source>", block, re.S)
        age = None
        published = _strip(pub_m.group(1)) if pub_m else None
        if published:
            try:
                age = round((now - parsedate_to_datetime(published)).total_seconds() / 86400, 1)
            except (TypeError, ValueError):
                age = None
        key, weight, label = classify(title)
        items.append(NewsItem(title=title, link=_strip(link_m.group(1)) if link_m else "",
                              source=_strip(src_m.group(1)) if src_m else "news",
                              published=published, age_days=age,
                              event=key, event_label=label, weight=weight))
    return items


def pressure(items: list[NewsItem]) -> dict:
    """Recency-weighted net direction of the news flow."""
    net = 0.0
    intensity = 0.0
    for i in items:
        if not i.weight:
            continue
        decay = 0.5 if i.age_days is None else max(0.15, 1 - i.age_days / 14)
        net += i.weight * decay
        intensity += abs(i.weight) * decay
    tone = "positive" if net > 1.5 else "negative" if net < -1.5 else "mixed"
    return {"net": round(net, 2), "intensity": round(intensity, 2), "tone": tone,
            "material_count": sum(1 for i in items if abs(i.weight) >= 2)}
