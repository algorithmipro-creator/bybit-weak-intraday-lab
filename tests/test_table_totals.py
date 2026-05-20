import pandas as pd
import pytest

from ui.table_totals import append_account_total_row, append_trade_total_row


def test_append_trade_total_row_adds_counts_sums_and_averages() -> None:
    trades = pd.DataFrame(
        [
            {
                "symbol": "AAAUSDT",
                "outcome": "tp",
                "pnl_underlying_pct": 6.0,
                "mfe_after_entry_pct": 8.0,
                "mae_after_entry_pct": 1.0,
            },
            {
                "symbol": "BBBUSDT",
                "outcome": "sl",
                "pnl_underlying_pct": -7.0,
                "mfe_after_entry_pct": 2.0,
                "mae_after_entry_pct": 7.0,
            },
            {
                "symbol": "CCCUSDT",
                "outcome": "time_stop",
                "pnl_underlying_pct": 1.0,
                "mfe_after_entry_pct": 4.0,
                "mae_after_entry_pct": 2.0,
            },
        ]
    )

    out = append_trade_total_row(trades)
    total = out.iloc[-1]

    assert len(out) == 4
    assert total["row_type"] == "TOTAL"
    assert total["symbol"] == "TOTAL"
    assert total["total_trades"] == 3
    assert total["tp_count"] == 1
    assert total["sl_count"] == 1
    assert total["time_stop_count"] == 1
    assert total["sum_pnl_underlying_pct"] == pytest.approx(0.0)
    assert total["avg_pnl_underlying_pct"] == pytest.approx(0.0)
    assert total["sum_mfe_after_entry_pct"] == pytest.approx(14.0)
    assert total["avg_mfe_after_entry_pct"] == pytest.approx(14.0 / 3.0)
    assert total["sum_mae_after_entry_pct"] == pytest.approx(10.0)
    assert total["avg_mae_after_entry_pct"] == pytest.approx(10.0 / 3.0)


def test_append_trade_total_row_does_not_mutate_source_frame() -> None:
    trades = pd.DataFrame([{"symbol": "AAAUSDT", "outcome": "tp", "pnl_underlying_pct": 6.0}])
    original_columns = list(trades.columns)

    append_trade_total_row(trades)

    assert list(trades.columns) == original_columns
    assert len(trades) == 1


def test_append_trade_total_row_keeps_empty_frames_empty() -> None:
    trades = pd.DataFrame(columns=["symbol", "outcome", "pnl_underlying_pct"])

    out = append_trade_total_row(trades)

    assert out.empty
    assert list(out.columns) == ["symbol", "outcome", "pnl_underlying_pct"]


def test_append_account_total_row_adds_final_equity_and_net_totals() -> None:
    curve = pd.DataFrame(
        [
            {
                "symbol": "AAAUSDT",
                "net_pnl_usd": 50.0,
                "costs_usd": 1.0,
                "account_return_pct": 0.5,
                "equity_after_usd": 10050.0,
            },
            {
                "symbol": "BBBUSDT",
                "net_pnl_usd": -25.0,
                "costs_usd": 1.2,
                "account_return_pct": -0.25,
                "equity_after_usd": 10025.0,
            },
        ]
    )

    out = append_account_total_row(curve, initial_equity_usd=10000.0)
    total = out.iloc[-1]

    assert len(out) == 3
    assert total["row_type"] == "TOTAL"
    assert total["symbol"] == "TOTAL"
    assert total["total_trades"] == 2
    assert total["total_net_pnl_usd"] == pytest.approx(25.0)
    assert total["total_costs_usd"] == pytest.approx(2.2)
    assert total["final_equity_usd"] == pytest.approx(10025.0)
    assert total["total_return_pct"] == pytest.approx(0.25)


def test_append_account_total_row_leaves_total_return_blank_without_initial_equity() -> None:
    curve = pd.DataFrame(
        [
            {"symbol": "AAAUSDT", "net_pnl_usd": 100.0, "costs_usd": 1.0, "equity_after_usd": 10100.0},
        ]
    )

    out = append_account_total_row(curve)
    total = out.iloc[-1]

    assert total["total_net_pnl_usd"] == pytest.approx(100.0)
    assert total["final_equity_usd"] == pytest.approx(10100.0)
    assert pd.isna(total["total_return_pct"])
