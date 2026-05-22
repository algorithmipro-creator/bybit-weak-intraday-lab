from __future__ import annotations

from pathlib import Path

from bybit_weak_intraday.archive import ArchiveDownloadResult
from bybit_weak_intraday.progress import ProgressState


def test_progress_state_counts_archive_results_and_emits_event() -> None:
    state = ProgressState(total=4)
    state.add_archive_result(ArchiveDownloadResult(path=Path("a.csv.gz"), status="cache_hit"))
    state.add_archive_result(ArchiveDownloadResult(path=Path("b.csv.gz"), status="downloaded"))
    state.add_archive_result(ArchiveDownloadResult(path=None, status="missing"))
    state.add_archive_result(ArchiveDownloadResult(path=None, status="error", error="network down"))

    event = state.advance("ENAUSDT", "2026-03-18")

    assert event == {
        "processed": 1,
        "total": 4,
        "current_symbol": "ENAUSDT",
        "current_date": "2026-03-18",
        "cache_hits": 1,
        "downloads": 1,
        "missing_files": 1,
        "errors": 1,
        "message": "scanning ENAUSDT 2026-03-18",
    }


def test_progress_state_builds_warnings_from_download_results() -> None:
    state = ProgressState(total=1)

    warnings = state.warnings_for_results(
        "GRASSUSDT",
        "2026-03-25",
        [
            ArchiveDownloadResult(path=None, status="missing"),
            ArchiveDownloadResult(path=None, status="error", warning="locked tmp", error="HTTP 500"),
        ],
    )

    assert warnings == [
        {"symbol": "GRASSUSDT", "date": "2026-03-25", "message": "archive file missing"},
        {"symbol": "GRASSUSDT", "date": "2026-03-25", "message": "HTTP 500; locked tmp"},
    ]
