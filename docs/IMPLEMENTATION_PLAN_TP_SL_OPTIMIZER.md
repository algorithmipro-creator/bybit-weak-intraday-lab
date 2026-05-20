# TP/SL Grid Optimizer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an offline TP/SL grid optimizer that reuses existing archive scan and `first_barrier` simulation logic.

**Architecture:** Keep signal discovery unchanged. Add an optimizer module that reruns the archive scanner over a TP/SL grid, aggregates outcomes, and writes optimizer CSVs through the existing job-store pattern. Add a FastAPI optimizer job endpoint and a Streamlit optimizer view.

**Tech Stack:** Python 3.12, pandas, FastAPI, Streamlit, pytest.

---

## Scope

Implement:

- `bybit_weak_intraday/optimizer.py`;
- core tests for grid aggregation;
- backend `POST /jobs/optimize-tp-sl`;
- backend CSV endpoints for `grid.csv` and `grid_trades.csv`;
- Streamlit controls for TP/SL grid jobs;
- docs.

Do not implement:

- dynamic ML TP/SL model;
- paper trading;
- scheduler;
- live execution.

## Design Decision

The first optimizer is intentionally offline and conservative.

It does not infer first-barrier ordering from MFE/MAE. Instead, it reruns the existing archive scan for each TP/SL pair so that the existing tick-level `first_barrier()` logic decides whether TP or SL was hit first.

This is slower than caching each candidate path once, but it is much safer for the MVP and avoids a hidden optimistic bias.

## Files

Create:

```text
bybit_weak_intraday/optimizer.py
tests/test_optimizer.py
```

Modify:

```text
backend/app/schemas.py
backend/app/job_store.py
backend/app/main.py
ui/streamlit_app.py
README.md
SPECIFICATION.md
docs/ROADMAP.md
```

## API

### Request

`POST /jobs/optimize-tp-sl`

Fields:

```text
all ScanRequest fields
tp_grid: list[float]
sl_grid: list[float]
```

Limits:

```text
1 <= len(tp_grid) <= 10
1 <= len(sl_grid) <= 10
0 < tp <= 1
0 < sl <= 1
```

### Outputs

For optimizer jobs:

```text
GET /jobs/{job_id}/grid.csv
GET /jobs/{job_id}/grid_trades.csv
```

`grid.csv` columns:

```text
tp_pct
sl_pct
trades
tp_hits
sl_hits
time_or_eod_exits
avg_underlying_pnl
median_underlying_pnl
avg_minutes_to_exit
tp_rate
sl_rate
```

`grid_trades.csv` contains all per-combo simulated trade rows with `tp_pct` and `sl_pct`.

## Task 1: Core Optimizer Tests

- [ ] Create `tests/test_optimizer.py`.
- [ ] Test that `summarize_grid_trades()` aggregates `tp`, `sl`, and `time_stop/eod` outcomes correctly.
- [ ] Test that `run_archive_tp_sl_grid()` calls `run_archive_scan()` once per TP/SL pair by monkeypatching the scanner.
- [ ] Verify tests fail before `optimizer.py` exists.

## Task 2: Core Optimizer Implementation

- [ ] Create `bybit_weak_intraday/optimizer.py`.
- [ ] Implement `summarize_grid_trades(trades: pd.DataFrame) -> pd.DataFrame`.
- [ ] Implement `run_archive_tp_sl_grid(...) -> tuple[pd.DataFrame, pd.DataFrame]`.
- [ ] Use `dataclasses.replace()` to set `tp_weak`, `tp_pump`, `sl_weak`, `sl_pump` per grid pair.
- [ ] Run `python -m pytest tests/test_optimizer.py -q`.
- [ ] Run `python -m pytest -q`.
- [ ] Commit core optimizer.

## Task 3: Backend Optimizer Job Tests

- [ ] Extend `tests/test_backend_api.py`.
- [ ] Add tests for `POST /jobs/optimize-tp-sl`.
- [ ] Assert invalid empty grids return 422.
- [ ] Monkeypatch job creation/executor so no real scan starts.
- [ ] Verify endpoint fails before implementation.

## Task 4: Backend Optimizer Implementation

- [ ] Add `OptimizeRequest` to `backend/app/schemas.py`.
- [ ] Extend `create_job()` with `job_type`.
- [ ] Split job runner into scan and optimizer branches.
- [ ] Save optimizer outputs as:
  - `grid.csv`
  - `grid_trades.csv`
- [ ] Add FastAPI routes:
  - `POST /jobs/optimize-tp-sl`
  - `GET /jobs/{job_id}/grid.csv`
  - `GET /jobs/{job_id}/grid_trades.csv`
- [ ] Run backend tests and full tests.
- [ ] Commit backend optimizer.

## Task 5: Streamlit UI

- [ ] Add sidebar mode selector:
  - `Archive scan`
  - `TP/SL optimizer`
- [ ] For optimizer mode, show TP grid and SL grid text inputs.
- [ ] POST to `/jobs/optimize-tp-sl`.
- [ ] When a job is done and grid files exist, show optimizer tabs:
  - Grid Summary
  - Grid Trades
  - Charts
- [ ] Keep existing scan UI behavior.
- [ ] Run tests.
- [ ] Commit UI.

## Task 6: Documentation And Final Verification

- [ ] Update README API section.
- [ ] Update SPECIFICATION strategy analytics section.
- [ ] Update ROADMAP Phase 3 status.
- [ ] Run `python -m pytest -q`.
- [ ] Push branch and create PR.

## Self-Review Notes

Spec coverage:

- Offline TP/SL optimizer: covered.
- Backend endpoint: covered.
- Streamlit view: covered.
- Dynamic optimizer: explicitly out of scope.
- Live trading: explicitly out of scope.

No placeholders remain.
