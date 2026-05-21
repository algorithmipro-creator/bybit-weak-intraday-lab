from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from backend.app.settings import Settings
from ui.result_summary import best_grid_result, trade_result_summary


def test_trade_result_summary_calculates_user_facing_kpis():
    trades = pd.DataFrame(
        [
            {"outcome": "tp", "pnl_underlying_pct": 6.0, "mfe_after_entry_pct": 9.0, "mae_after_entry_pct": 1.0},
            {"outcome": "sl", "pnl_underlying_pct": -7.0, "mfe_after_entry_pct": 2.0, "mae_after_entry_pct": 7.0},
            {"outcome": "eod", "pnl_underlying_pct": 1.0, "mfe_after_entry_pct": 4.0, "mae_after_entry_pct": 2.0},
        ]
    )

    summary = trade_result_summary(trades)

    assert summary["trades"] == 3
    assert summary["tp_rate_pct"] == pytest.approx(100 / 3)
    assert summary["sl_rate_pct"] == pytest.approx(100 / 3)
    assert summary["avg_pnl_pct"] == 0.0
    assert summary["median_pnl_pct"] == 1.0
    assert summary["avg_mfe_pct"] == 5.0
    assert summary["avg_mae_pct"] == pytest.approx(10 / 3)


def test_best_grid_result_prefers_avg_pnl_then_tp_rate():
    grid = pd.DataFrame(
        [
            {"tp_pct": 4.0, "sl_pct": 7.0, "trades": 10, "avg_underlying_pnl": 3.0, "tp_rate": 0.8},
            {"tp_pct": 6.0, "sl_pct": 7.0, "trades": 10, "avg_underlying_pnl": 4.0, "tp_rate": 0.5},
            {"tp_pct": 8.0, "sl_pct": 7.0, "trades": 10, "avg_underlying_pnl": 4.0, "tp_rate": 0.7},
        ]
    )

    best = best_grid_result(grid)

    assert best["tp_pct"] == 8.0
    assert best["sl_pct"] == 7.0
    assert best["avg_underlying_pnl"] == 4.0


def test_best_grid_result_ignores_empty_or_nan_rows():
    grid = pd.DataFrame(
        [
            {"tp_pct": 4.0, "sl_pct": 7.0, "trades": 0, "avg_underlying_pnl": float("nan"), "tp_rate": float("nan")},
            {"tp_pct": 6.0, "sl_pct": 7.0, "trades": 0, "avg_underlying_pnl": float("nan"), "tp_rate": float("nan")},
        ]
    )

    assert best_grid_result(grid) is None


def test_backend_defaults_to_one_worker_to_avoid_cache_write_conflicts():
    settings = Settings(_env_file=None)

    assert settings.max_workers == 1


def test_backend_defaults_use_relative_data_paths_for_local_test_imports():
    settings = Settings(_env_file=None)

    assert settings.data_dir == Path("data")
    assert settings.cache_dir == Path("data/bybit_archive_cache")
    assert settings.jobs_dir == Path("data/jobs")
    assert settings.execution_journal_path == Path("data/execution_journal.csv")
