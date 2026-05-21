from __future__ import annotations

from datetime import date
from io import StringIO
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
TAIL_READ_CHUNK_BYTES = 8192


def _empty_journal_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=JOURNAL_COLUMNS)


def _row_from_event(event: dict[str, Any]) -> dict[str, Any]:
    return {column: event.get(column, "") for column in JOURNAL_COLUMNS}


def _has_canonical_header(path: Path) -> bool:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            header = handle.readline().strip()
    except OSError:
        return False
    return header.split(",") == JOURNAL_COLUMNS


def _normalize_existing_journal(path: Path) -> None:
    frame = read_journal(path)
    frame.to_csv(path, index=False)


def append_journal_event(path: str | Path, event: dict[str, Any]) -> None:
    journal_path = Path(path)
    journal_path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not journal_path.exists() or journal_path.stat().st_size == 0
    if not write_header and not _has_canonical_header(journal_path):
        _normalize_existing_journal(journal_path)
    row = pd.DataFrame([_row_from_event(event)], columns=JOURNAL_COLUMNS)
    row.to_csv(journal_path, mode="a", header=write_header, index=False)


def read_journal(path: str | Path) -> pd.DataFrame:
    journal_path = Path(path)
    if not journal_path.exists():
        return _empty_journal_frame()
    if journal_path.stat().st_size == 0:
        return _empty_journal_frame()
    try:
        frame = pd.read_csv(journal_path)
    except pd.errors.EmptyDataError:
        return _empty_journal_frame()
    return frame.reindex(columns=JOURNAL_COLUMNS)


def _tail_data_lines(path: Path, limit: int) -> list[str]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        header = handle.readline().rstrip("\r\n")
    if not header:
        return []

    with path.open("rb") as handle:
        handle.seek(0, 2)
        position = handle.tell()
        buffer = b""
        while position > 0 and buffer.count(b"\n") <= limit:
            read_size = min(TAIL_READ_CHUNK_BYTES, position)
            position -= read_size
            handle.seek(position)
            buffer = handle.read(read_size) + buffer

    lines = buffer.splitlines()
    if position > 0 and lines:
        lines = lines[1:]
    elif lines:
        lines = lines[1:]
    return [line.decode("utf-8") for line in lines[-limit:]]


def read_journal_tail(path: str | Path, limit: int) -> pd.DataFrame:
    journal_path = Path(path)
    clamped_limit = max(1, int(limit))
    if not journal_path.exists():
        return _empty_journal_frame()
    if journal_path.stat().st_size == 0:
        return _empty_journal_frame()

    with journal_path.open("r", encoding="utf-8-sig", newline="") as handle:
        header = handle.readline().rstrip("\r\n")
    if not header:
        return _empty_journal_frame()

    data_lines = _tail_data_lines(journal_path, clamped_limit)
    if not data_lines:
        return _empty_journal_frame()

    csv_text = header + "\n" + "\n".join(data_lines)
    try:
        frame = pd.read_csv(StringIO(csv_text))
    except pd.errors.EmptyDataError:
        return _empty_journal_frame()
    return frame.reindex(columns=JOURNAL_COLUMNS).iloc[::-1].reset_index(drop=True)


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
    counted = frame.loc[mask]
    if counted.empty:
        return 0

    keyed_attempts: set[tuple[str, str]] = set()
    legacy_rows = 0
    for _, row in counted.iterrows():
        event_id = "" if pd.isna(row["event_id"]) else str(row["event_id"]).strip()
        order_link_id = "" if pd.isna(row["order_link_id"]) else str(row["order_link_id"]).strip()
        if event_id:
            keyed_attempts.add(("event_id", event_id))
        elif order_link_id:
            keyed_attempts.add(("order_link_id", order_link_id))
        else:
            legacy_rows += 1
    return len(keyed_attempts) + legacy_rows
