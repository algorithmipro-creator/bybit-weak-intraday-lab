"""Archive scanner wrapper for causal/live-scan-safe signals."""
from __future__ import annotations

import datetime as dt
from dataclasses import asdict
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from .archive import date_range, download_archive_file, get_archive_universe, http_session, load_archive_ticks, parse_date
from .causal import CausalSignal, find_causal_signals
from .core import StrategyConfig, first_barrier, normalize_ticks

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

CAUSAL_EVALUATION_COLUMNS = [
    *CAUSAL_SIGNAL_COLUMNS,
    "entry_time_utc",
    "entry_price",
    "tp_pct",
    "sl_pct",
    "mfe_after_entry_pct",
    "mae_after_entry_pct",
    "outcome",
    "exit_time_utc",
    "exit_price",
    "pnl_underlying_pct",
    "minutes_to_exit",
]


def signals_to_frame(signals: Iterable[CausalSignal]) -> pd.DataFrame:
    rows = [asdict(signal) for signal in signals]
    return pd.DataFrame(rows, columns=CAUSAL_SIGNAL_COLUMNS)


def evaluations_to_frame(rows: Iterable[dict]) -> pd.DataFrame:
    return pd.DataFrame(list(rows), columns=CAUSAL_EVALUATION_COLUMNS)


def evaluate_causal_signal(signal: CausalSignal, cur_ticks_raw: pd.DataFrame, cfg: StrategyConfig) -> dict:
    """Evaluate future path after a causal signal has already been emitted."""
    cur_ticks = normalize_ticks(cur_ticks_raw)
    signal_ns = int(pd.Timestamp(signal.signal_time_utc).value)
    mask = cur_ticks["ts_ns"].to_numpy("int64") > signal_ns
    prices = cur_ticks.loc[mask, "price"].to_numpy(float)
    ns = cur_ticks.loc[mask, "ts_ns"].to_numpy("int64")
    tp = cfg.tp_pump if signal.mode == "pump" else cfg.tp_weak
    sl = cfg.sl_pump if signal.mode == "pump" else cfg.sl_weak
    mfe = max(0.0, (signal.signal_price - np.min(prices)) / signal.signal_price * 100) if prices.size else np.nan
    mae = max(0.0, (np.max(prices) - signal.signal_price) / signal.signal_price * 100) if prices.size else np.nan

    return {
        **asdict(signal),
        "entry_time_utc": signal.signal_time_utc,
        "entry_price": signal.signal_price,
        "tp_pct": tp * 100,
        "sl_pct": sl * 100,
        "mfe_after_entry_pct": float(mfe) if not pd.isna(mfe) else np.nan,
        "mae_after_entry_pct": float(mae) if not pd.isna(mae) else np.nan,
        **first_barrier(prices, ns, signal.signal_price, signal_ns, tp, sl, cfg.max_hold_min),
    }


def evaluate_causal_signals(signals: Iterable[CausalSignal], cur_ticks_raw: pd.DataFrame, cfg: StrategyConfig) -> pd.DataFrame:
    return evaluations_to_frame(evaluate_causal_signal(signal, cur_ticks_raw, cfg) for signal in signals)


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
    signals, _ = run_archive_causal_scan_outputs(
        start=start,
        end=end,
        symbols=symbols,
        full_universe=full_universe,
        include_majors=include_majors,
        max_symbols=max_symbols,
        cache_dir=cache_dir,
        cfg=cfg,
        sleep=sleep,
    )
    return signals


def run_archive_causal_scan_outputs(
    start: str | dt.date,
    end: str | dt.date,
    symbols: Iterable[str] | None = None,
    full_universe: bool = False,
    include_majors: bool = False,
    max_symbols: int = 0,
    cache_dir: str | Path = "./bybit_archive_cache",
    cfg: StrategyConfig | None = None,
    sleep: float = 0.15,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Run causal detection and post-signal evaluation in one archive pass."""
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
    evaluation_frames: list[pd.DataFrame] = []
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
                day_signals = find_causal_signals(sym, str(day), cur_ticks, prev_ticks, cfg)
                signals.extend(day_signals)
                if day_signals:
                    evaluation_frames.append(evaluate_causal_signals(day_signals, cur_ticks, cfg))
            except Exception as exc:
                error_rows.append({"date": str(day), "symbol": sym, "error": str(exc)})

    out = signals_to_frame(signals)
    if error_rows:
        errors = pd.DataFrame(error_rows)
        out = pd.concat([out, errors], ignore_index=True, sort=False)
    if not out.empty and "signal_time_utc" in out.columns:
        out = out.sort_values(["date", "signal_time_utc", "score"], ascending=[True, True, False], na_position="last")
    evaluations = (
        pd.concat(evaluation_frames, ignore_index=True, sort=False)
        if evaluation_frames
        else evaluations_to_frame([])
    )
    if not evaluations.empty and "signal_time_utc" in evaluations.columns:
        evaluations = evaluations.sort_values(["date", "signal_time_utc", "score"], ascending=[True, True, False], na_position="last")
    return out.reset_index(drop=True), evaluations.reset_index(drop=True)
