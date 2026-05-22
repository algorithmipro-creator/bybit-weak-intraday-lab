# Stable Scanner Job Lifecycle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make archive scanner jobs resilient to cache temp-file conflicts and show live progress, cache stats, and warnings in the Scanner Jobs UI.

**Architecture:** Add a small archive download result API, a shared progress state helper, scanner progress callbacks, job-store persistence, and a Streamlit progress panel. Keep job state in existing `meta.json` files and preserve current CSV outputs.

**Tech Stack:** Python 3.12, pandas, requests, FastAPI, Streamlit, pytest, file-based job metadata.

---

## Scope Check

This plan implements one connected subsystem: stable scanner job lifecycle. It touches downloader reliability, scanner progress emission, backend metadata persistence, and the existing Scanner Jobs screen. Demo execution and strategy logic are intentionally out of scope.

## File Map

- Modify `bybit_weak_intraday/archive.py`: add structured download result, unique temp paths, safe cleanup, and compatibility wrapper.
- Create `bybit_weak_intraday/progress.py`: shared progress state and event formatting for scanner jobs.
- Modify `bybit_weak_intraday/scanner.py`: emit progress and warnings for archive scan work units.
- Modify `bybit_weak_intraday/causal_scanner.py`: emit progress and warnings for causal scan work units.
- Modify `bybit_weak_intraday/optimizer.py`: translate nested scan progress into TP/SL optimizer progress.
- Modify `backend/app/job_store.py`: initialize, merge, and persist job progress and warnings.
- Modify `ui/streamlit_app.py`: render progress bar, current work, cache counters, and warnings in `Active Job`.
- Create `tests/test_archive.py`: downloader reliability tests.
- Create `tests/test_progress.py`: shared progress state tests.
- Create `tests/test_scanner_progress.py`: regular scanner callback tests.
- Modify `tests/test_causal_scanner.py`: causal scanner callback tests.
- Modify `tests/test_optimizer.py`: optimizer callback tests.
- Modify `tests/test_backend_api.py`: job-store progress persistence tests.
- Modify `tests/test_streamlit_demo_execution_helpers.py`: source-level UI progress tests.

## Task 1: Reliable Archive Download Result

**Files:**
- Modify: `bybit_weak_intraday/archive.py`
- Create: `tests/test_archive.py`

- [ ] **Step 1: Write failing downloader tests**

Create `tests/test_archive.py`:

