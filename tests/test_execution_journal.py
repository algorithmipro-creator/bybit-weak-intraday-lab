from __future__ import annotations

from datetime import date

from bybit_weak_intraday.execution import journal as journal_module
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


def test_append_journal_event_writes_header_for_empty_existing_file(tmp_path) -> None:
    path = tmp_path / "execution_journal.csv"
    path.touch()

    append_journal_event(
        path,
        {
            "created_at_utc": "2026-05-21T10:00:00+00:00",
            "mode": "demo",
            "status": "accepted",
        },
    )

    frame = read_journal(path)

    assert list(frame.columns) == JOURNAL_COLUMNS
    assert len(frame) == 1
    assert frame.loc[0, "status"] == "accepted"


def test_append_journal_event_normalizes_existing_extra_column_file(tmp_path) -> None:
    path = tmp_path / "execution_journal.csv"
    path.write_text(
        "created_at_utc,status,mode,api_secret\n"
        "2026-05-21T10:00:00+00:00,accepted,demo,must-not-leak\n",
        encoding="utf-8",
    )

    append_journal_event(
        path,
        {
            "created_at_utc": "2026-05-21T11:00:00+00:00",
            "mode": "demo",
            "status": "sent",
        },
    )

    frame = read_journal(path)

    assert list(frame.columns) == JOURNAL_COLUMNS
    assert "api_secret" not in frame.columns
    assert len(frame) == 2


def test_append_journal_event_normalizes_existing_missing_column_file(tmp_path) -> None:
    path = tmp_path / "execution_journal.csv"
    path.write_text(
        "created_at_utc,status,mode\n"
        "2026-05-21T10:00:00+00:00,accepted,demo\n",
        encoding="utf-8",
    )

    append_journal_event(
        path,
        {
            "created_at_utc": "2026-05-21T11:00:00+00:00",
            "mode": "demo",
            "status": "sent",
        },
    )

    frame = read_journal(path)

    assert list(frame.columns) == JOURNAL_COLUMNS
    assert len(frame) == 2


def test_count_daily_test_orders_counts_only_accepted_or_sent_rows(tmp_path) -> None:
    path = tmp_path / "execution_journal.csv"
    append_journal_event(path, {"created_at_utc": "2026-05-21T10:00:00+00:00", "mode": "demo", "status": " Accepted "})
    append_journal_event(path, {"created_at_utc": "2026-05-21T11:00:00+00:00", "mode": "demo", "status": " Sent "})
    append_journal_event(path, {"created_at_utc": "2026-05-21T12:00:00+00:00", "mode": "demo", "status": "rejected"})
    append_journal_event(path, {"created_at_utc": "2026-05-21T13:00:00+00:00", "mode": "paper", "status": "accepted"})
    append_journal_event(path, {"created_at_utc": "2026-05-20T12:00:00+00:00", "mode": "demo", "status": "accepted"})

    assert count_daily_test_orders(path, date(2026, 5, 21)) == 2


def test_count_daily_test_orders_deduplicates_lifecycle_rows_by_event_id(tmp_path) -> None:
    path = tmp_path / "execution_journal.csv"
    append_journal_event(
        path,
        {
            "created_at_utc": "2026-05-21T10:00:00+00:00",
            "event_id": "event-sent",
            "order_link_id": "order-sent",
            "mode": "demo",
            "status": "accepted",
        },
    )
    append_journal_event(
        path,
        {
            "created_at_utc": "2026-05-21T10:00:01+00:00",
            "event_id": "event-sent",
            "order_link_id": "order-sent",
            "mode": "demo",
            "status": "sent",
        },
    )
    append_journal_event(
        path,
        {
            "created_at_utc": "2026-05-21T11:00:00+00:00",
            "event_id": "event-error",
            "order_link_id": "order-error",
            "mode": "demo",
            "status": "accepted",
        },
    )
    append_journal_event(
        path,
        {
            "created_at_utc": "2026-05-21T11:00:01+00:00",
            "event_id": "event-error",
            "order_link_id": "order-error",
            "mode": "demo",
            "status": "error",
        },
    )

    assert count_daily_test_orders(path, date(2026, 5, 21)) == 2


