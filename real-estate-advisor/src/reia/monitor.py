"""Government-signal monitor: sweep public sources, classify, match to corridors.

Parsing is BeautifulSoup end to end — RSS via the XML parser, listing pages via
CSS selectors. Government sites change markup and go down without notice, so every
source failure is logged and skipped, never fatal (a dead source must not kill the
sweep). Rule-based keyword classification is the fast path; `ai.classify_event`
optionally enriches stored events with severity/stage hints.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

from . import config, db


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_rss(xml_text: str) -> list[dict]:
    soup = BeautifulSoup(xml_text, "xml")
    items = []
    for it in soup.find_all("item"):
        title = it.title.get_text(strip=True) if it.title else ""
        if not title:
            continue
        items.append({
            "title": title,
            "url": it.link.get_text(strip=True) if it.link else "",
            "body": it.description.get_text(strip=True) if it.description else "",
        })
    return items


def parse_listing(html_text: str, selector: str, base_url: str = "") -> list[dict]:
    soup = BeautifulSoup(html_text, "lxml")
    items = []
    for a in soup.select(selector):
        title = a.get_text(" ", strip=True)
        href = a.get("href") or ""
        if len(title) < 25:          # skip nav links; real notices have long titles
            continue
        if href and not href.startswith("http"):
            href = base_url.rstrip("/") + "/" + href.lstrip("/")
        items.append({"title": title, "url": href, "body": ""})
    return items


def classify(text: str) -> list[str]:
    """Rule-based event taxonomy from config.EVENT_KEYWORDS."""
    low = text.lower()
    return [cat for cat, kws in config.EVENT_KEYWORDS.items()
            if any(k in low for k in kws)]


def match_corridors(text: str, corridors: list[tuple[str, str]]) -> list[str]:
    """corridors: [(slug, comma-keywords)] → slugs whose any keyword appears."""
    low = text.lower()
    return [slug for slug, kws in corridors
            if any(k.strip() and k.strip() in low for k in kws.split(","))]


def store_items(items: list[dict], source: str, region: str) -> int:
    """Classify + corridor-match + insert (deduped). Returns rows newly stored."""
    with db.connect() as conn:
        corridors = conn.execute("SELECT slug, keywords FROM corridors").fetchall()
        new = 0
        for it in items:
            text = f"{it['title']} {it.get('body', '')}"
            cats = classify(text)
            if not cats:
                continue                      # irrelevant to development signals
            slugs = match_corridors(text, corridors)
            cur = conn.execute(
                "INSERT OR IGNORE INTO events (fetched_at, source, region, url, "
                "title, body, categories, corridors) VALUES (?,?,?,?,?,?,?,?)",
                (_now(), source, region, it.get("url", ""), it["title"],
                 it.get("body", ""), ",".join(cats), ",".join(slugs)))
            new += cur.rowcount
        return new


def sweep(sources: list[dict] | None = None) -> dict:
    """Fetch every configured source. Returns {source: new_events | 'error: ...'}."""
    results: dict[str, object] = {}
    for src in sources or config.SOURCES:
        try:
            resp = requests.get(src["url"], headers=config.HEADERS,
                                timeout=config.REQUEST_TIMEOUT)
            resp.raise_for_status()
            if src["kind"] == "rss":
                items = parse_rss(resp.text)
            else:
                base = "/".join(src["url"].split("/")[:3])
                items = parse_listing(resp.text, src.get("selector", "a"), base)
            results[src["name"]] = store_items(items, src["name"], src["region"])
        except Exception as e:                     # dead source ≠ dead sweep
            results[src["name"]] = f"error: {type(e).__name__}: {e}"
        time.sleep(config.THROTTLE_SECONDS)
    return results


def recent_events(days: int = 30, corridor: str | None = None) -> list[dict]:
    q = ("SELECT fetched_at, source, title, categories, corridors, url FROM events "
         "WHERE fetched_at >= datetime('now', ?)")
    params: list = [f"-{days} days"]
    if corridor:
        q += " AND corridors LIKE ?"
        params.append(f"%{corridor}%")
    q += " ORDER BY fetched_at DESC"
    with db.connect() as conn:
        rows = conn.execute(q, params).fetchall()
    keys = ["fetched_at", "source", "title", "categories", "corridors", "url"]
    return [dict(zip(keys, r)) for r in rows]
