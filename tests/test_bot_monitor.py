from __future__ import annotations

import pandas as pd
import pytest

from ui.bot_monitor import (
    build_scanner_watchlist,
    normalize_open_orders,
    normalize_positions,
    result_rows,
    safe_float,
    select_latest_scanner_job,
    summarize_wallet,
)


def test_safe_float_handles_numbers_strings_and_missing_values() -> None:
    assert safe_float("12.5") == 12.5
    assert safe_float(7) == 7.0
    assert safe_float("") is None
    assert safe_float(None) is None
    assert safe_float("not-a-number") is None


def test_safe_float_rejects_non_finite_values() -> None:
    assert safe_float("NaN") is None
    assert safe_float(float("nan")) is None
    assert safe_float("inf") is None
    assert safe_float(float("inf")) is None


def test_result_rows_extracts_bybit_result_list() -> None:
    assert result_rows({"result": {"list": [{"symbol": "ENAUSDT"}]}}) == [{"symbol": "ENAUSDT"}]
    assert result_rows({"result": {"list": None}}) == []
    assert result_rows(None) == []


def test_summarize_wallet_extracts_account_numbers() -> None:
    payload = {
        "result": {
            "list": [
                {
                    "totalEquity": "1024.80",
                    "totalWalletBalance": "1025.22",
                    "totalAvailableBalance": "1018.12",
                    "totalInitialMargin": "6.68",
                    "totalPerpUPL": "-0.42",
                    "coin": [{"coin": "USDT", "walletBalance": "1025.22"}],
                }
            ]
        }
    }

    summary = summarize_wallet(payload)

    assert summary == {
        "equity": 1024.80,
        "wallet_balance": 1025.22,
        "available_balance": 1018.12,
        "margin_used": 6.68,
        "unrealized_pnl": -0.42,
    }


def test_summarize_wallet_handles_missing_fields() -> None:
    assert summarize_wallet({"result": {"list": [{}]}}) == {
        "equity": None,
        "wallet_balance": None,
        "available_balance": None,
        "margin_used": None,
        "unrealized_pnl": None,
    }


def test_normalize_positions_derives_pnl_pct_and_infers_tpsl_from_orders() -> None:
    positions = {
        "result": {
            "list": [
                {
                    "symbol": "ENAUSDT",
                    "side": "Sell",
                    "size": "95",
                    "avgPrice": "0.10441",
                    "markPrice": "0.10485",
                    "unrealisedPnl": "-0.42",
                    "positionValue": "104.41",
                    "leverage": "5",
                    "positionIM": "20.88",
                    "liqPrice": "",
                }
            ]
        }
    }
    orders = {
        "result": {
            "list": [
                {
                    "symbol": "ENAUSDT",
                    "side": "Buy",
                    "orderType": "Market",
                    "qty": "95",
                    "triggerPrice": "0.09814",
                    "stopOrderType": "TakeProfit",
                    "orderStatus": "Untriggered",
                },
                {
                    "symbol": "ENAUSDT",
                    "side": "Buy",
                    "orderType": "Market",
                    "qty": "95",
                    "triggerPrice": "0.11172",
                    "stopOrderType": "StopLoss",
                    "orderStatus": "Untriggered",
                },
            ]
        }
    }

    rows = normalize_positions(positions, orders)

    assert len(rows) == 1
    row = rows[0]
    assert row["symbol"] == "ENAUSDT"
    assert row["side"] == "Sell"
    assert row["size"] == 95.0
    assert row["entry_price"] == 0.10441
    assert row["mark_price"] == 0.10485
    assert row["unrealized_pnl"] == -0.42
    assert row["pnl_pct"] == pytest.approx(-0.0040226032)
    assert row["leverage"] == 5.0
    assert row["margin"] == 20.88
    assert row["take_profit"] == 0.09814
    assert row["stop_loss"] == 0.11172


