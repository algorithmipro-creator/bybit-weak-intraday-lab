"""Core research logic for Bybit weak intraday short strategies.

This module is deliberately exchange-execution agnostic. It only scores public
market data and simulates hypothetical short entries/exits. It does not place
orders and should not be modified into a live trading engine without a separate
risk review.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class StrategyConfig:
    min_turnover: float = 1_000_000.0
    weak_threshold: int = 9
    pump_threshold: int = 9
    tp_weak: float = 0.06
    sl_weak: float = 0.07
    tp_pump: float = 0.08
    sl_pump: float = 0.07
    max_hold_min: float | None = 720.0
    bar_interval: str = "5min"


def normalize_ticks(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize Bybit public trade archive rows to a standard tick schema."""
    required = {"timestamp", "side", "size", "price"}
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"tick dataframe missing columns: {sorted(missing)}")

    out = df.copy()
    # Bybit archive timestamps are seconds with millisecond decimals.
    ts_ms = (pd.to_numeric(out["timestamp"], errors="coerce").astype(float).to_numpy() * 1000).astype("int64")
    out["dt"] = pd.to_datetime(ts_ms, unit="ms", utc=True).as_unit("ns")
    out["ts_ns"] = out["dt"].astype("int64")
    out["size"] = pd.to_numeric(out["size"], errors="coerce")
    out["price"] = pd.to_numeric(out["price"], errors="coerce")
    if "foreignNotional" in out.columns:
        out["quote"] = pd.to_numeric(out["foreignNotional"], errors="coerce").abs()
    elif "quote" in out.columns:
        out["quote"] = pd.to_numeric(out["quote"], errors="coerce").abs()
    else:
        out["quote"] = (out["size"] * out["price"]).abs()
    out["side"] = out["side"].astype(str)
    out = out.dropna(subset=["dt", "ts_ns", "size", "price", "quote"]).sort_values("ts_ns")
    return out.reset_index(drop=True)


def make_bars(ticks: pd.DataFrame, interval: str = "5min") -> pd.DataFrame:
    """Build OHLCV bars plus cumulative VWAP from normalized ticks."""
    if ticks.empty:
        return pd.DataFrame()
    g = ticks.set_index("dt").resample(interval, label="left", closed="left")
    bars = pd.DataFrame(
        {
            "open": g["price"].first(),
            "high": g["price"].max(),
            "low": g["price"].min(),
            "close": g["price"].last(),
            "volume": g["size"].sum(),
            "turnover": g["quote"].sum(),
            "trades": g["price"].count(),
        }
    ).dropna(subset=["open", "high", "low", "close"])
    bars["cum_turnover"] = bars["turnover"].cumsum()
    bars["cum_volume"] = bars["volume"].cumsum()
    bars["vwap"] = bars["cum_turnover"] / bars["cum_volume"].replace(0, np.nan)
    return bars.reset_index()


def path_max_short(bars: pd.DataFrame) -> tuple[float, int, int]:
    """Return max high-to-subsequent-low move, peak index, trough index."""
    if bars.empty:
        return float("nan"), -1, -1
    highs = bars["high"].to_numpy(float)
    lows = bars["low"].to_numpy(float)
    running_high = np.maximum.accumulate(highs)
    dd = lows / running_high - 1
    trough = int(np.nanargmin(dd))
    peak = int(np.nanargmax(highs[: trough + 1]))
    return -float(dd[trough]), peak, trough


def path_runup(bars: pd.DataFrame) -> tuple[float, int, int]:
    """Return max low-to-subsequent-high runup, trough index, peak index."""
    if bars.empty:
        return float("nan"), -1, -1
    lows = bars["low"].to_numpy(float)
    highs = bars["high"].to_numpy(float)
    running_low = np.minimum.accumulate(lows)
    ru = highs / running_low - 1
    peak = int(np.nanargmax(ru))
    trough = int(np.nanargmin(lows[: peak + 1]))
    return float(ru[peak]), trough, peak


def first_vwap_loss_after_peak(bars: pd.DataFrame, peak_idx: int) -> dict[str, Any] | None:
    """First bar close below cumulative VWAP after the selected peak."""
    if bars.empty or peak_idx < 0:
        return None
    peak_time = bars.iloc[peak_idx]["dt"]
    after = bars[bars["dt"] > peak_time]
    below = after[after["close"] < after["vwap"]]
    if below.empty:
        return None
    row = below.iloc[0]
    return {"time": row["dt"], "ts_ns": int(row["dt"].value), "price": float(row["close"])}


