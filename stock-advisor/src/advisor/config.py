"""Central configuration: paths, URLs, tunables."""
from __future__ import annotations

import os
from pathlib import Path

# Data lives outside the source tree; override with ADVISOR_DATA_DIR.
DATA_DIR = Path(os.environ.get("ADVISOR_DATA_DIR", Path.home() / ".advisor-data"))
DB_PATH = DATA_DIR / "advisor.db"
BHAVCOPY_CACHE_DIR = DATA_DIR / "bhavcopy"

# NSE index constituent lists (public CSVs).
NIFTY500_URL = "https://nsearchives.nseindia.com/content/indices/ind_nifty500list.csv"

# New-format NSE CM bhavcopy, {date} = YYYYMMDD.
BHAVCOPY_URL = (
    "https://nsearchives.nseindia.com/content/cm/"
    "BhavCopy_NSE_CM_0_0_0_{date}_F_0000.csv.zip"
)

# NSE blocks default requests UAs; a browser UA + polite throttling is required.
NSE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
}
REQUEST_TIMEOUT = 30
THROTTLE_SECONDS = 1.0  # minimum gap between NSE requests

# yfinance uses .NS suffix for NSE symbols.
YF_SUFFIX = ".NS"
PRICE_HISTORY_YEARS = 10


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    BHAVCOPY_CACHE_DIR.mkdir(parents=True, exist_ok=True)
