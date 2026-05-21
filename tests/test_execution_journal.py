from __future__ import annotations

from datetime import date

from bybit_weak_intraday.execution.journal import (
    JOURNAL_COLUMNS,
    append_journal_event,
    count_daily_test_orders,
    read_journal,
)


def test_append_journal_event_creates_csv_with_expected_columns(tmp_path) -> None:
    path = tmp_path / "execution_journal.csv"

    append_journal_event(
        path,
        {
            "created_at_utc": "2026-05-21T10:00:00+00:00",
            "event_id": "evt-1",
            "order_link_id": "bwi-1",
            "mode": "demo",
            "symbol": "ENAUSDT",
            "side": "Sell",
            "category": "linear",
            "requested_notional_usdt": 10,
            "qty": "1",
            "take_profit": "0.94",
            "stop_loss": "1.07",
            "status": "accepted",
            "reason": "allowed",
            "bybit_ret_code": 0,
            "bybit_ret_msg": "OK",
            "raw_response_path": "",
            "api_secret": "must-not-leak",
        },
    )

    frame = read_journal(path)

    assert len(frame) == 1
    assert list(frame.columns) == JOURNAL_COLUMNS
    assert frame.loc[0, "symbol"] == "ENAUSDT"
    assert frame.loc[0, "status"] == "accepted"
    assert "api_secret" not in frame.columns


def test_count_daily_test_orders_counts_only_accepted_or_sent_rows(tmp_path) -> None:
    path = tmp_path / "execution_journal.csv"
    append_journal_event(path, {"created_at_utc": "2026-05-21T10:00:00+00:00", "status": "accepted"})
    append_journal_event(path, {"created_at_utc": "2026-05-21T11:00:00+00:00", "status": "sent"})
    append_journal_event(path, {"created_at_utc": "2026-05-21T12:00:00+00:00", "status": "rejected"})
    append_journal_event(path, {"created_at_utc": "2026-05-20T12:00:00+00:00", "status": "accepted"})

    assert count_daily_test_orders(path, date(2026, 5, 21)) == 2


def test_read_journal_missing_file_returns_empty_frame(tmp_path) -> None:
    frame = read_journal(tmp_path / "missing.csv")

    assert frame.empty
