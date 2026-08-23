"""Configuration: paths, monitored sources (all public), scraper politeness."""
from __future__ import annotations

import os
from pathlib import Path

DATA_DIR = Path(os.environ.get("REIA_DATA_DIR", Path.home() / ".reia-data"))
DB_PATH = DATA_DIR / "reia.db"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "en-IN,en;q=0.9",
}
REQUEST_TIMEOUT = 30
THROTTLE_SECONDS = 2.0   # government sites: be extra polite

# Public sources the monitor sweeps. kind: 'rss' | 'html'
# selector: CSS selector for item links on HTML listing pages (BeautifulSoup).
# These are starting points — expect to tune selectors after the first live run;
# government sites change markup without notice (the monitor logs parse failures
# instead of crashing).
SOURCES: list[dict] = [
    {"name": "pib_all", "kind": "rss", "region": "central",
     "url": "https://www.pib.gov.in/RssMain.aspx?ModId=6&Lang=1&Regid=3"},
    {"name": "nhai_whatsnew", "kind": "html", "region": "central",
     "url": "https://nhai.gov.in/#/whats-new", "selector": "a"},
    {"name": "ap_cabinet_news", "kind": "html", "region": "AP",
     "url": "https://www.ap.gov.in/latest-updates/", "selector": "a"},
    {"name": "tg_news", "kind": "html", "region": "TG",
     "url": "https://www.telangana.gov.in/news/", "selector": "a"},
    # Add district gazette / HMDA / CRDA / APIIC / TGIIC pages as they're verified.
]

# Keyword taxonomy for rule-based event classification (fast path; AI refines).
EVENT_KEYWORDS: dict[str, list[str]] = {
    "highway_road": ["highway", "expressway", "ring road", "nhai", "bypass",
                     "corridor road", "orr", "rrr", "four-lane", "six-lane"],
    "rail_metro": ["railway line", "metro", "rrts", "rail corridor", "new line",
                   "doubling", "railway station", "mmts"],
    "airport_port": ["airport", "greenfield airport", "aerodrome", "port",
                     "harbour", "bhogapuram"],
    "industrial": ["industrial park", "industrial corridor", "sez", "pharma city",
                   "textile park", "pm mitra", "nimz", "manufacturing cluster",
                   "apiic", "tgiic", "allotment of land"],
    "urban_planning": ["master plan", "land pooling", "layout approval", "hmda",
                       "crda", "dtcp", "municipal corporation", "urban development",
                       "capital city", "amaravati", "new city", "township"],
    "irrigation_power": ["irrigation", "reservoir", "lift irrigation", "power plant",
                         "solar park", "transmission"],
    "acquisition": ["land acquisition", "notification under", "award enquiry",
                    "section 11", "section 19", "compensation"],
    "policy": ["it policy", "industrial policy", "incentive", "cabinet approved",
               "foundation stone", "inaugurat", "tender", "dpr approved",
               "budget allocation"],
}

# Corridors we track. Seeded with AP/TG watch-map (knowledge 01); extend via CLI.
SEED_CORRIDORS: list[dict] = [
    {"slug": "amaravati", "name": "Amaravati capital region", "state": "AP",
     "keywords": ["amaravati", "crda", "capital city", "mangalagiri", "thullur"]},
    {"slug": "vizag-bhogapuram", "name": "Visakhapatnam–Bhogapuram", "state": "AP",
     "keywords": ["visakhapatnam", "vizag", "bhogapuram", "anandapuram"]},
    {"slug": "hyd-rrr-north", "name": "Hyderabad RRR (north arc)", "state": "TG",
     "keywords": ["regional ring road", "rrr", "sangareddy", "toopran",
                  "gajwel", "choutuppal"]},
    {"slug": "hyd-pharma-south", "name": "Hyderabad south (pharma/industrial)",
     "state": "TG", "keywords": ["pharma city", "mucherla", "yacharam",
                                 "kandukur", "srisailam highway"]},
    {"slug": "bengaluru-hyd", "name": "Hyderabad–Bengaluru industrial corridor",
     "state": "AP", "keywords": ["orvakal", "kurnool", "industrial corridor node"]},
]


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
