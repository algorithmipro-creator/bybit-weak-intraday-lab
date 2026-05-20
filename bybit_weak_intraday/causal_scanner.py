"""Archive scanner wrapper for causal/live-scan-safe signals."""
from __future__ import annotations

import datetime as dt
from dataclasses import asdict
from pathlib import Path
from typing import Iterable

import pandas as pd

from .archive import date_range, download_archive_file, get_archive_universe, http_session, load_archive_ticks, parse_date
from .causal import CausalSignal, find_causal_signals
from .core import StrategyConfig

CAUSAL_SIGNAL_COLUMNS = [
    "date",
    "symbol",
    "mode",
    "signal_time_utc",
    "signal_price",
    "score",
    "weak_score",
    "pump_score",
    "turnover_so_far_usdt",
    "prev_turnover_usdt",
    "turnover_ratio_so_far",
    "runup_so_far_pct",
    "peak_time_utc",
    "vwap_at_signal",
    "sell_share_peak_to_signal_pct",
]


def signals_to_frame(signals: Iterable[CausalSignal]) -> pd.DataFrame:
    rows = [asdict(signal) for signal in signals]
    return pd.DataFrame(rows, columns=CAUSAL_SIGNAL_COLUMNS)


def run_archive_causal_scan(
    start: str | dt.date,
    end: str | dt.date,
    symbols: Iterable[str] | None = None,
    full_universe: bool = False,
    include_majors: bool = False,
    max_symbols: int = 0,
    cache_dir: str | Path = "./bybit_archive_cache",
    cfg: StrategyConfig | None = None,
    sleep: float = 0.15,
) -> pd.DataFrame:
    """Run causal signal detection over Bybit public archive files."""
    cfg = cfg or StrategyConfig()
    start_date = parse_date(start) if isinstance(start, str) else start
    end_date = parse_date(end) if isinstance(end, str) else end
    days = date_range(start_date, end_date)
    sess = http_session()
    cache = Path(cache_dir)

    if full_universe:
        symbol_list = get_archive_universe(sess, exclude_majors=not include_majors)
    else:
        symbol_list = [s.strip().upper() for s in (symbols or []) if s.strip()]

    if max_symbols and len(symbol_list) > max_symbols:
        symbol_list = symbol_list[:max_symbols]

    signals: list[CausalSignal] = []
    error_rows: list[dict] = []
    for sym in symbol_list:
        for day in days:
            prev = day - dt.timedelta(days=1)
            cur_path = download_archive_file(sess, sym, day, cache, sleep=sleep)
            prev_path = download_archive_file(sess, sym, prev, cache, sleep=sleep)
            if cur_path is None or prev_path is None:
                continue
            try:
                cur_ticks = load_archive_ticks(cur_path)
                prev_ticks = load_archive_ticks(prev_path)
                signals.extend(find_causal_signals(sym, str(day), cur_ticks, prev_ticks, cfg))
            except Exception as exc:
                error_rows.append({"date": str(day), "symbol": sym, "error": str(exc)})

    out = signals_to_frame(signals)
    if error_rows:
        errors = pd.DataFrame(error_rows)
        out = pd.concat([out, errors], ignore_index=True, sort=False)
    if not out.empty and "signal_time_utc" in out.columns:
        out = out.sort_values(["date", "signal_time_utc", "score"], ascending=[True, True, False], na_position="last")
    return out.reset_index(drop=True)