```python
from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from bybit_weak_intraday import archive
from bybit_weak_intraday.archive import download_archive_file, download_archive_file_result


class FakeResponse:
    def __init__(self, *, status_code: int = 200, chunks: list[bytes] | None = None):
        self.status_code = status_code
        self._chunks = chunks or [b"timestamp,symbol,side,size,price,foreignNotional\n"]

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def iter_content(self, chunk_size: int):
        yield from self._chunks


class FakeSession:
    def __init__(self, response: FakeResponse):
        self.response = response
        self.calls = []

    def get(self, url: str, *, stream: bool, timeout: int):
        self.calls.append({"url": url, "stream": stream, "timeout": timeout})
        return self.response


def test_download_archive_file_result_reports_cache_hit_without_network(tmp_path: Path) -> None:
    out = archive.cache_path(tmp_path, "ENAUSDT", dt.date(2026, 3, 18))
    out.parent.mkdir(parents=True)
    out.write_bytes(b"cached")
    session = FakeSession(FakeResponse())

    result = download_archive_file_result(session, "ENAUSDT", dt.date(2026, 3, 18), tmp_path, sleep=0)

    assert result.path == out
    assert result.status == "cache_hit"
    assert result.warning is None
    assert result.error is None
    assert session.calls == []


def test_download_archive_file_result_uses_unique_temp_paths(monkeypatch, tmp_path: Path) -> None:
    generated: list[Path] = []

    def fake_tmp_path(out: Path) -> Path:
        tmp = out.with_name(f"{out.name}.{len(generated)}.tmp")
        generated.append(tmp)
        return tmp

    monkeypatch.setattr(archive, "_unique_tmp_path", fake_tmp_path)
    session = FakeSession(FakeResponse(chunks=[b"abc"]))

    first = download_archive_file_result(session, "ENAUSDT", dt.date(2026, 3, 18), tmp_path, sleep=0)
    out = archive.cache_path(tmp_path, "ENAUSDT", dt.date(2026, 3, 18))
    out.unlink()
    second = download_archive_file_result(session, "ENAUSDT", dt.date(2026, 3, 18), tmp_path, sleep=0)

    assert first.status == "downloaded"
    assert second.status == "downloaded"
    assert generated[0] != generated[1]
    assert all(not path.exists() for path in generated)


def test_download_archive_file_result_reports_missing_on_404(tmp_path: Path) -> None:
    result = download_archive_file_result(
        FakeSession(FakeResponse(status_code=404)),
        "ENAUSDT",
        dt.date(2026, 3, 18),
        tmp_path,
        sleep=0,
    )

    assert result.path is None
    assert result.status == "missing"
    assert result.error is None


def test_download_archive_file_result_does_not_fail_on_temp_cleanup_error(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(archive, "_safe_unlink", lambda path: "locked temp file")

    result = download_archive_file_result(
        FakeSession(FakeResponse(status_code=500)),
        "ENAUSDT",
        dt.date(2026, 3, 18),
        tmp_path,
        retries=1,
        sleep=0,
    )

    assert result.path is None
    assert result.status == "error"
    assert result.warning == "locked temp file"
    assert "HTTP 500" in str(result.error)


def test_download_archive_file_keeps_path_or_none_compatibility(tmp_path: Path) -> None:
    path = download_archive_file(
        FakeSession(FakeResponse(chunks=[b"abc"])),
        "ENAUSDT",
        dt.date(2026, 3, 18),
        tmp_path,
        sleep=0,
    )

    assert path == archive.cache_path(tmp_path, "ENAUSDT", dt.date(2026, 3, 18))
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m pytest tests/test_archive.py -q
```

Expected: FAIL because `download_archive_file_result`, `_unique_tmp_path`, and structured result fields do not exist.

- [ ] **Step 3: Implement structured downloader**

In `bybit_weak_intraday/archive.py`, add imports:

```python
import os
import threading
import uuid
from dataclasses import dataclass
```

Add this dataclass and helpers above `download_archive_file()`:

```python
@dataclass(frozen=True)
class ArchiveDownloadResult:
    path: Path | None
    status: str
    warning: str | None = None
    error: str | None = None


def _unique_tmp_path(out: Path) -> Path:
    suffix = f"{os.getpid()}.{threading.get_ident()}.{uuid.uuid4().hex}.tmp"
    return out.with_name(f"{out.name}.{suffix}")


def _safe_unlink(path: Path) -> str | None:
    try:
        path.unlink(missing_ok=True)
        return None
    except OSError as exc:
        return str(exc)
```

Replace `download_archive_file()` with this compatibility wrapper plus new result function:

```python
def download_archive_file_result(
    sess: requests.Session,
    symbol: str,
    day: dt.date,
    cache_dir: Path,
    retries: int = 3,
    sleep: float = 0.15,
) -> ArchiveDownloadResult:
    """Download one Bybit public archive file into cache and report cache/download status."""
    out = cache_path(cache_dir, symbol, day)
    if out.exists() and out.stat().st_size > 0:
        return ArchiveDownloadResult(path=out, status="cache_hit")

    out.parent.mkdir(parents=True, exist_ok=True)
    url = archive_url(symbol, day)
    last_warning: str | None = None

    for attempt in range(retries):
        tmp = _unique_tmp_path(out)
        try:
            if out.exists() and out.stat().st_size > 0:
                return ArchiveDownloadResult(path=out, status="cache_hit")

            r = sess.get(url, stream=True, timeout=60)
            if r.status_code == 404:
                return ArchiveDownloadResult(path=None, status="missing")
            r.raise_for_status()

            with open(tmp, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        f.write(chunk)

            if out.exists() and out.stat().st_size > 0:
                cleanup_warning = _safe_unlink(tmp)
                return ArchiveDownloadResult(path=out, status="cache_hit", warning=cleanup_warning)

            tmp.replace(out)
            time.sleep(sleep)
            return ArchiveDownloadResult(path=out, status="downloaded")
        except Exception as exc:
            cleanup_warning = _safe_unlink(tmp)
            last_warning = cleanup_warning or last_warning
            if attempt == retries - 1:
                return ArchiveDownloadResult(path=None, status="error", warning=last_warning, error=str(exc))
            time.sleep(1 + attempt)

    return ArchiveDownloadResult(path=None, status="error", warning=last_warning, error="download retries exhausted")


def download_archive_file(
    sess: requests.Session,
    symbol: str,
    day: dt.date,
    cache_dir: Path,
    retries: int = 3,
    sleep: float = 0.15,
) -> Path | None:
    """Download one Bybit public archive file into cache; return path or None."""
    return download_archive_file_result(
        sess,
        symbol,
        day,
        cache_dir,
        retries=retries,
        sleep=sleep,
    ).path
```