def midpoint_loss_after_runup(bars: pd.DataFrame, trough_idx: int, peak_idx: int) -> pd.Timestamp | None:
    """First close below the 50% midpoint of the pump impulse."""
    if bars.empty or trough_idx < 0 or peak_idx < 0:
        return None
    low = float(bars.iloc[trough_idx]["low"])
    high = float(bars.iloc[peak_idx]["high"])
    midpoint = low + 0.5 * (high - low)
    after = bars[bars["dt"] > bars.iloc[peak_idx]["dt"]]
    below = after[after["close"] < midpoint]
    return None if below.empty else below.iloc[0]["dt"]


def sell_share_after(ticks: pd.DataFrame, ts_ns: int) -> float:
    """Quote-volume sell share after a timestamp, in percent."""
    after = ticks[ticks["ts_ns"] > ts_ns]
    if after.empty:
        return float("nan")
    total = after["quote"].sum()
    sell = after.loc[after["side"].str.lower() == "sell", "quote"].sum()
    return float(sell / total * 100) if total else float("nan")


def first_barrier(
    prices: np.ndarray,
    ts_ns: np.ndarray,
    entry_price: float,
    entry_ns: int,
    tp: float,
    sl: float,
    max_hold_min: float | None = None,
) -> dict[str, Any]:
    """For a short position, return first TP/SL/time-stop outcome."""
    if prices.size == 0:
        return {"outcome": "no_data", "exit_time_utc": None, "exit_price": np.nan, "pnl_underlying_pct": np.nan, "minutes_to_exit": np.nan}
    if max_hold_min is not None:
        max_ns = entry_ns + int(max_hold_min * 60 * 1e9)
        keep = ts_ns <= max_ns
        prices = prices[keep]
        ts_ns = ts_ns[keep]
        if prices.size == 0:
            return {"outcome": "time_stop", "exit_time_utc": None, "exit_price": np.nan, "pnl_underlying_pct": 0.0, "minutes_to_exit": max_hold_min}

    target = entry_price * (1 - tp)
    stop = entry_price * (1 + sl)
    hit_tp = prices <= target
    hit_sl = prices >= stop
    hit = hit_tp | hit_sl
    if hit.any():
        i = int(np.argmax(hit))
        outcome = "tp" if hit_tp[i] else "sl"
        exit_price = target if outcome == "tp" else stop
        pnl = (entry_price - exit_price) / entry_price * 100
        minutes = (ts_ns[i] - entry_ns) / 1e9 / 60
        return {
            "outcome": outcome,
            "exit_time_utc": pd.to_datetime(ts_ns[i], unit="ns", utc=True).isoformat(),
            "exit_price": float(exit_price),
            "pnl_underlying_pct": float(pnl),
            "minutes_to_exit": float(minutes),
        }
    exit_price = float(prices[-1])
    pnl = (entry_price - exit_price) / entry_price * 100
    minutes = (ts_ns[-1] - entry_ns) / 1e9 / 60
    return {
        "outcome": "time_stop" if max_hold_min is not None else "eod",
        "exit_time_utc": pd.to_datetime(ts_ns[-1], unit="ns", utc=True).isoformat(),
        "exit_price": exit_price,
        "pnl_underlying_pct": float(pnl),
        "minutes_to_exit": float(minutes),
    }


