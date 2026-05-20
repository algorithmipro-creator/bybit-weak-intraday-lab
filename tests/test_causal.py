from __future__ import annotations

import pandas as pd

from bybit_weak_intraday.core import normalize_ticks
from bybit_weak_intraday.causal import sell_share_between, truncate_ticks_at


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