- [ ] **Step 4: Run downloader tests**

Run:

```powershell
python -m pytest tests/test_archive.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit downloader work**

Run:

```powershell
git add bybit_weak_intraday/archive.py tests/test_archive.py
git commit -m "fix: make archive downloads cache-lock resilient"
```

## Task 2: Shared Progress State

**Files:**
- Create: `bybit_weak_intraday/progress.py`
- Create: `tests/test_progress.py`

- [ ] **Step 1: Write failing progress tests**

Create `tests/test_progress.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m pytest tests/test_progress.py -q
```

Expected: FAIL because `bybit_weak_intraday.progress` does not exist.

- [ ] **Step 3: Implement progress helper**

Create `bybit_weak_intraday/progress.py`:

```python
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .archive import ArchiveDownloadResult

ProgressCallback = Callable[[dict[str, Any]], None]


@dataclass
class ProgressState:
    total: int
    processed: int = 0
    cache_hits: int = 0
    downloads: int = 0
    missing_files: int = 0
    errors: int = 0

    def add_archive_result(self, result: ArchiveDownloadResult) -> None:
        if result.status == "cache_hit":
            self.cache_hits += 1
        elif result.status == "downloaded":
            self.downloads += 1
        elif result.status == "missing":
            self.missing_files += 1
        elif result.status == "error":
            self.errors += 1

    def advance(self, symbol: str, date: str, *, message: str | None = None) -> dict[str, Any]:
        self.processed += 1
        status_message = message or f"scanning {symbol} {date}"
        return {
            "processed": self.processed,
            "total": self.total,
            "current_symbol": symbol,
            "current_date": date,
            "cache_hits": self.cache_hits,
            "downloads": self.downloads,
            "missing_files": self.missing_files,
            "errors": self.errors,
            "message": status_message,
        }

    def warnings_for_results(
        self,
        symbol: str,
        date: str,
        results: list[ArchiveDownloadResult],
    ) -> list[dict[str, str]]:
        warnings: list[dict[str, str]] = []
        for result in results:
            if result.status == "missing":
                warnings.append({"symbol": symbol, "date": date, "message": "archive file missing"})
            elif result.status == "error":
                message = result.error or "archive download failed"
                if result.warning:
                    message = f"{message}; {result.warning}"
                warnings.append({"symbol": symbol, "date": date, "message": message})
            elif result.warning:
                warnings.append({"symbol": symbol, "date": date, "message": result.warning})
        return warnings
```

- [ ] **Step 4: Run progress tests**

Run:

```powershell
python -m pytest tests/test_progress.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit progress helper**

Run:

```powershell
git add bybit_weak_intraday/progress.py tests/test_progress.py
git commit -m "feat: add scanner progress state helper"
```

## Task 3: Regular Archive Scan Progress

**Files:**
- Modify: `bybit_weak_intraday/scanner.py`
- Create: `tests/test_scanner_progress.py`

- [ ] **Step 1: Write failing regular scanner progress tests**

Create `tests/test_scanner_progress.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m pytest tests/test_scanner_progress.py -q
```

Expected: FAIL because `run_archive_scan()` does not accept `progress_callback` and `scanner.download_archive_file_result` is not imported.

