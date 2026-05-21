from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

JOURNAL_COLUMNS = [
    "created_at_utc",
    "event_id",
    "order_link_id",
    "mode",
    "symbol",
    "side",
    "category",
    "requested_notional_usdt",
    "qty",
    "take_profit",
    "stop_loss",
    "status",
    "reason",
    "bybit_ret_code",
    "bybit_ret_msg",
    "raw_response_path",
]

COUNTED_ORDER_STATUSES = {"accepted", "sent"}


def _row_from_event(event: dict[str, Any]) -> dict[str, Any]:
    return {column: event.get(column, "") for column in JOURNAL_COLUMNS}


def append_journal_event(path: str | Path, event: dict[str, Any]) -> None:
    journal_path = Path(path)
    journal_path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not journal_path.exists() or journal_path.stat().st_size == 0
    row = pd.DataFrame([_row_from_event(event)], columns=JOURNAL_COLUMNS)
    row.to_csv(journal_path, mode="a", header=write_header, index=False)


def read_journal(path: str | Path) -> pd.DataFrame:
    journal_path = Path(path)
    if not journal_path.exists():
        return pd.DataFrame(columns=JOURNAL_COLUMNS)
    if journal_path.stat().st_size == 0:
        return pd.DataFrame(columns=JOURNAL_COLUMNS)
    try:
        frame = pd.read_csv(journal_path)
    except pd.errors.EmptyDataError:
        return pd.DataFrame(columns=JOURNAL_COLUMNS)
    return frame.reindex(columns=JOURNAL_COLUMNS)


def count_daily_test_orders(path: str | Path, day: date) -> int:
    frame = read_journal(path)
    if (
        frame.empty
        or "created_at_utc" not in frame.columns
        or "status" not in frame.columns
        or "mode" not in frame.columns
    ):
        return 0
    created = pd.to_datetime(frame["created_at_utc"], errors="coerce", utc=True, format="ISO8601")
    statuses = frame["status"].astype(str).str.strip().str.lower()
    modes = frame["mode"].astype(str).str.strip().str.lower()
    mask = (created.dt.date == day) & statuses.isin(COUNTED_ORDER_STATUSES) & (modes == "demo")
    return int(mask.sum())
