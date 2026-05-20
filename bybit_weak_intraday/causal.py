"""Causal/live-scan-safe signal helpers.

This module is for signal generation that must not inspect current-day future
ticks when deciding whether a signal exists. Post-signal evaluation belongs in a
separate step after a signal has already been emitted.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


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