- [ ] **Step 3: Implement regular scan progress**

In `bybit_weak_intraday/scanner.py`:

Change imports:

```python
from typing import Iterable

from .archive import date_range, download_archive_file_result, get_archive_universe, http_session, load_archive_ticks, parse_date
from .progress import ProgressCallback, ProgressState
```

Add `progress_callback` to `run_archive_scan()`:

```python
    progress_callback: ProgressCallback | None = None,
```

After `symbol_list` is finalized, initialize:

```python
    progress = ProgressState(total=len(symbol_list) * len(days))
```

Inside the nested loop, replace `download_archive_file()` calls with:

```python
            cur_result = download_archive_file_result(sess, sym, day, cache, sleep=sleep)
            prev_result = download_archive_file_result(sess, sym, prev, cache, sleep=sleep)
            for result in (cur_result, prev_result):
                progress.add_archive_result(result)
            warnings = progress.warnings_for_results(sym, str(day), [cur_result, prev_result])
            if cur_result.path is None or prev_result.path is None:
                event = progress.advance(sym, str(day))
                if warnings:
                    event["warnings"] = warnings
                if progress_callback:
                    progress_callback(event)
                continue
```

In the `try` success branch, emit:

```python
                event = progress.advance(sym, str(day))
                if warnings:
                    event["warnings"] = warnings
                if progress_callback:
                    progress_callback(event)
```

In the `except Exception as exc` branch, increment errors and emit:

```python
                metrics.append({"date": str(day), "symbol": sym, "error": str(exc)})
                progress.errors += 1
                warnings.append({"symbol": sym, "date": str(day), "message": str(exc)})
                event = progress.advance(sym, str(day))
                event["warnings"] = warnings
                if progress_callback:
                    progress_callback(event)
```

- [ ] **Step 4: Run regular scanner tests**

Run:

```powershell
python -m pytest tests/test_scanner_progress.py -q
```

Expected: PASS.

- [ ] **Step 5: Run existing causal and optimizer tests for import compatibility**

Run:

```powershell
python -m pytest tests/test_causal_scanner.py tests/test_optimizer.py -q
```

Expected: PASS or targeted failures only where old monkeypatches still patch `download_archive_file`. If old monkeypatch failures occur, Task 4 updates causal scanner tests and imports.

- [ ] **Step 6: Commit regular scanner progress**

Run:

```powershell
git add bybit_weak_intraday/scanner.py tests/test_scanner_progress.py
git commit -m "feat: emit regular scan progress"
```

## Task 4: Causal Scan Progress

**Files:**
- Modify: `bybit_weak_intraday/causal_scanner.py`
- Modify: `tests/test_causal_scanner.py`

- [ ] **Step 1: Write failing causal progress test**

Append to `tests/test_causal_scanner.py`:

```python
def test_run_archive_causal_scan_outputs_emits_progress_for_missing_archive(monkeypatch, tmp_path):
    events: list[dict] = []

    def fake_download(_sess, symbol, day, _cache, sleep=0.15):
        if str(day) == "2026-03-17":
            return scanner.ArchiveDownloadResult(path=None, status="missing")
        return scanner.ArchiveDownloadResult(path=tmp_path / f"{symbol}-{day}.csv.gz", status="cache_hit")

    monkeypatch.setattr(scanner, "download_archive_file_result", fake_download)
    monkeypatch.setattr(scanner, "load_archive_ticks", lambda path: pd.DataFrame())
    monkeypatch.setattr(scanner, "find_causal_signals", lambda *args, **kwargs: [])

    signals, evaluations = run_archive_causal_scan_outputs(
        start="2026-03-18",
        end="2026-03-18",
        symbols=["testusdt"],
        cache_dir=tmp_path,
        progress_callback=events.append,
    )

    assert signals.empty
    assert evaluations.empty
    assert events[-1]["processed"] == 1
    assert events[-1]["total"] == 1
    assert events[-1]["current_symbol"] == "TESTUSDT"
    assert events[-1]["missing_files"] == 1
    assert events[-1]["warnings"] == [
        {"symbol": "TESTUSDT", "date": "2026-03-18", "message": "archive file missing"}
    ]
```

