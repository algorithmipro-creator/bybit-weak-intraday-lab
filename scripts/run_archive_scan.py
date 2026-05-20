#!/usr/bin/env python3
"""CLI wrapper for tick-level Bybit archive scans."""
from __future__ import annotations

import argparse
from pathlib import Path

from bybit_weak_intraday.core import StrategyConfig
from bybit_weak_intraday.scanner import run_archive_scan


def parse_symbols(value: str) -> list[str]:
    return [x.strip().upper() for x in value.split(",") if x.strip()]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--symbols", default="")
    ap.add_argument("--symbol-file", default="")
    ap.add_argument("--full-universe", action="store_true")
    ap.add_argument("--include-majors", action="store_true")
    ap.add_argument("--max-symbols", type=int, default=0)
    ap.add_argument("--cache-dir", default="./bybit_archive_cache")
    ap.add_argument("--out-metrics", default="bybit_metrics.csv")
    ap.add_argument("--out-trades", default="bybit_trades.csv")
    ap.add_argument("--min-turnover", type=float, default=1_000_000)
    ap.add_argument("--weak-threshold", type=int, default=9)
    ap.add_argument("--pump-threshold", type=int, default=9)
    ap.add_argument("--tp-weak", type=float, default=0.06)
    ap.add_argument("--sl-weak", type=float, default=0.07)
    ap.add_argument("--tp-pump", type=float, default=0.08)
    ap.add_argument("--sl-pump", type=float, default=0.07)
    ap.add_argument("--max-hold-min", type=float, default=720)
    ap.add_argument("--sleep", type=float, default=0.15)
    args = ap.parse_args()

    symbols = parse_symbols(args.symbols)
    if args.symbol_file:
        symbols.extend([x.strip().upper() for x in Path(args.symbol_file).read_text().splitlines() if x.strip()])

    cfg = StrategyConfig(
        min_turnover=args.min_turnover,
        weak_threshold=args.weak_threshold,
        pump_threshold=args.pump_threshold,
        tp_weak=args.tp_weak,
        sl_weak=args.sl_weak,
        tp_pump=args.tp_pump,
        sl_pump=args.sl_pump,
        max_hold_min=args.max_hold_min,
    )
    metrics, trades = run_archive_scan(
        start=args.start,
        end=args.end,
        symbols=symbols,
        full_universe=args.full_universe,
        include_majors=args.include_majors,
        max_symbols=args.max_symbols,
        cache_dir=args.cache_dir,
        cfg=cfg,
        sleep=args.sleep,
    )
    metrics.to_csv(args.out_metrics, index=False)
    trades.to_csv(args.out_trades, index=False)
    print(f"metrics rows: {len(metrics)} -> {args.out_metrics}")
    print(f"trade rows: {len(trades)} -> {args.out_trades}")
    if not trades.empty:
        cols = [
            "date", "symbol", "mode", "turnover_usdt", "weak_score", "pump_score",
            "entry_time_utc", "tp_pct", "sl_pct", "outcome", "pnl_underlying_pct",
            "minutes_to_exit", "mfe_after_entry_pct", "mae_after_entry_pct",
        ]
        print(trades[[c for c in cols if c in trades.columns]].head(50).to_string(index=False))


if __name__ == "__main__":
    main()
