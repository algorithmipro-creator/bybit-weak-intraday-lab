from __future__ import annotations

import pandas as pd
import pytest

from ui.account_backtest import AccountBacktestSettings, run_account_backtest


def test_account_backtest_single_winner_after_fees():
    trades = pd.DataFrame(
        [
            {
                "date": "2026-03-18",
                "symbol": "AAAUSDT",
                "mode": "weak",
                "outcome": "tp",
                "entry_time_utc": "2026-03-18T10:00:00+00:00",
                "exit_time_utc": "2026-03-18T11:00:00+00:00",
                "pnl_underlying_pct": 6.0,
            }
        ]
    )

    summary, curve = run_account_backtest(trades, AccountBacktestSettings())

    assert summary["trades"] == 1
    assert summary["skipped_trades"] == 0
    assert summary["final_equity_usd"] == pytest.approx(10058.8)
    assert summary["total_return_pct"] == pytest.approx(0.588)
    assert curve.loc[0, "gross_pnl_usd"] == pytest.approx(60.0)
    assert curve.loc[0, "costs_usd"] == pytest.approx(1.2)
    assert curve.loc[0, "net_pnl_usd"] == pytest.approx(58.8)


def test_account_backtest_compounds_by_exit_order():
    trades = pd.DataFrame(
        [
            {
                "symbol": "BBB",
                "entry_time_utc": "2026-03-18T10:00:00+00:00",
                "exit_time_utc": "2026-03-18T12:00:00+00:00",
                "pnl_underlying_pct": -7.0,
            },
            {
                "symbol": "AAA",
                "entry_time_utc": "2026-03-18T09:00:00+00:00",
                "exit_time_utc": "2026-03-18T11:00:00+00:00",
                "pnl_underlying_pct": 6.0,
            },
        ]
    )
    settings = AccountBacktestSettings(entry_fee_pct=0.0, exit_fee_pct=0.0)

    summary, curve = run_account_backtest(trades, settings)

    assert curve["symbol"].tolist() == ["AAA", "BBB"]
    assert curve.loc[0, "equity_after_usd"] == pytest.approx(10060.0)
    assert curve.loc[1, "equity_after_usd"] == pytest.approx(9989.58)
    assert summary["final_equity_usd"] == pytest.approx(9989.58)


def test_account_backtest_reports_max_drawdown():
    trades = pd.DataFrame(
        [
            {
                "symbol": "AAA",
                "entry_time_utc": "2026-03-18T09:00:00+00:00",
                "exit_time_utc": "2026-03-18T10:00:00+00:00",
                "pnl_underlying_pct": 10.0,
            },
            {
                "symbol": "BBB",
                "entry_time_utc": "2026-03-18T10:00:00+00:00",
                "exit_time_utc": "2026-03-18T11:00:00+00:00",
                "pnl_underlying_pct": -20.0,
            },
        ]
    )
    settings = AccountBacktestSettings(entry_fee_pct=0.0, exit_fee_pct=0.0)

    summary, _ = run_account_backtest(trades, settings)

    assert summary["max_drawdown_pct"] == pytest.approx(2.0)


def test_account_backtest_skips_missing_pnl_rows():
    trades = pd.DataFrame(
        [
            {
                "symbol": "AAA",
                "entry_time_utc": "2026-03-18T09:00:00+00:00",
                "exit_time_utc": "2026-03-18T10:00:00+00:00",
                "pnl_underlying_pct": None,
            },
            {
                "symbol": "BBB",
                "entry_time_utc": "2026-03-18T10:00:00+00:00",
                "exit_time_utc": "2026-03-18T11:00:00+00:00",
                "pnl_underlying_pct": 5.0,
            },
        ]
    )
    settings = AccountBacktestSettings(entry_fee_pct=0.0, exit_fee_pct=0.0)

    summary, curve = run_account_backtest(trades, settings)

    assert summary["trades"] == 1
    assert summary["skipped_trades"] == 1
    assert len(curve) == 1


def test_account_backtest_uses_entry_time_when_exit_time_is_missing():
    trades = pd.DataFrame(
        [
            {"symbol": "BBB", "entry_time_utc": "2026-03-18T12:00:00+00:00", "pnl_underlying_pct": 1.0},
            {"symbol": "AAA", "entry_time_utc": "2026-03-18T11:00:00+00:00", "pnl_underlying_pct": 1.0},
        ]
    )

    _, curve = run_account_backtest(trades, AccountBacktestSettings())

    assert curve["symbol"].tolist() == ["AAA", "BBB"]


def test_account_backtest_empty_input_is_stable():
    summary, curve = run_account_backtest(pd.DataFrame(), AccountBacktestSettings())

    assert summary["trades"] == 0
    assert summary["skipped_trades"] == 0
    assert summary["final_equity_usd"] == 10000.0
    assert summary["total_return_pct"] == 0.0
    assert curve.empty