Also update existing `test_run_archive_causal_scan_outputs_returns_signals_and_evaluations()` fake downloader to return `ArchiveDownloadResult`:

```python
    def fake_download(_sess, symbol, day, _cache, sleep=0.15):
        return scanner.ArchiveDownloadResult(path=f"{symbol}-{day}", status="cache_hit")
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m pytest tests/test_causal_scanner.py::test_run_archive_causal_scan_outputs_emits_progress_for_missing_archive -q
```

Expected: FAIL because causal scanner does not expose `ArchiveDownloadResult`, `download_archive_file_result`, or `progress_callback`.

- [ ] **Step 3: Implement causal scan progress**

In `bybit_weak_intraday/causal_scanner.py`:

Change imports:

```python
from .archive import (
    ArchiveDownloadResult,
    date_range,
    download_archive_file_result,
    get_archive_universe,
    http_session,
    load_archive_ticks,
    parse_date,
)
from .progress import ProgressCallback, ProgressState
```

Add `progress_callback` to both `run_archive_causal_scan()` and `run_archive_causal_scan_outputs()`:

```python
    progress_callback: ProgressCallback | None = None,
```

Pass it through from `run_archive_causal_scan()`:

```python
        progress_callback=progress_callback,
```

In `run_archive_causal_scan_outputs()`, initialize after `symbol_list` is finalized:

```python
    progress = ProgressState(total=len(symbol_list) * len(days))
```

Replace download calls and emit using the same structure as regular scan:

```python
            cur_result = download_archive_file_result(sess, sym, day, cache, sleep=sleep)
            prev_result = download_archive_file_result(sess, sym, prev, cache, sleep=sleep)
            for result in (cur_result, prev_result):
                progress.add_archive_result(result)
            warnings = progress.warnings_for_results(sym, str(day), [cur_result, prev_result])
            if cur_result.path is None or prev_result.path is None:
                event = progress.advance(sym, str(day))
                if warnings:
                    event["warnings"] = warnings
                if progress_callback:
                    progress_callback(event)
                continue
```

In success and exception branches, emit the same event shape. In the exception branch, also append the existing `error_rows` row and increment `progress.errors`.

- [ ] **Step 4: Run causal tests**

Run:

```powershell
python -m pytest tests/test_causal_scanner.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit causal progress**

Run:

```powershell
git add bybit_weak_intraday/causal_scanner.py tests/test_causal_scanner.py
git commit -m "feat: emit causal scan progress"
```

## Task 5: TP/SL Optimizer Progress Translation

**Files:**
- Modify: `bybit_weak_intraday/optimizer.py`
- Modify: `tests/test_optimizer.py`

- [ ] **Step 1: Write failing optimizer progress test**

Append to `tests/test_optimizer.py`:

```python
def test_run_archive_tp_sl_grid_translates_nested_scan_progress(monkeypatch):
    events: list[dict] = []

    def fake_run_archive_scan(**kwargs):
        kwargs["progress_callback"](
            {
                "processed": 1,
                "total": 2,
                "current_symbol": "ENAUSDT",
                "current_date": "2026-03-18",
                "cache_hits": 1,
                "downloads": 0,
                "missing_files": 0,
                "errors": 0,
                "message": "scanning ENAUSDT 2026-03-18",
            }
        )
        return pd.DataFrame(), pd.DataFrame()

    monkeypatch.setattr("bybit_weak_intraday.optimizer.run_archive_scan", fake_run_archive_scan)

    run_archive_tp_sl_grid(
        start="2026-03-18",
        end="2026-03-19",
        symbols=["ENAUSDT"],
        tp_grid=[0.04, 0.06],
        sl_grid=[0.05],
        progress_callback=events.append,
    )

    assert events[0]["processed"] == 1
    assert events[0]["total"] == 4
    assert events[0]["grid_combo"] == "1/2"
    assert events[0]["tp_pct"] == 4.0
    assert events[0]["sl_pct"] == 5.0
    assert events[0]["message"] == "optimizing TP 4.00% / SL 5.00%: ENAUSDT 2026-03-18"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m pytest tests/test_optimizer.py::test_run_archive_tp_sl_grid_translates_nested_scan_progress -q
