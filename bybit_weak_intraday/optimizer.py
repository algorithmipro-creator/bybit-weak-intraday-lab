"""Offline TP/SL grid optimizer built on the archive scanner."""
from __future__ import annotations

import datetime as dt
from dataclasses import replace
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from .archive import date_range, get_archive_universe, http_session, parse_date
from .core import StrategyConfig
from .progress import ProgressCallback
from .scanner import run_archive_scan

GRID_SUMMARY_COLUMNS = [
    "tp_pct",
    "sl_pct",
    "trades",
    "tp_hits",
    "sl_hits",
    "time_or_eod_exits",
    "avg_underlying_pnl",
    "median_underlying_pnl",
    "avg_minutes_to_exit",
    "tp_rate",
    "sl_rate",
]


def _pct(value: float) -> float:
    return round(float(value) * 100, 10)


def summarize_grid_trades(trades: pd.DataFrame) -> pd.DataFrame:
    """Aggregate per-trade grid results by TP/SL pair."""
    if trades.empty:
        return pd.DataFrame(columns=GRID_SUMMARY_COLUMNS)

    rows: list[dict] = []
    for (tp_pct, sl_pct), group in trades.groupby(["tp_pct", "sl_pct"], dropna=False):
        outcomes = group["outcome"].astype(str)
        count = int(len(group))
        tp_hits = int((outcomes == "tp").sum())
        sl_hits = int((outcomes == "sl").sum())
        rows.append(
            {
                "tp_pct": float(tp_pct),
                "sl_pct": float(sl_pct),
                "trades": count,
                "tp_hits": tp_hits,
                "sl_hits": sl_hits,
                "time_or_eod_exits": int(count - tp_hits - sl_hits),
                "avg_underlying_pnl": float(group["pnl_underlying_pct"].mean()),
                "median_underlying_pnl": float(group["pnl_underlying_pct"].median()),
                "avg_minutes_to_exit": float(group["minutes_to_exit"].mean()),
                "tp_rate": float(tp_hits / count) if count else np.nan,
                "sl_rate": float(sl_hits / count) if count else np.nan,
            }
        )

    return pd.DataFrame(rows, columns=GRID_SUMMARY_COLUMNS).sort_values(
        ["avg_underlying_pnl", "tp_rate", "tp_pct", "sl_pct"],
        ascending=[False, False, True, True],
    )


def _empty_summary_for_grid(tp_grid: Iterable[float], sl_grid: Iterable[float]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "tp_pct": _pct(tp),
                "sl_pct": _pct(sl),
                "trades": 0,
                "tp_hits": 0,
                "sl_hits": 0,
                "time_or_eod_exits": 0,
                "avg_underlying_pnl": np.nan,
                "median_underlying_pnl": np.nan,
                "avg_minutes_to_exit": np.nan,
                "tp_rate": np.nan,
                "sl_rate": np.nan,
            }
            for tp in tp_grid
            for sl in sl_grid
        ],
        columns=GRID_SUMMARY_COLUMNS,
    )


def run_archive_tp_sl_grid(
    start: str | dt.date,
    end: str | dt.date,
    symbols: Iterable[str] | None = None,
    full_universe: bool = False,
    include_majors: bool = False,
    max_symbols: int = 0,
    cache_dir: str | Path = "./bybit_archive_cache",
    cfg: StrategyConfig | None = None,
    tp_grid: Iterable[float] = (0.04, 0.06, 0.08),
    sl_grid: Iterable[float] = (0.05, 0.07),
    sleep: float = 0.15,
    progress_callback: ProgressCallback | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Run archive scans for each TP/SL pair and aggregate trade outcomes."""
    base_cfg = cfg or StrategyConfig()
    tp_values = [float(tp) for tp in tp_grid]
    sl_values = [float(sl) for sl in sl_grid]
    start_date = parse_date(start) if isinstance(start, str) else start
    end_date = parse_date(end) if isinstance(end, str) else end
    days = date_range(start_date, end_date)
    if full_universe:
        symbol_list = get_archive_universe(http_session(), exclude_majors=not include_majors)
    else:
        symbol_list = [s.strip().upper() for s in (symbols or []) if s.strip()]
    if max_symbols and len(symbol_list) > max_symbols:
        symbol_list = symbol_list[:max_symbols]

    combo_total = len(tp_values) * len(sl_values)
    scan_total = len(symbol_list) * len(days)
    optimizer_total = combo_total * scan_total
    completed_before_combo = 0
    combo_number = 0
    trade_frames: list[pd.DataFrame] = []

    for tp in tp_values:
        for sl in sl_values:
            combo_number += 1

            def _combo_progress(
                event: dict,
                *,
                combo_number: int = combo_number,
                tp: float = tp,
                sl: float = sl,
                completed_before_combo: int = completed_before_combo,
            ) -> None:
                if progress_callback is None:
                    return
                translated = event.copy()
                translated["processed"] = completed_before_combo + int(event.get("processed") or 0)
                translated["total"] = optimizer_total
                translated["grid_combo"] = f"{combo_number}/{combo_total}"
                translated["tp_pct"] = _pct(tp)
                translated["sl_pct"] = _pct(sl)
                translated["message"] = (
                    f"optimizing TP {_pct(tp):.2f}% / SL {_pct(sl):.2f}%: "
                    f"{event.get('current_symbol') or ''} {event.get('current_date') or ''}"
                ).strip()
                try:
                    progress_callback(translated)
                except Exception:
                    return

            combo_cfg = replace(base_cfg, tp_weak=tp, tp_pump=tp, sl_weak=sl, sl_pump=sl)
            _, trades = run_archive_scan(
                start=start,
                end=end,
                symbols=symbol_list,
                full_universe=False,
                include_majors=False,
                max_symbols=0,
                cache_dir=cache_dir,
                cfg=combo_cfg,
                sleep=sleep,
                progress_callback=_combo_progress,
            )
            completed_before_combo += scan_total
            if trades.empty:
                continue
            trades = trades.copy()
            trades["tp_pct"] = _pct(tp)
            trades["sl_pct"] = _pct(sl)
            trade_frames.append(trades)

    if not trade_frames:
        return _empty_summary_for_grid(tp_values, sl_values), pd.DataFrame()

    all_trades = pd.concat(trade_frames, ignore_index=True)
    summary = summarize_grid_trades(all_trades)
    return summary, all_trades