def test_normalize_open_orders_keeps_trigger_prices_and_statuses() -> None:
    payload = {
        "result": {
            "list": [
                {
                    "symbol": "ENAUSDT",
                    "side": "Buy",
                    "orderType": "Market",
                    "qty": "95",
                    "price": "",
                    "triggerPrice": "0.09814",
                    "stopOrderType": "TakeProfit",
                    "orderStatus": "Untriggered",
                    "createdTime": "1779363307000",
                }
            ]
        }
    }

    rows = normalize_open_orders(payload)

    assert rows == [
        {
            "symbol": "ENAUSDT",
            "side": "Buy",
            "order_type": "Market",
            "qty": 95.0,
            "price": None,
            "trigger_price": 0.09814,
            "stop_order_type": "TakeProfit",
            "status": "Untriggered",
            "created_time": "2026-05-21T11:35:07+00:00",
        }
    ]


def test_normalize_open_orders_handles_non_finite_timestamp() -> None:
    payload = {"result": {"list": [{"symbol": "ENAUSDT", "createdTime": "NaN"}]}}

    rows = normalize_open_orders(payload)

    assert rows[0]["created_time"] is None


def test_select_latest_scanner_job_prefers_latest_causal_scan() -> None:
    jobs = [
        {"job_id": "scan-new", "job_type": "scan", "status": "done", "updated_at": "2026-05-21T12:00:00+00:00"},
        {"job_id": "causal-old", "job_type": "causal_scan", "status": "done", "updated_at": "2026-05-21T10:00:00+00:00"},
    ]

    assert select_latest_scanner_job(jobs)["job_id"] == "causal-old"


def test_select_latest_scanner_job_falls_back_to_regular_scan() -> None:
    jobs = [
        {"job_id": "scan-old", "job_type": "scan", "status": "done", "updated_at": "2026-05-21T09:00:00+00:00"},
        {"job_id": "scan-new", "job_type": "scan", "status": "done", "updated_at": "2026-05-21T12:00:00+00:00"},
        {"job_id": "running-causal", "job_type": "causal_scan", "status": "running", "updated_at": "2026-05-21T13:00:00+00:00"},
    ]

    assert select_latest_scanner_job(jobs)["job_id"] == "scan-new"


def test_select_latest_scanner_job_handles_malformed_input() -> None:
    assert select_latest_scanner_job(None) is None
    assert select_latest_scanner_job(
        ["bad", {"job_id": "scan", "job_type": "scan", "status": "done"}]
    )["job_id"] == "scan"


def test_select_latest_scanner_job_returns_none_for_non_iterable_input() -> None:
    assert select_latest_scanner_job(123) is None


def test_select_latest_scanner_job_handles_mixed_naive_and_invalid_timestamps() -> None:
    jobs = [
        {"job_id": "invalid", "job_type": "scan", "status": "done", "updated_at": "not-a-date"},
        {"job_id": "naive", "job_type": "scan", "status": "done", "updated_at": "2026-05-21T12:00:00"},
    ]

    assert select_latest_scanner_job(jobs)["job_id"] == "naive"


def test_build_scanner_watchlist_from_causal_signals() -> None:
    signals = pd.DataFrame(
        [
            {
                "symbol": "JTOUSDT",
                "mode": "pump",
                "score": 10,
                "signal_time_utc": "2026-03-18T10:00:00+00:00",
                "signal_price": 2.5,
                "turnover_so_far_usdt": 1_500_000,
            }
        ]
    )
    evaluations = pd.DataFrame([{"symbol": "JTOUSDT", "outcome": "tp", "pnl_underlying_pct": 0.06}])

    watchlist = build_scanner_watchlist("causal_scan", signals=signals, evaluations=evaluations)

    assert list(watchlist.columns) == [
        "symbol",
        "mode",
        "score",
        "time_utc",
        "price",
        "turnover_usdt",
        "status",
        "outcome",
        "pnl_underlying_pct",
    ]
    assert watchlist.loc[0, "symbol"] == "JTOUSDT"
    assert watchlist.loc[0, "status"] == "waiting"
    assert watchlist.loc[0, "outcome"] == "tp"