```

Expected: FAIL because optimizer does not accept `progress_callback`.

- [ ] **Step 3: Implement optimizer callback translation**

In `bybit_weak_intraday/optimizer.py`, import:

```python
from .archive import date_range, get_archive_universe, http_session, parse_date
from .progress import ProgressCallback
```

Add `progress_callback` to `run_archive_tp_sl_grid()`:

```python
    progress_callback: ProgressCallback | None = None,
```

Before the grid loop, compute total work:

```python
    start_date = parse_date(start) if isinstance(start, str) else start
    end_date = parse_date(end) if isinstance(end, str) else end
    days = date_range(start_date, end_date)
    if full_universe:
        symbol_list = get_archive_universe(http_session(), exclude_majors=not include_majors)
    else:
        symbol_list = [s.strip().upper() for s in (symbols or []) if s.strip()]
    if max_symbols and len(symbol_list) > max_symbols:
        symbol_list = symbol_list[:max_symbols]
    combo_total = len(tp_values) * len(sl_values)
    scan_total = len(symbol_list) * len(days)
    optimizer_total = combo_total * scan_total
    completed_before_combo = 0
```

Inside each combo, create a nested callback. Use an explicit counter because empty result combos do not append to `trade_frames`:

```python
    combo_number = 0
    for tp in tp_values:
        for sl in sl_values:
            combo_number += 1

            def _combo_progress(event: dict, *, combo_number: int = combo_number, tp: float = tp, sl: float = sl) -> None:
                if not progress_callback:
                    return
                translated = dict(event)
                translated["processed"] = completed_before_combo + int(event.get("processed") or 0)
                translated["total"] = optimizer_total
                translated["grid_combo"] = f"{combo_number}/{combo_total}"
                translated["tp_pct"] = _pct(tp)
                translated["sl_pct"] = _pct(sl)
                translated["message"] = (
                    f"optimizing TP {_pct(tp):.2f}% / SL {_pct(sl):.2f}%: "
                    f"{event.get('current_symbol') or ''} {event.get('current_date') or ''}"
                ).strip()
                progress_callback(translated)
```

Pass `symbols=symbol_list`, `full_universe=False`, and `progress_callback=_combo_progress` to `run_archive_scan()` so the already normalized symbol list is reused. Keep `include_majors` and `max_symbols` at their neutral values for that inner call because filtering already happened before the grid loop. After each combo, increment:

```python
            completed_before_combo += scan_total
```

- [ ] **Step 4: Run optimizer tests**

Run:

```powershell
python -m pytest tests/test_optimizer.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit optimizer progress**

Run:

```powershell
git add bybit_weak_intraday/optimizer.py tests/test_optimizer.py
git commit -m "feat: emit optimizer scan progress"
```

## Task 6: Persist Progress and Warnings in Job Store

**Files:**
- Modify: `backend/app/job_store.py`
- Modify: `tests/test_backend_api.py`

- [ ] **Step 1: Write failing job-store progress test**

Append to `tests/test_backend_api.py`:

```python
def test_run_job_persists_progress_and_warnings(monkeypatch, tmp_path):
    monkeypatch.setattr(job_store.settings, "jobs_dir", tmp_path)
    monkeypatch.setattr(job_store.settings, "cache_dir", tmp_path / "cache")

    job_id = job_store.create_job(_scan_payload(symbols=["ENAUSDT"]))

    def fake_run_archive_scan(**kwargs):
        kwargs["progress_callback"](
            {
                "processed": 1,
                "total": 1,
                "current_symbol": "ENAUSDT",
                "current_date": "2026-03-18",
                "cache_hits": 1,
                "downloads": 1,
                "missing_files": 0,
                "errors": 0,
                "message": "scanning ENAUSDT 2026-03-18",
                "warnings": [
                    {"symbol": "ENAUSDT", "date": "2026-03-18", "message": "locked temp cleanup skipped"}
                ],
            }
        )
        return pd.DataFrame([{"symbol": "ENAUSDT"}]), pd.DataFrame()

    monkeypatch.setattr(job_store, "run_archive_scan", fake_run_archive_scan)

    job_store.run_job(job_id)

    meta = job_store.load_meta(job_id)
    assert meta["status"] == "done"
    assert meta["progress"] == {
        "processed": 1,
        "total": 1,
        "current_symbol": "ENAUSDT",
        "current_date": "2026-03-18",
        "cache_hits": 1,
        "downloads": 1,
        "missing_files": 0,
        "errors": 0,
    }
    assert meta["message"] == "scan complete"
    assert meta["warnings"] == [
        {"symbol": "ENAUSDT", "date": "2026-03-18", "message": "locked temp cleanup skipped"}
    ]
```

