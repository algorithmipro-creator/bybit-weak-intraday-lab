from __future__ import annotations

import pandas as pd

from bybit_weak_intraday.core import normalize_ticks
from bybit_weak_intraday.causal import find_causal_signals, sell_share_between, truncate_ticks_at
from bybit_weak_intraday.core import StrategyConfig


def test_truncate_ticks_at_removes_future_rows():
    raw = pd.DataFrame(
        {
            "timestamp": [1773792000, 1773792001, 1773792002],
            "side": ["Buy", "Sell", "Sell"],
            "size": [1, 2, 100],
            "price": [10, 10, 10],
        }
    )
    ticks = normalize_ticks(raw)
    signal_ns = int(ticks.iloc[1]["ts_ns"])

    out = truncate_ticks_at(ticks, signal_ns)

    assert len(out) == 2
    assert out["size"].sum() == 3
    assert out["ts_ns"].max() == signal_ns


def test_sell_share_between_uses_only_interval():
    raw = pd.DataFrame(
        {
            "timestamp": [1773792000, 1773792001, 1773792002, 1773792003],
            "side": ["Buy", "Sell", "Sell", "Buy"],
            "size": [10, 4, 6, 100],
            "price": [1, 1, 1, 1],
        }
    )
    ticks = normalize_ticks(raw)
    start_ns = int(ticks.iloc[0]["ts_ns"])
    end_ns = int(ticks.iloc[2]["ts_ns"])

    sell_share = sell_share_between(ticks, start_ns, end_ns)

    assert sell_share == 50.0


def _ticks(prices: list[float], sides: list[str], start_ts: int = 1773792000) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": [start_ts + i * 300 for i in range(len(prices))],
            "side": sides,
            "size": [1000 for _ in prices],
            "price": prices,
        }
    )


def test_find_causal_signals_emits_weak_without_future_ticks():
    prev = _ticks(
        prices=[100, 96, 92, 90],
        sides=["Sell", "Sell", "Sell", "Sell"],
        start_ts=1773705600,
    )
    cur = _ticks(
        prices=[90, 94, 96, 95, 93, 91, 89, 200],
        sides=["Buy", "Buy", "Buy", "Sell", "Sell", "Sell", "Sell", "Buy"],
    )
    cfg = StrategyConfig(min_turnover=0, weak_threshold=8, pump_threshold=99)

    signals = find_causal_signals("TESTUSDT", "2026-03-18", cur, prev, cfg)

    weak = [s for s in signals if s.mode == "weak"]
    assert len(weak) == 1
    assert weak[0].symbol == "TESTUSDT"
    assert weak[0].signal_price < weak[0].vwap_at_signal
    assert weak[0].signal_price != 200
    assert weak[0].turnover_so_far_usdt == 468_000


def test_find_causal_signals_emits_pump_after_vwap_loss():
    prev = _ticks(
        prices=[1, 1, 1, 1],
        sides=["Buy", "Sell", "Buy", "Sell"],
        start_ts=1773705600,
    )
    cur = _ticks(
        prices=[10, 12, 15, 14, 13, 11, 10.5],
        sides=["Buy", "Buy", "Buy", "Sell", "Sell", "Sell", "Sell"],
    )
    cfg = StrategyConfig(min_turnover=0, weak_threshold=99, pump_threshold=8)

    signals = find_causal_signals("PUMPUSDT", "2026-03-18", cur, prev, cfg)

    pump = [s for s in signals if s.mode == "pump"]
    assert len(pump) == 1
    assert pump[0].pump_score >= 8
    assert pump[0].runup_so_far_pct >= 25
    assert pump[0].signal_price < pump[0].vwap_at_signal
