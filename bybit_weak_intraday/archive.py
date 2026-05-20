"""Helpers for downloading Bybit public trade archives."""
from __future__ import annotations

import datetime as dt
import re
import time
from pathlib import Path
from typing import Iterable

import pandas as pd
import requests

BASE_ARCHIVE = "https://public.bybit.com/trading/"
MAJORS = {
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT", "DOGEUSDT", "ADAUSDT", "AVAXUSDT",
    "LINKUSDT", "TRXUSDT", "TONUSDT", "DOTUSDT", "LTCUSDT", "BCHUSDT", "POLUSDT", "MATICUSDT",
    "ETCUSDT", "UNIUSDT", "NEARUSDT", "APTUSDT", "ARBUSDT", "OPUSDT", "FILUSDT", "ATOMUSDT",
}


def parse_date(s: str) -> dt.date:
    return dt.datetime.strptime(s, "%Y-%m-%d").date()


def date_range(start: dt.date, end: dt.date) -> list[dt.date]:
    cur = start
    out: list[dt.date] = []
    while cur <= end:
        out.append(cur)
        cur += dt.timedelta(days=1)
    return out


def http_session(user_agent: str = "bybit-weak-intraday-lab/1.0") -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": user_agent})
    return s


def archive_url(symbol: str, day: dt.date) -> str:
    return f"{BASE_ARCHIVE}{symbol.upper()}/{symbol.upper()}{day:%Y-%m-%d}.csv.gz"


def cache_path(cache_dir: Path, symbol: str, day: dt.date) -> Path:
    return cache_dir / symbol.upper() / f"{symbol.upper()}{day:%Y-%m-%d}.csv.gz"


def get_archive_universe(sess: requests.Session, exclude_majors: bool = True) -> list[str]:
    """List USDT symbols visible in Bybit public /trading/ archive."""
    r = sess.get(BASE_ARCHIVE, timeout=30)
    r.raise_for_status()
    syms: list[str] = []
    for m in re.finditer(r'href="([^"]+/)"', r.text):
        sym = m.group(1).strip("/").upper()
        if not sym.endswith("USDT"):
            continue
        if "-" in sym or sym.endswith("PERP"):
            continue
        if exclude_majors and sym in MAJORS:
            continue
        syms.append(sym)
    return sorted(set(syms))


def download_archive_file(
    sess: requests.Session,
    symbol: str,
    day: dt.date,
    cache_dir: Path,
    retries: int = 3,
    sleep: float = 0.15,
) -> Path | None:
    """Download one Bybit public archive file into cache; return path or None."""
    out = cache_path(cache_dir, symbol, day)
    if out.exists() and out.stat().st_size > 0:
        return out
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".tmp")
    url = archive_url(symbol, day)
    for attempt in range(retries):
        try:
            r = sess.get(url, stream=True, timeout=60)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            with open(tmp, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        f.write(chunk)
            tmp.replace(out)
            time.sleep(sleep)
            return out
        except Exception:
            tmp.unlink(missing_ok=True)
            if attempt == retries - 1:
                return None
            time.sleep(1 + attempt)
    return None


def load_archive_ticks(path: Path) -> pd.DataFrame:
    usecols = ["timestamp", "symbol", "side", "size", "price", "foreignNotional"]
    return pd.read_csv(path, usecols=lambda c: c in usecols)