def test_count_daily_test_orders_ignores_malformed_timestamps(tmp_path) -> None:
    path = tmp_path / "execution_journal.csv"
    append_journal_event(path, {"created_at_utc": "not-a-date", "mode": "demo", "status": "accepted"})
    append_journal_event(path, {"created_at_utc": "2026-05-21T10:00:00+00:00", "mode": "demo", "status": "accepted"})

    assert count_daily_test_orders(path, date(2026, 5, 21)) == 1


def test_read_journal_empty_existing_file_returns_empty_frame_with_columns(tmp_path) -> None:
    path = tmp_path / "execution_journal.csv"
    path.touch()

    frame = read_journal(path)

    assert frame.empty
    assert list(frame.columns) == JOURNAL_COLUMNS


def test_count_daily_test_orders_empty_existing_file_returns_zero(tmp_path) -> None:
    path = tmp_path / "execution_journal.csv"
    path.touch()

    assert count_daily_test_orders(path, date(2026, 5, 21)) == 0


def test_read_journal_drops_extra_columns_from_existing_csv(tmp_path) -> None:
    path = tmp_path / "execution_journal.csv"
    path.write_text(
        "created_at_utc,status,mode,api_secret\n"
        "2026-05-21T10:00:00+00:00,accepted,demo,must-not-leak\n",
        encoding="utf-8",
    )

    frame = read_journal(path)

    assert list(frame.columns) == JOURNAL_COLUMNS
    assert "api_secret" not in frame.columns


def test_read_journal_adds_missing_columns_from_existing_csv(tmp_path) -> None:
    path = tmp_path / "execution_journal.csv"
    path.write_text(
        "created_at_utc,status,mode\n"
        "2026-05-21T10:00:00+00:00,accepted,demo\n",
        encoding="utf-8",
    )

    frame = read_journal(path)

    assert list(frame.columns) == JOURNAL_COLUMNS
    assert "event_id" in frame.columns
    assert "raw_response_path" in frame.columns


def test_read_journal_missing_file_returns_empty_frame(tmp_path) -> None:
    frame = read_journal(tmp_path / "missing.csv")

    assert frame.empty
    assert list(frame.columns) == JOURNAL_COLUMNS


def test_read_journal_tail_returns_newest_rows_first_and_drops_extra_columns(tmp_path) -> None:
    path = tmp_path / "execution_journal.csv"
    path.write_text(
        "created_at_utc,event_id,status,mode,api_secret\n"
        "2026-05-21T10:00:00+00:00,event-1,accepted,demo,old-secret\n"
        "2026-05-21T10:01:00+00:00,event-2,sent,demo,must-not-leak\n"
        "2026-05-21T10:02:00+00:00,event-3,rejected,demo,new-secret\n",
        encoding="utf-8",
    )

    frame = journal_module.read_journal_tail(path, 2)

    assert list(frame.columns) == JOURNAL_COLUMNS
    assert list(frame["event_id"]) == ["event-3", "event-2"]
    assert "api_secret" not in frame.columns
    assert "must-not-leak" not in str(frame.to_dict(orient="records"))


def test_read_journal_tail_handles_limit_one(tmp_path) -> None:
    path = tmp_path / "execution_journal.csv"
    append_journal_event(path, {"created_at_utc": "2026-05-21T10:00:00+00:00", "event_id": "event-1"})
    append_journal_event(path, {"created_at_utc": "2026-05-21T10:01:00+00:00", "event_id": "event-2"})

    frame = journal_module.read_journal_tail(path, 1)

    assert len(frame) == 1
    assert frame.loc[0, "event_id"] == "event-2"


def test_read_journal_tail_missing_file_returns_empty_frame(tmp_path) -> None:
    frame = journal_module.read_journal_tail(tmp_path / "missing.csv", 50)

    assert frame.empty
    assert list(frame.columns) == JOURNAL_COLUMNS