def score_symbol_day(symbol: str, day: str, cur_ticks_raw: pd.DataFrame, prev_ticks_raw: pd.DataFrame, cfg: StrategyConfig) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Score one symbol/day and simulate the selected entry if candidate."""
    cur_ticks = normalize_ticks(cur_ticks_raw)
    prev_ticks = normalize_ticks(prev_ticks_raw)
    if cur_ticks.empty or prev_ticks.empty:
        return None, None

    cur_bars = make_bars(cur_ticks, cfg.bar_interval)
    prev_bars = make_bars(prev_ticks, cfg.bar_interval)
    if cur_bars.empty or prev_bars.empty:
        return None, None

    turnover = float(cur_ticks["quote"].sum())
    prev_turnover = float(prev_ticks["quote"].sum())
    turnover_ratio = turnover / prev_turnover if prev_turnover else np.nan
    prev_ret = (float(prev_ticks["price"].iloc[-1]) / float(prev_ticks["price"].iloc[0]) - 1) * 100
    prev_short, _, _ = path_max_short(prev_bars)
    prev_max_dd = -prev_short * 100

    max_short, weak_peak, weak_trough = path_max_short(cur_bars)
    max_runup, run_trough, run_peak = path_runup(cur_bars)
    if weak_peak < 0 or run_peak < 0:
        return None, None

    weak_peak_time = cur_bars.iloc[weak_peak]["dt"]
    pump_peak_time = cur_bars.iloc[run_peak]["dt"]
    weak_peak_hour = weak_peak_time.hour + weak_peak_time.minute / 60
    pump_peak_hour = pump_peak_time.hour + pump_peak_time.minute / 60
    weak_entry = first_vwap_loss_after_peak(cur_bars, weak_peak)
    pump_entry = first_vwap_loss_after_peak(cur_bars, run_peak)
    midpoint_loss = midpoint_loss_after_runup(cur_bars, run_trough, run_peak)
    weak_sell = sell_share_after(cur_ticks, int(weak_peak_time.value))
    pump_sell = sell_share_after(cur_ticks, int(pump_peak_time.value))

    weak_score = 0
    if prev_ret <= -4:
        weak_score += 2
    if prev_max_dd <= -9:
        weak_score += 2
    if turnover_ratio <= 0.8:
        weak_score += 2
    if 3 <= max_runup * 100 <= 12:
        weak_score += 1
    if weak_peak_hour <= 11:
        weak_score += 1
    if weak_entry is not None:
        weak_score += 2
    if weak_sell >= 52:
        weak_score += 1

    pump_score = 0
    if turnover_ratio >= 8:
        pump_score += 2
    if turnover_ratio >= 15:
        pump_score += 1
    if max_runup * 100 >= 25:
        pump_score += 2
    if 7 <= pump_peak_hour <= 11.5:
        pump_score += 1
    if pump_entry is not None:
        pump_score += 2
    if midpoint_loss is not None:
        pump_score += 1
    if pump_sell >= 52:
        pump_score += 1

    main_candidate = turnover >= cfg.min_turnover and (weak_score >= cfg.weak_threshold or pump_score >= cfg.pump_threshold)
    mode = None
    entry = None
    tp = None
    sl = None
    if main_candidate:
        if pump_score >= cfg.pump_threshold and pump_score >= weak_score:
            mode = "pump"
            entry = pump_entry
            tp = cfg.tp_pump
            sl = cfg.sl_pump
        else:
            mode = "weak"
            entry = weak_entry
            tp = cfg.tp_weak
            sl = cfg.sl_weak

    metrics = {
        "date": str(day),
        "symbol": symbol,
        "turnover_usdt": turnover,
        "prev_turnover_usdt": prev_turnover,
        "turnover_ratio_vs_prev": turnover_ratio,
        "prev_day_ret_pct": prev_ret,
        "prev_day_max_dd_pct": prev_max_dd,
        "max_short_move_pct": max_short * 100,
        "max_runup_pct": max_runup * 100,
        "weak_peak_time_utc": weak_peak_time.isoformat(),
        "pump_peak_time_utc": pump_peak_time.isoformat(),
        "weak_peak_hour_utc": weak_peak_hour,
        "pump_peak_hour_utc": pump_peak_hour,
        "weak_vwap_loss_time_utc": None if weak_entry is None else weak_entry["time"].isoformat(),
        "pump_vwap_loss_time_utc": None if pump_entry is None else pump_entry["time"].isoformat(),
        "weak_sell_share_after_peak_pct": weak_sell,
        "pump_sell_share_after_peak_pct": pump_sell,
        "weak_score": weak_score,
        "pump_score": pump_score,
        "candidate_score": max(weak_score, pump_score),
        "main_candidate": bool(main_candidate),
        "selected_mode": mode,
    }

    trade = None
    if main_candidate and entry is not None and tp is not None and sl is not None:
        mask = cur_ticks["ts_ns"].to_numpy() > entry["ts_ns"]
        prices = cur_ticks.loc[mask, "price"].to_numpy(float)
        ns = cur_ticks.loc[mask, "ts_ns"].to_numpy("int64")
        mfe = (entry["price"] - np.min(prices)) / entry["price"] * 100 if prices.size else np.nan
        mae = (np.max(prices) - entry["price"]) / entry["price"] * 100 if prices.size else np.nan
        trade = {
            "date": str(day),
            "symbol": symbol,
            "mode": mode,
            "entry_time_utc": entry["time"].isoformat(),
            "entry_price": entry["price"],
            "tp_pct": tp * 100,
            "sl_pct": sl * 100,
            "mfe_after_entry_pct": mfe,
            "mae_after_entry_pct": mae,
            **first_barrier(prices, ns, entry["price"], entry["ts_ns"], tp, sl, cfg.max_hold_min),
        }
    return metrics, trade
