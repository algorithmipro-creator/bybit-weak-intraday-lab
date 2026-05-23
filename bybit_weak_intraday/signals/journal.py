from __future__ import annotations

import csv
from collections import deque
from pathlib import Path
from typing import Any

import pandas as pd

DECISION_JOURNAL_COLUMNS = [
    "created_at_utc",
    "decision_id",
    "job_id",
    "job_type",
    "symbol",
    "mode",
    "score",
    "status",
    "reason",
    "side",
    "notional_usdt",
    "take_profit_pct",
    "stop_loss_pct",
    "candidate_price",
    "candidate_time_utc",
    "order_link_id",
    "execution_status",
    "telegram_status",
    "telegram_error",
    "details",
]


def _empty_decision_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=DECISION_JOURNAL_COLUMNS)


def _row_from_event(event: dict[str, Any]) -> dict[str, Any]:
    return {column: event.get(column, "") for column in DECISION_JOURNAL_COLUMNS}


def _normalize_existing_journal_for_append(journal_path: Path) -> None:
    try:
        frame = pd.read_csv(journal_path)
    except (OSError, UnicodeDecodeError, pd.errors.EmptyDataError, pd.errors.ParserError):
        _empty_decision_frame().to_csv(journal_path, index=False)
        return
    if list(frame.columns) != DECISION_JOURNAL_COLUMNS:
        frame.reindex(columns=DECISION_JOURNAL_COLUMNS).fillna("").to_csv(journal_path, index=False)


def append_decision_event(path: str | Path, event: dict[str, Any]) -> None:
    journal_path = Path(path)
    journal_path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not journal_path.exists() or journal_path.stat().st_size == 0
    if not write_header:
        _normalize_existing_journal_for_append(journal_path)
    row = pd.DataFrame([_row_from_event(event)], columns=DECISION_JOURNAL_COLUMNS)
    row.to_csv(journal_path, mode="a", header=write_header, index=False)


def read_decision_journal(path: str | Path) -> pd.DataFrame:
    journal_path = Path(path)
    try:
        if not journal_path.exists() or journal_path.stat().st_size == 0:
            return _empty_decision_frame()
        frame = pd.read_csv(journal_path)
    except (OSError, UnicodeDecodeError, pd.errors.EmptyDataError, pd.errors.ParserError):
        return _empty_decision_frame()
    return frame.reindex(columns=DECISION_JOURNAL_COLUMNS).fillna("")


def read_decision_journal_tail(path: str | Path, limit: int) -> pd.DataFrame:
    journal_path = Path(path)
    clamped_limit = max(1, int(limit))
    if not journal_path.exists() or journal_path.stat().st_size == 0:
        return _empty_decision_frame()
    try:
        with journal_path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = deque(csv.DictReader(handle), maxlen=clamped_limit)
    except (csv.Error, OSError, UnicodeDecodeError):
        return _empty_decision_frame()
    if not rows:
        return _empty_decision_frame()
    frame = pd.DataFrame(list(reversed(rows)))
    return frame.reindex(columns=DECISION_JOURNAL_COLUMNS).fillna("").reset_index(drop=True)