Add import near the top of `tests/test_backend_api.py`:

```python
import pandas as pd
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m pytest tests/test_backend_api.py::test_run_job_persists_progress_and_warnings -q
```

Expected: FAIL because job store does not pass `progress_callback` or persist progress.

- [ ] **Step 3: Implement progress persistence**

In `backend/app/job_store.py`, add helper functions after `_strategy_config_from_request()`:

```python
PROGRESS_KEYS = {
    "processed",
    "total",
    "current_symbol",
    "current_date",
    "cache_hits",
    "downloads",
    "missing_files",
    "errors",
}


def _merge_progress_event(job_id: str, meta: dict[str, Any], event: dict[str, Any]) -> None:
    progress = {key: event.get(key) for key in PROGRESS_KEYS if key in event}
    if progress:
        meta["progress"] = progress
    if event.get("message"):
        meta["message"] = str(event["message"])
    warnings = event.get("warnings") or []
    if isinstance(warnings, list):
        existing = meta.setdefault("warnings", [])
        for warning in warnings:
            if isinstance(warning, dict) and warning not in existing:
                existing.append(warning)
    meta["updated_at"] = now_iso()
    save_meta(job_id, meta)


def _progress_callback(job_id: str, meta: dict[str, Any]):
    def _callback(event: dict[str, Any]) -> None:
        _merge_progress_event(job_id, meta, event)

    return _callback
```

In `run_job()`, initialize progress and warnings when setting running:

```python
    meta.update(
        {
            "status": "running",
            "updated_at": now_iso(),
            "message": "scan running",
            "progress": {
                "processed": 0,
                "total": 0,
                "cache_hits": 0,
                "downloads": 0,
                "missing_files": 0,
                "errors": 0,
            },
            "warnings": [],
        }
    )
```

Pass callback into each job runner. Update signatures:

```python
def _run_scan_job(job_id: str, meta: dict[str, Any], progress_callback=None) -> None:
```

Then pass:

```python
        progress_callback=progress_callback,
```

Do this for `_run_scan_job`, `_run_causal_scan_job`, and `_run_tp_sl_grid_job`.

In `run_job()`:

```python
        callback = _progress_callback(job_id, meta)
        if meta.get("job_type") == "causal_scan":
            _run_causal_scan_job(job_id, meta, progress_callback=callback)
        elif meta.get("job_type") == "tp_sl_grid":
            _run_tp_sl_grid_job(job_id, meta, progress_callback=callback)
        else:
            _run_scan_job(job_id, meta, progress_callback=callback)
```

- [ ] **Step 4: Run backend tests**

Run:

```powershell
python -m pytest tests/test_backend_api.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit job-store progress**

Run:

```powershell
git add backend/app/job_store.py tests/test_backend_api.py
git commit -m "feat: persist scanner job progress"
```

## Task 7: Render Progress in Scanner Jobs UI

**Files:**
- Modify: `ui/streamlit_app.py`
- Modify: `tests/test_streamlit_demo_execution_helpers.py`

- [ ] **Step 1: Write failing UI source test**

Append to `tests/test_streamlit_demo_execution_helpers.py`:

```python
def test_active_job_overview_renders_progress_cache_stats_and_warnings() -> None:
    active_source = _function_source("render_active_job_overview")
    progress_source = _function_source("render_job_progress")

    assert "render_job_progress(meta)" in active_source
    assert "st.progress" in progress_source
    assert "symbol-days" in progress_source
    assert "Now scanning" in progress_source
    assert "Cache" in progress_source
    assert "cache_hits" in progress_source
    assert "downloads" in progress_source
    assert "missing_files" in progress_source
    assert "warnings" in progress_source
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m pytest tests/test_streamlit_demo_execution_helpers.py::test_active_job_overview_renders_progress_cache_stats_and_warnings -q
```

Expected: FAIL because `render_job_progress()` does not exist.

- [ ] **Step 3: Implement progress renderer**

In `ui/streamlit_app.py`, add this helper before `render_active_job_overview()`:

```python
def render_job_progress(meta: dict) -> None:
    progress = meta.get("progress") if isinstance(meta.get("progress"), dict) else {}
    processed = int(progress.get("processed") or 0)
    total = int(progress.get("total") or 0)

    if total > 0:
        ratio = min(max(processed / total, 0.0), 1.0)
        st.progress(ratio, text=f"{processed} / {total} symbol-days")
    else:
        st.caption("Progress will appear after the scanner starts processing symbol-days.")

    current_symbol = progress.get("current_symbol") or "n/a"
    current_date = progress.get("current_date") or "n/a"
    st.markdown("**Now scanning**")
    st.caption(f"{current_symbol} | {current_date}")

    st.markdown("**Cache**")
    cache_cols = st.columns(4)
    cache_cols[0].metric("Hits", progress.get("cache_hits") or 0)
    cache_cols[1].metric("Downloads", progress.get("downloads") or 0)
    cache_cols[2].metric("Missing", progress.get("missing_files") or 0)
    cache_cols[3].metric("Errors", progress.get("errors") or 0)

    warnings = meta.get("warnings") if isinstance(meta.get("warnings"), list) else []
    if warnings:
        st.markdown("**Warnings**")
        warning_rows = [row for row in warnings if isinstance(row, dict)]
        for warning in warning_rows[:5]:
            symbol = warning.get("symbol") or "unknown"
            date = warning.get("date") or "unknown"
            message = warning.get("message") or "warning"
            st.warning(f"{symbol} {date}: {message}")
```

In `render_active_job_overview()`, after `render_job_status(meta)` add:

```python
        render_job_progress(meta)
```

- [ ] **Step 4: Run UI tests**

Run:

```powershell
python -m pytest tests/test_streamlit_demo_execution_helpers.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit UI progress**

Run:

```powershell
git add ui/streamlit_app.py tests/test_streamlit_demo_execution_helpers.py
git commit -m "feat: show scanner job progress in ui"
```

## Task 8: Full Verification and Push

**Files:**
- Verify all touched files.

- [ ] **Step 1: Run the complete test suite**

Run:

```powershell
python -m pytest -q
```

Expected: all tests PASS.

- [ ] **Step 2: Check git status**

Run:

```powershell
git status --short --branch
```

Expected: clean working tree, branch ahead of origin by the new commits.

- [ ] **Step 3: Push the branch**

Run:

```powershell
git push
```

Expected: branch `feature/bot-monitor-dashboard` pushed to GitHub PR #11.

- [ ] **Step 4: Restart local Streamlit if it is running**

Run:

```powershell
$existingProcesses = Get-NetTCPConnection -LocalPort 8502 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique
foreach ($procId in $existingProcesses) { Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue }
$env:BWI_API_URL = 'http://127.0.0.1:8001'
python -m streamlit run ui/streamlit_app.py --server.port 8502 --server.address 127.0.0.1 --server.headless true --browser.gatherUsageStats false
```

Expected: Streamlit serves the updated UI at `http://127.0.0.1:8502`.

## Self-Review Checklist

- Spec coverage: downloader reliability is covered by Task 1, progress metadata by Tasks 2-6, UI visibility by Task 7, verification by Task 8.
- Type consistency: `ArchiveDownloadResult`, `ProgressState`, and `ProgressCallback` are introduced before scanners use them.
- Scope: live/demo execution remains untouched.
- Testing: every behavior change has a failing test step before implementation.