def test_build_scanner_watchlist_matches_causal_evaluations_by_signal_time() -> None:
    signals = pd.DataFrame(
        [
            {
                "date": "2026-03-18",
                "symbol": "JTOUSDT",
                "mode": "pump",
                "score": 9,
                "signal_time_utc": "2026-03-18T10:00:00+00:00",
                "signal_price": 2.5,
                "turnover_so_far_usdt": 1_500_000,
            },
            {
                "date": "2026-03-18",
                "symbol": "JTOUSDT",
                "mode": "pump",
                "score": 10,
                "signal_time_utc": "2026-03-18T11:00:00+00:00",
                "signal_price": 2.7,
                "turnover_so_far_usdt": 1_800_000,
            },
        ]
    )
    evaluations = pd.DataFrame(
        [
            {
                "date": "2026-03-18",
                "symbol": "JTOUSDT",
                "signal_time_utc": "2026-03-18T10:00:00+00:00",
                "outcome": "sl",
                "pnl_underlying_pct": -0.07,
            },
            {
                "date": "2026-03-18",
                "symbol": "JTOUSDT",
                "signal_time_utc": "2026-03-18T11:00:00+00:00",
                "outcome": "tp",
                "pnl_underlying_pct": 0.08,
            },
        ]
    )

    watchlist = build_scanner_watchlist("causal_scan", signals=signals, evaluations=evaluations)

    assert list(watchlist["outcome"]) == ["sl", "tp"]
    assert list(watchlist["pnl_underlying_pct"]) == [-0.07, 0.08]


def test_build_scanner_watchlist_handles_malformed_inputs() -> None:
    assert build_scanner_watchlist("causal_scan", signals="bad").empty
    assert build_scanner_watchlist("scan", trades=object()).empty


def test_build_scanner_watchlist_rejects_scalar_row_collections() -> None:
    assert build_scanner_watchlist("causal_scan", signals=[1, 2]).empty
    assert build_scanner_watchlist("scan", trades=[1, 2]).empty


def test_build_scanner_watchlist_sanitizes_non_finite_numeric_fields() -> None:
    trades = pd.DataFrame(
        [
            {
                "symbol": "ENAUSDT",
                "mode": "weak",
                "candidate_score": "NaN",
                "entry_time_utc": "2026-03-18T10:00:00+00:00",
                "entry_price": "inf",
                "turnover_usdt": "NaN",
                "pnl_underlying_pct": "inf",
            }
        ]
    )

    watchlist = build_scanner_watchlist("scan", trades=trades)

    assert pd.isna(watchlist.loc[0, "score"])
    assert pd.isna(watchlist.loc[0, "price"])
    assert pd.isna(watchlist.loc[0, "turnover_usdt"])
    assert pd.isna(watchlist.loc[0, "pnl_underlying_pct"])


def test_select_latest_scanner_job_treats_missing_or_empty_job_type_as_regular_scan() -> None:
    jobs = [
        {"job_id": "legacy-old", "status": "done", "updated_at": "2026-05-21T09:00:00+00:00"},
        {"job_id": "legacy-new", "job_type": "", "status": "done", "updated_at": "2026-05-21T12:00:00+00:00"},
    ]

    assert select_latest_scanner_job(jobs)["job_id"] == "legacy-new"


def test_build_scanner_watchlist_from_regular_scan_marks_candidates() -> None:
    trades = pd.DataFrame(
        [
            {
                "symbol": "ENAUSDT",
                "mode": "weak",
                "candidate_score": 9,
                "entry_time_utc": "2026-03-18T10:00:00+00:00",
                "entry_price": 0.1,
                "turnover_usdt": 1_200_000,
                "outcome": "tp",
                "pnl_underlying_pct": 0.06,
            }
        ]
    )

    watchlist = build_scanner_watchlist("scan", trades=trades)

    assert watchlist.loc[0, "status"] == "candidate"
    assert watchlist.loc[0, "score"] == 9
    assert watchlist.loc[0, "time_utc"] == "2026-03-18T10:00:00+00:00"


def test_build_scanner_watchlist_from_regular_scan_overrides_existing_status() -> None:
    trades = pd.DataFrame(
        [
            {
                "symbol": "ENAUSDT",
                "mode": "weak",
                "candidate_score": 9,
                "entry_time_utc": "2026-03-18T10:00:00+00:00",
                "entry_price": 0.1,
                "turnover_usdt": 1_200_000,
                "status": "waiting",
            }
        ]
    )

    watchlist = build_scanner_watchlist("scan", trades=trades)

    assert watchlist.loc[0, "status"] == "candidate"
