from __future__ import annotations

import pandas as pd

from bybit_weak_intraday.core import StrategyConfig
from bybit_weak_intraday.optimizer import run_archive_tp_sl_grid, summarize_grid_trades


def test_summarize_grid_trades_aggregates_outcomes():
    trades = pd.DataFrame(
        [
            {"tp_pct": 4.0, "sl_pct": 7.0, "outcome": "tp", "pnl_underlying_pct": 4.0, "minutes_to_exit": 10.0},
            {"tp_pct": 4.0, "sl_pct": 7.0, "outcome": "sl", "pnl_underlying_pct": -7.0, "minutes_to_exit": 20.0},
            {"tp_pct": 4.0, "sl_pct": 7.0, "outcome": "eod", "pnl_underlying_pct": 1.0, "minutes_to_exit": 30.0},
            {"tp_pct": 6.0, "sl_pct": 7.0, "outcome": "tp", "pnl_underlying_pct": 6.0, "minutes_to_exit": 40.0},
        ]
    )

    summary = summarize_grid_trades(trades)
    row = summary[(summary["tp_pct"] == 4.0) & (summary["sl_pct"] == 7.0)].iloc[0]

    assert row["trades"] == 3
    assert row["tp_hits"] == 1
    assert row["sl_hits"] == 1
    assert row["time_or_eod_exits"] == 1
    assert row["avg_underlying_pnl"] == -2.0 / 3.0
    assert row["median_underlying_pnl"] == 1.0
    assert row["avg_minutes_to_exit"] == 20.0
    assert row["tp_rate"] == 1.0 / 3.0
    assert row["sl_rate"] == 1.0 / 3.0


def test_run_archive_tp_sl_grid_calls_scanner_for_each_pair(monkeypatch):
    calls: list[tuple[float, float]] = []

    def fake_run_archive_scan(**kwargs):
        cfg = kwargs["cfg"]
        calls.append((cfg.tp_weak, cfg.sl_weak))
        trades = pd.DataFrame(
            [
                {
                    "date": "2026-03-18",
                    "symbol": "ENAUSDT",
                    "mode": "weak",
                    "outcome": "tp",
                    "pnl_underlying_pct": cfg.tp_weak * 100,
                    "minutes_to_exit": 12.0,
                }
            ]
        )
        return pd.DataFrame(), trades

    monkeypatch.setattr("bybit_weak_intraday.optimizer.run_archive_scan", fake_run_archive_scan)

    summary, trades = run_archive_tp_sl_grid(
        start="2026-03-18",
        end="2026-03-18",
        symbols=["ENAUSDT"],
        tp_grid=[0.04, 0.06],
        sl_grid=[0.05, 0.07],
        cfg=StrategyConfig(min_turnover=0),
    )

    assert calls == [(0.04, 0.05), (0.04, 0.07), (0.06, 0.05), (0.06, 0.07)]
    assert len(summary) == 4
    assert len(trades) == 4
    assert set(trades["tp_pct"]) == {4.0, 6.0}
    assert set(trades["sl_pct"]) == {5.0, 7.0}
