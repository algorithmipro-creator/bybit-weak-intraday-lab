from __future__ import annotations

from pathlib import Path

import pandas as pd

from bybit_weak_intraday.signals.journal import (
    DECISION_JOURNAL_COLUMNS,
    append_decision_event,
    read_decision_journal,
    read_decision_journal_tail,
)


def test_append_decision_event_creates_stable_csv(tmp_path: Path) -> None:
    path = tmp_path / "signal_decisions.csv"

    append_decision_event(
        path,
        {
            "created_at_utc": "2026-05-22T18:00:00+00:00",
            "decision_id": "dec-1",
            "job_id": "job-1",
            "symbol": "ENAUSDT",
            "mode": "weak",
            "score": 10,
            "status": "qualified",
            "reason": "qualified",
        },
    )

    frame = read_decision_journal(path)
    assert list(frame.columns) == DECISION_JOURNAL_COLUMNS
    assert frame.loc[0, "decision_id"] == "dec-1"
    assert frame.loc[0, "symbol"] == "ENAUSDT"
    assert frame.loc[0, "status"] == "qualified"
    assert frame.loc[0, "telegram_status"] == ""


def test_read_decision_journal_handles_missing_empty_and_malformed_files(tmp_path: Path) -> None:
    missing = read_decision_journal(tmp_path / "missing.csv")
    assert missing.empty
    assert list(missing.columns) == DECISION_JOURNAL_COLUMNS

    empty_path = tmp_path / "empty.csv"
    empty_path.write_text("", encoding="utf-8")
    assert read_decision_journal(empty_path).empty

    bad_path = tmp_path / "bad.csv"
    bad_path.write_bytes(b"\xff\xfe\x00")
    assert read_decision_journal(bad_path).empty


def test_read_decision_journal_normalizes_old_columns(tmp_path: Path) -> None:
    path = tmp_path / "old.csv"
    pd.DataFrame([{"decision_id": "dec-1", "extra": "drop-me"}]).to_csv(path, index=False)

    frame = read_decision_journal(path)

    assert list(frame.columns) == DECISION_JOURNAL_COLUMNS
    assert frame.loc[0, "decision_id"] == "dec-1"
    assert "extra" not in frame.columns


def test_append_decision_event_normalizes_existing_old_column_file(tmp_path: Path) -> None:
    path = tmp_path / "old.csv"
    pd.DataFrame([{"decision_id": "dec-1", "extra": "drop-me"}]).to_csv(path, index=False)

    append_decision_event(path, {"decision_id": "dec-2", "symbol": "ENAUSDT"})

    frame = read_decision_journal(path)
    assert list(frame.columns) == DECISION_JOURNAL_COLUMNS
    assert list(frame["decision_id"]) == ["dec-1", "dec-2"]
    assert frame.loc[1, "symbol"] == "ENAUSDT"


def test_read_decision_journal_tail_returns_newest_first(tmp_path: Path) -> None:
    path = tmp_path / "signal_decisions.csv"
    append_decision_event(path, {"decision_id": "dec-1", "created_at_utc": "2026-05-22T18:00:00+00:00"})
    append_decision_event(path, {"decision_id": "dec-2", "created_at_utc": "2026-05-22T18:01:00+00:00"})

    frame = read_decision_journal_tail(path, 1)

    assert list(frame["decision_id"]) == ["dec-2"]
    assert list(frame.columns) == DECISION_JOURNAL_COLUMNS
