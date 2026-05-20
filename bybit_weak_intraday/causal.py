"""Causal/live-scan-safe signal helpers.

This module is for signal generation that must not inspect current-day future
ticks when deciding whether a signal exists. Post-signal evaluation belongs in a
separate step after a signal has already been emitted.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .core import StrategyConfig, make_bars, normalize_ticks, path_max_short


@dataclass(frozen=True)
class CausalSignal:
    date: str
    symbol: str
    mode: str
    signal_time_utc: str
    signal_price: float
    score: int
    weak_score: int
    pump_score: int
    turnover_so_far_usdt: float
    prev_turnover_usdt: float
    turnover_ratio_so_far: float
    runup_so_far_pct: float
    peak_time_utc: str
    vwap_at_signal: float
    sell_share_peak_to_signal_pct: float


def truncate_ticks_at(ticks: pd.DataFrame, signal_ns: int) -> pd.DataFrame:
    """Return only rows known at signal_ns."""
    return ticks.loc[ticks["ts_ns"] <= signal_ns].copy().reset_index(drop=True)


def sell_share_between(ticks: pd.DataFrame, start_ns: int, end_ns: int) -> float:
    """Quote-volume sell share for start_ns <= ts_ns <= end_ns."""
    window = ticks[(ticks["ts_ns"] >= start_ns) & (ticks["ts_ns"] <= end_ns)]
    if window.empty:
        return float("nan")
    total = float(window["quote"].sum())
    if total == 0:
        return float("nan")
    sell = float(window.loc[window["side"].str.lower() == "sell", "quote"].sum())
    return sell / total * 100


def _previous_day_metrics(prev_ticks_raw: pd.DataFrame, interval: str) -> dict[str, float]:
    prev_ticks = normalize_ticks(prev_ticks_raw)
    prev_bars = make_bars(prev_ticks, interval)
    prev_turnover = float(prev_ticks["quote"].sum())
    prev_ret = (float(prev_ticks["price"].iloc[-1]) / float(prev_ticks["price"].iloc[0]) - 1) * 100
    prev_short, _, _ = path_max_short(prev_bars)
    return {
        "prev_turnover_usdt": prev_turnover,
        "prev_day_ret_pct": prev_ret,
        "prev_day_max_dd_pct": -prev_short * 100,
    }


def _runup_so_far(bars_so_far: pd.DataFrame) -> tuple[float, int, int]:
    lows = bars_so_far["low"].to_numpy(float)
    highs = bars_so_far["high"].to_numpy(float)
    running_low = np.minimum.accumulate(lows)
    runups = highs / running_low - 1
    peak_idx = int(np.nanargmax(runups))
    trough_idx = int(np.nanargmin(lows[: peak_idx + 1]))
    return float(runups[peak_idx]), trough_idx, peak_idx


def _first_vwap_loss_indices(bars: pd.DataFrame) -> set[int]:
    out: set[int] = set()
    seen_peak = False
    running_high = -np.inf
    for i, row in bars.iterrows():
        high = float(row["high"])
        if high > running_high:
            running_high = high
            seen_peak = True
            continue
        if seen_peak and float(row["close"]) < float(row["vwap"]):
            out.add(int(i))
            seen_peak = False
    return out


def _timestamp_to_tick_units(ts: pd.Timestamp, ticks: pd.DataFrame) -> int:
    """Convert a Timestamp to the same integer time unit as normalized ticks."""
    ns = int(pd.Timestamp(ts).value)
    sample = int(ticks["ts_ns"].dropna().iloc[0])
    candidates = [ns, ns // 1_000, ns // 1_000_000, ns // 1_000_000_000]
    return min(candidates, key=lambda value: abs(value - sample))


def find_causal_signals(
    symbol: str,
    day: str,
    cur_ticks_raw: pd.DataFrame,
    prev_ticks_raw: pd.DataFrame,
    cfg: StrategyConfig,
) -> list[CausalSignal]:
    """Find causal weak signals without reading future ticks for decisions."""
    cur_ticks = normalize_ticks(cur_ticks_raw)
    if cur_ticks.empty:
        return []

    prev = _previous_day_metrics(prev_ticks_raw, cfg.bar_interval)
    if prev["prev_turnover_usdt"] == 0:
        return []

    bars = make_bars(cur_ticks, cfg.bar_interval)
    if bars.empty:
        return []

    signals: list[CausalSignal] = []
    emitted_modes: set[str] = set()
    vwap_loss_indices = _first_vwap_loss_indices(bars)

    for i, row in bars.iterrows():
        if int(i) not in vwap_loss_indices:
            continue

        signal_ns = _timestamp_to_tick_units(row["dt"], cur_ticks)
        ticks_so_far = truncate_ticks_at(cur_ticks, signal_ns)
        bars_so_far = bars.iloc[: int(i) + 1].copy()
        turnover_so_far = float(ticks_so_far["quote"].sum())
        turnover_ratio = turnover_so_far / prev["prev_turnover_usdt"]
        runup, _, run_peak = _runup_so_far(bars_so_far)
        peak_idx = int(np.nanargmax(bars_so_far["high"].to_numpy(float)))
        peak_time = bars_so_far.iloc[peak_idx]["dt"]
        peak_hour = peak_time.hour + peak_time.minute / 60
        peak_ts = _timestamp_to_tick_units(peak_time, cur_ticks)
        sell_share = sell_share_between(cur_ticks, peak_ts, signal_ns)

        weak_score = 0
        if prev["prev_day_ret_pct"] <= -4:
            weak_score += 2
        if prev["prev_day_max_dd_pct"] <= -9:
            weak_score += 2
        if turnover_ratio <= 0.8:
            weak_score += 2
        if 3 <= runup * 100 <= 12:
            weak_score += 1
        if peak_hour <= 11:
            weak_score += 1
        weak_score += 2
        if sell_share >= 52:
            weak_score += 1

        pump_score = 0
        if turnover_ratio >= 8:
            pump_score += 2
        if turnover_ratio >= 15:
            pump_score += 1
        if runup * 100 >= 25:
            pump_score += 2
        pump_peak_time = bars_so_far.iloc[run_peak]["dt"]
        pump_peak_hour = pump_peak_time.hour + pump_peak_time.minute / 60
        if 7 <= pump_peak_hour <= 11.5:
            pump_score += 1
        pump_score += 2
        low = float(bars_so_far.iloc[0 : run_peak + 1]["low"].min())
        high = float(bars_so_far.iloc[run_peak]["high"])
        midpoint = low + 0.5 * (high - low)
        if float(row["close"]) < midpoint:
            pump_score += 1
        pump_peak_ts = _timestamp_to_tick_units(pump_peak_time, cur_ticks)
        pump_sell_share = sell_share_between(cur_ticks, pump_peak_ts, signal_ns)
        if pump_sell_share >= 52:
            pump_score += 1

        if (
            "weak" not in emitted_modes
            and turnover_so_far >= cfg.min_turnover
            and weak_score >= cfg.weak_threshold
        ):
            signals.append(
                CausalSignal(
                    date=str(day),
                    symbol=symbol,
                    mode="weak",
                    signal_time_utc=row["dt"].isoformat(),
                    signal_price=float(row["close"]),
                    score=weak_score,
                    weak_score=weak_score,
                    pump_score=pump_score,
                    turnover_so_far_usdt=turnover_so_far,
                    prev_turnover_usdt=prev["prev_turnover_usdt"],
                    turnover_ratio_so_far=turnover_ratio,
                    runup_so_far_pct=runup * 100,
                    peak_time_utc=peak_time.isoformat(),
                    vwap_at_signal=float(row["vwap"]),
                    sell_share_peak_to_signal_pct=sell_share,
                )
            )
            emitted_modes.add("weak")

        if (
            "pump" not in emitted_modes
            and turnover_so_far >= cfg.min_turnover
            and pump_score >= cfg.pump_threshold
        ):
            signals.append(
                CausalSignal(
                    date=str(day),
                    symbol=symbol,
                    mode="pump",
                    signal_time_utc=row["dt"].isoformat(),
                    signal_price=float(row["close"]),
                    score=pump_score,
                    weak_score=weak_score,
                    pump_score=pump_score,
                    turnover_so_far_usdt=turnover_so_far,
                    prev_turnover_usdt=prev["prev_turnover_usdt"],
                    turnover_ratio_so_far=turnover_ratio,
                    runup_so_far_pct=runup * 100,
                    peak_time_utc=pump_peak_time.isoformat(),
                    vwap_at_signal=float(row["vwap"]),
                    sell_share_peak_to_signal_pct=pump_sell_share,
                )
            )
            emitted_modes.add("pump")

    return signals
