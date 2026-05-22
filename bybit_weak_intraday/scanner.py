"""Archive scanner that applies core strategy scoring across symbols/days."""
from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Iterable

import pandas as pd

from .archive import date_range, download_archive_file_result, get_archive_universe, http_session, load_archive_ticks, parse_date
from .core import StrategyConfig, score_symbol_day
from .progress import ProgressCallback, ProgressState


def run_archive_scan(
    start: str | dt.date,
    end: str | dt.date,
    symbols: Iterable[str] | None = None,
    full_universe: bool = False,
    include_majors: bool = False,
    max_symbols: int = 0,
    cache_dir: str | Path = "./bybit_archive_cache",
    cfg: StrategyConfig | None = None,
    sleep: float = 0.15,
    progress_callback: ProgressCallback | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Run a tick-level archive scan and return metrics/trades dataframes."""
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

    progress = ProgressState(total=len(symbol_list) * len(days))
    metrics: list[dict] = []
    trades: list[dict] = []
    for sym in symbol_list:
        for day in days:
            prev = day - dt.timedelta(days=1)
            cur_result = download_archive_file_result(sess, sym, day, cache, sleep=sleep)
            prev_result = download_archive_file_result(sess, sym, prev, cache, sleep=sleep)
            for result in (cur_result, prev_result):
                progress.add_archive_result(result)
            warnings = progress.warnings_for_results(sym, str(day), [cur_result, prev_result])
            if cur_result.path is None or prev_result.path is None:
                event = progress.advance(sym, str(day))
                if warnings:
                    event["warnings"] = warnings
                if progress_callback:
                    progress_callback(event)
                continue
            try:
                cur_ticks = load_archive_ticks(cur_result.path)
                prev_ticks = load_archive_ticks(prev_result.path)
                m, t = score_symbol_day(sym, str(day), cur_ticks, prev_ticks, cfg)
                if m:
                    metrics.append(m)
                if t and m:
                    trades.append({**m, **t})
                event = progress.advance(sym, str(day))
                if warnings:
                    event["warnings"] = warnings
                if progress_callback:
                    progress_callback(event)
            except Exception as exc:
                metrics.append({"date": str(day), "symbol": sym, "error": str(exc)})
                progress.errors += 1
                warnings.append({"symbol": sym, "date": str(day), "message": str(exc)})
                event = progress.advance(sym, str(day))
                event["warnings"] = warnings
                if progress_callback:
                    progress_callback(event)

    dfm = pd.DataFrame(metrics)
    dft = pd.DataFrame(trades)
    if not dfm.empty and "candidate_score" in dfm.columns:
        dfm = dfm.sort_values(["date", "candidate_score", "turnover_usdt"], ascending=[True, False, False])
    if not dft.empty and "candidate_score" in dft.columns:
        dft = dft.sort_values(["date", "candidate_score", "turnover_usdt"], ascending=[True, False, False])
    return dfm, dft
