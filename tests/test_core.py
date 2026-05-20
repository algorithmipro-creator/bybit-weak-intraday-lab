from __future__ import annotations

import pandas as pd

from bybit_weak_intraday.core import StrategyConfig, make_bars, normalize_ticks, path_max_short, path_runup


def test_normalize_ticks_computes_quote_when_missing():
    df = pd.DataFrame(
        {
            "timestamp": [1773792000.0, 1773792001.0],
            "side": ["Buy", "Sell"],
            "size": [10, 5],
            "price": [2.0, 2.1],
        }
    )
    out = normalize_ticks(df)
    assert "quote" in out.columns
    assert out["quote"].sum() == 30.5
    assert out["dt"].dt.tz is not None


def test_normalize_ticks_stores_timestamp_in_nanoseconds():
    df = pd.DataFrame(
        {
            "timestamp": [1773792000.0655],
            "side": ["Sell"],
            "size": [10],
            "price": [2.0],
        }
    )

    out = normalize_ticks(df)

    assert out.loc[0, "ts_ns"] == out.loc[0, "dt"].value
    assert out.loc[0, "ts_ns"] > 10**18


def test_path_metrics_from_bars():
    ticks = pd.DataFrame(
        {
            "timestamp": [1773792000, 1773792300, 1773792600, 1773792900],
            "side": ["Buy", "Buy", "Sell", "Sell"],
            "size": [1, 1, 1, 1],
            "price": [100, 120, 110, 90],
        }
    )
    nt = normalize_ticks(ticks)
    bars = make_bars(nt, "5min")
    short, peak_idx, trough_idx = path_max_short(bars)
    runup, trough0, peak0 = path_runup(bars)
    assert round(short * 100, 2) == 25.0
    assert round(runup * 100, 2) == 20.0
    assert peak_idx <= trough_idx
    assert trough0 <= peak0


def test_strategy_config_defaults():
    cfg = StrategyConfig()
    assert cfg.weak_threshold == 9
    assert cfg.pump_threshold == 9
    assert cfg.tp_weak == 0.06
