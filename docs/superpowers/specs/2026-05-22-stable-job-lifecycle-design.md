# Stable Scanner Job Lifecycle Design

Date: 2026-05-22

## Purpose

The scanner should behave like a reliable research service, not a black-box script. When a user starts an archive scan, causal scan, or TP/SL optimizer job, the backend must keep running despite cache contention or per-symbol archive issues, and the UI must show what the job is doing.

This design covers archive cache reliability, job progress metadata, user-facing warnings, and a clearer Scanner Jobs lifecycle panel.

## Current State

- Scanner jobs run in the FastAPI backend through `backend/app/job_store.py`.
- Archive files are downloaded by `bybit_weak_intraday/archive.py`.
- The downloader currently writes to a shared temp file path like `SYMBOLYYYY-MM-DD.csv.gz.tmp`.
- On Windows, a concurrent or recently interrupted process can leave that temp file locked, causing `WinError 32`.
- The UI can show queued/running/done/error, but it does not show symbol/date progress or cache activity.
- Backend defaults to one worker, but lock errors can still happen after restarts, overlapping local processes, or stale temp cleanup.

## Goals

1. Make archive downloads resilient to temp-file lock conflicts.
2. Keep jobs alive when a single symbol/day fails to download or parse.
3. Persist progress in `meta.json` so `/jobs` and `/jobs/{job_id}` can expose it.
4. Show progress and cache stats in the Streamlit `Scanner Jobs` page.
5. Preserve current scan behavior and CSV outputs.
6. Keep live/demo execution untouched.

## Non-Goals

- No production-grade external queue in this step.
- No cancel/retry job endpoint in this step.
- No live-trading automation.
- No change to the trading strategy rules.
- No database migration; job state remains file-based JSON.

## Chosen Approach

Implement the middle path: cache reliability plus progress metadata plus UI visibility.

This keeps the project simple enough for the current MVP while fixing the practical problem the user already saw: a scan can fail from `.tmp` cache contention and the interface does not explain what happened.

## Backend Design

### Archive Downloader

`download_archive_file()` will stop using one shared temp path.

New behavior:

- Final cache path stays the same:
  `data/bybit_archive_cache/SYMBOL/SYMBOLYYYY-MM-DD.csv.gz`
- Temp path becomes unique per attempt, for example:
  `SYMBOLYYYY-MM-DD.csv.gz.<pid>.<thread>.<uuid>.tmp`
- Before downloading, if the final file exists and has size > 0, return it.
- After downloading, check the final path again. If another process already completed it, delete this temp file if possible and return the final file.
- Replace temp into final path atomically where possible.
- If temp cleanup fails because Windows still has the file locked, record the cleanup warning but do not fail the job.
- A 404 still means "archive file missing" and returns `None`.

The downloader should return enough metadata for progress accounting:

```python
ArchiveDownloadResult(
    path=Path(...) | None,
    status="cache_hit" | "downloaded" | "missing" | "error",
    warning=None | "...",
)
```

For compatibility, either keep `download_archive_file()` returning `Path | None` and add a new `download_archive_file_result()`, or update call sites together. The implementation plan should choose the least invasive option after checking tests.

### Scanner Progress Callback

`run_archive_scan()` and `run_archive_causal_scan_outputs()` will accept an optional callback:

```python
progress_callback(event: dict) -> None
```

The callback is invoked once per symbol/day after download attempts and again after scoring/evaluation.

Example event:

```json
{
  "current_symbol": "ENAUSDT",
  "current_date": "2026-03-20",
  "processed": 18,
  "total": 70,
  "cache_hits": 21,
  "downloads": 12,
  "missing_files": 3,
  "errors": 0,
  "message": "scanning ENAUSDT 2026-03-20"
}
```

The scanner should treat individual symbol/day errors as row-level warnings where possible. The full job should become `error` only for unrecoverable failures such as invalid request shape, no write access to the jobs directory, or unexpected top-level exceptions outside the symbol/day loop.

### Job Store

`backend/app/job_store.py` will own progress persistence.

Each running job `meta.json` will include:

```json
{
  "status": "running",
  "message": "scanning ENAUSDT 2026-03-20",
  "progress": {
    "processed": 18,
    "total": 70,
    "current_symbol": "ENAUSDT",
    "current_date": "2026-03-20",
    "cache_hits": 21,
    "downloads": 12,
    "missing_files": 3,
    "errors": 0
  },
  "warnings": [
    {
      "symbol": "GRASSUSDT",
      "date": "2026-03-25",
      "message": "archive file missing"
    }
  ]
}
```

Progress writes should be throttled enough to avoid excessive disk writes. A simple implementation can save after each symbol/day because scan volume is modest in the MVP. If full-universe scans become too chatty, the implementation can throttle later by time or processed count.

When a job completes, keep the final progress block and add result row counts as today.

## Frontend Design

The `Scanner Jobs` page already has an `Active Job` area. It will be extended with:

- Progress bar when `progress.total > 0`.
- Text summary: `18 / 70 symbol-days`.
- Current symbol/date line.
- Cache counters: hits, downloads, missing files, errors.
- Warning list, limited to the newest or first few warnings.
- Clear empty states when progress is not yet available.

Example:

```text
Active Job
RUNNING | causal_scan | Updated 2026-05-22 18:42

[########------------] 18 / 70 symbol-days

Now scanning
ENAUSDT | 2026-03-20

Cache
Hits 21 | Downloads 12 | Missing 3 | Errors 0

Warnings
GRASSUSDT 2026-03-25: archive file missing
```

The lower job table and detailed CSV result tabs stay in place.

## Data Flow

1. User starts a scan from Streamlit.
2. Streamlit posts to `/jobs/scan`, `/jobs/scan-causal`, or `/jobs/optimize-tp-sl`.
3. Backend creates `meta.json` with queued status.
4. Worker sets status to running and initializes progress.
5. Scanner loops through symbol/date work units.
6. Archive downloader reports cache/download/missing/error status.
7. Scanner calls `progress_callback(event)`.
8. Job store merges progress into `meta.json`.
9. Streamlit polls `/jobs` and `/jobs/{job_id}`.
10. UI renders progress, warnings, and final result counts.

## Error Handling

- Missing archive file: count as `missing_files`, add warning, continue.
- Temp cleanup failure: add warning, continue.
- Download transport failure after retries: count as error or missing depending on status, continue if the scanner can skip that symbol/day.
- Parse/scoring failure for one symbol/day: add metrics error row where current scanner behavior supports it, increment errors, continue.
- Top-level job failure: status becomes `error`, message is sanitized by existing job error flow.

## Testing

Add or update tests for:

- Downloader uses unique temp paths instead of one shared `.tmp`.
- Downloader returns existing final cache file if another process completed it.
- Cleanup errors do not raise when final cache file is usable.
- Scanner calls progress callback with processed/total/current symbol/date.
- Job store writes progress into `meta.json`.
- Streamlit source-level test confirms progress bar, cache counters, and warnings are rendered in `Scanner Jobs`.
- Full test suite remains green.

## Rollout

1. Implement downloader result object or compatibility wrapper.
2. Add progress callback support to regular scan.
3. Add progress callback support to causal scan.
4. Wire progress into job store.
5. Extend Streamlit `Active Job` UI.
6. Run targeted tests and full suite.
7. Push to the current PR branch.

## Open Decisions Resolved

- Job state remains JSON files, not a database.
- The UI will show progress in `Scanner Jobs`, not `Monitor`.
- Execution/demo order code is out of scope for this feature.
- Full external queue is deferred until the MVP needs cancellation, retries, or multiple workers.
