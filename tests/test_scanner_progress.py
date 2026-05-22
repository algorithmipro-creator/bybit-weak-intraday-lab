from __future__ import annotations

import datetime as dt
from pathlib import Path

import pandas as pd

import bybit_weak_intraday.scanner as scanner
from bybit_weak_intraday.archive import ArchiveDownloadResult
from bybit_weak_intraday.scanner import run_archive_scan


def test_run_archive_scan_emits_progress_and_continues_on_missing_archive(monkeypatch, tmp_path: Path) -> None:
    events: list[dict] = []
    download_calls: list[tuple[str, dt.date]] = []

    def fake_download(_sess, symbol, day, _cache, sleep=0.15):
        download_calls.append((symbol, day))
        if day == dt.date(2026, 3, 17):
            return ArchiveDownloadResult(path=None, status="missing")
        return ArchiveDownloadResult(path=Path(f"{symbol}-{day}.csv.gz"), status="cache_hit")

    monkeypatch.setattr(scanner, "download_archive_file_result", fake_download)
    monkeypatch.setattr(scanner, "load_archive_ticks", lambda path: pd.DataFrame())
    monkeypatch.setattr(scanner, "score_symbol_day", lambda *args, **kwargs: ({}, None))

    metrics, trades = run_archive_scan(
        start="2026-03-18",
        end="2026-03-18",
        symbols=["enausdt"],
        cache_dir=tmp_path,
        progress_callback=events.append,
    )

    assert metrics.empty
    assert trades.empty
    assert events[-1]["processed"] == 1
    assert events[-1]["total"] == 1
    assert events[-1]["current_symbol"] == "ENAUSDT"
    assert events[-1]["current_date"] == "2026-03-18"
    assert events[-1]["cache_hits"] == 1
    assert events[-1]["missing_files"] == 1
    assert events[-1]["warnings"] == [
        {"symbol": "ENAUSDT", "date": "2026-03-18", "message": "archive file missing"}
    ]


def test_run_archive_scan_emits_progress_for_parse_error(monkeypatch, tmp_path: Path) -> None:
    events: list[dict] = []

    def fake_download(_sess, symbol, day, _cache, sleep=0.15):
        return ArchiveDownloadResult(path=Path(f"{symbol}-{day}.csv.gz"), status="downloaded")

    monkeypatch.setattr(scanner, "download_archive_file_result", fake_download)
    monkeypatch.setattr(scanner, "load_archive_ticks", lambda path: (_ for _ in ()).throw(ValueError("bad csv")))

    metrics, trades = run_archive_scan(
        start="2026-03-18",
        end="2026-03-18",
        symbols=["ENAUSDT"],
        cache_dir=tmp_path,
        progress_callback=events.append,
    )

    assert trades.empty
    assert metrics.loc[0, "error"] == "bad csv"
    assert events[-1]["errors"] == 1
    assert events[-1]["warnings"] == [
        {"symbol": "ENAUSDT", "date": "2026-03-18", "message": "bad csv"}
    ]
