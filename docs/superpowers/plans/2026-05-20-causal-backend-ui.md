# Causal Backend UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose the existing causal/no-lookahead signal core through backend jobs and Streamlit so users can compare historical research scans with live-safe causal signal scans.

**Architecture:** Keep `bybit_weak_intraday/core.py` and historical scanner unchanged. Add a small archive wrapper around `find_causal_signals()` that downloads the same Bybit archive files and writes `signals.csv`. Add a new backend job type and endpoint, then render causal results in Streamlit without account backtest because causal output is signal-only and has no post-entry PnL.

**Tech Stack:** Python, pandas, FastAPI, Pydantic, Streamlit, Plotly, pytest.

---

### Task 1: Causal Archive Scanner Wrapper

**Files:**
- Create: `bybit_weak_intraday/causal_scanner.py`
- Create: `tests/test_causal_scanner.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_causal_scanner.py` with:

```python
from __future__ import annotations

import pandas as pd

from bybit_weak_intraday.causal import CausalSignal
from bybit_weak_intraday.causal_scanner import signals_to_frame


def test_signals_to_frame_preserves_causal_fields():
    signals = [
        CausalSignal(
            date="2026-03-18",
            symbol="TESTUSDT",
            mode="weak",
            signal_time_utc="2026-03-18T10:00:00+00:00",
            signal_price=1.23,
            score=9,
            weak_score=9,
            pump_score=3,
            turnover_so_far_usdt=1_500_000,
            prev_turnover_usdt=2_000_000,
            turnover_ratio_so_far=0.75,
            runup_so_far_pct=6.0,
            peak_time_utc="2026-03-18T09:30:00+00:00",
            vwap_at_signal=1.25,
            sell_share_peak_to_signal_pct=54.0,
        )
    ]

    frame = signals_to_frame(signals)

    assert list(frame.columns) == [
        "date",
        "symbol",
        "mode",
        "signal_time_utc",
        "signal_price",
        "score",
        "weak_score",
        "pump_score",
        "turnover_so_far_usdt",
        "prev_turnover_usdt",
        "turnover_ratio_so_far",
        "runup_so_far_pct",
        "peak_time_utc",
        "vwap_at_signal",
        "sell_share_peak_to_signal_pct",
    ]
    assert frame.loc[0, "symbol"] == "TESTUSDT"
    assert frame.loc[0, "score"] == 9


def test_signals_to_frame_empty_has_stable_columns():
    frame = signals_to_frame([])

    assert frame.empty
    assert "signal_time_utc" in frame.columns
```

- [ ] **Step 2: Run test to verify failure**

Run:

```powershell
..\..\.venv\Scripts\python.exe -m pytest tests/test_causal_scanner.py -q
```

Expected: `ModuleNotFoundError: No module named 'bybit_weak_intraday.causal_scanner'`.

- [ ] **Step 3: Implement wrapper**

Create `bybit_weak_intraday/causal_scanner.py` with `CAUSAL_SIGNAL_COLUMNS`, `signals_to_frame(signals)`, and a public runner named `run_archive_causal_scan`. The runner should mirror `run_archive_scan`, call `download_archive_file`, `load_archive_ticks`, and `find_causal_signals`, then return one DataFrame of signals.

- [ ] **Step 4: Verify wrapper tests pass**

Run:

```powershell
..\..\.venv\Scripts\python.exe -m pytest tests/test_causal_scanner.py -q
```

Expected: `2 passed`.

### Task 2: Backend Causal Job

**Files:**
- Modify: `backend/app/job_store.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/schemas.py`
- Modify: `tests/test_backend_api.py`

- [ ] **Step 1: Write backend API tests**

Append tests that post to `/jobs/scan-causal`, assert normalized symbols, assert `job_type == "causal_scan"`, and assert `/jobs/{job_id}` exposes `signals_url` for done causal jobs.

- [ ] **Step 2: Run backend tests to verify failure**

Run:

```powershell
..\..\.venv\Scripts\python.exe -m pytest tests/test_backend_api.py -q
```

Expected: fail because `/jobs/scan-causal` and `signals_url` are not implemented.

- [ ] **Step 3: Implement backend job**

Use `ScanRequest` for causal scans. Add:

```text
POST /jobs/scan-causal
GET /jobs/{job_id}/signals.csv
```

Add `_run_causal_scan_job()` in `job_store.py`, write `signals.csv`, and set meta fields:

```text
job_type = causal_scan
message = causal scan complete
signals_rows
signals_path
```

- [ ] **Step 4: Verify backend tests pass**

Run:

```powershell
..\..\.venv\Scripts\python.exe -m pytest tests/test_backend_api.py -q
```

Expected: all backend API tests pass.

### Task 3: Streamlit Causal Results

**Files:**
- Modify: `ui/streamlit_app.py`

- [ ] **Step 1: Add causal job type option**

Change the sidebar job radio to:

```python
["Archive scan", "Causal signal scan", "TP/SL optimizer"]
```

When selected, post to `/jobs/scan-causal`.

- [ ] **Step 2: Render causal jobs**

For `job_type == "causal_scan"` and `status == "done"`, load `/jobs/{job_id}/signals.csv`, show a signal overview, download button, table, and charts:

```text
Signals count
Weak signals
Pump signals
Average score
Scatter: signal time vs score colored by mode
Histogram: mode
```

- [ ] **Step 3: Compile Streamlit**

Run:

```powershell
..\..\.venv\Scripts\python.exe -m py_compile ui\streamlit_app.py
```

Expected: exit code `0`.

### Task 4: Verification And PR

**Files:**
- All files changed above.

- [ ] **Step 1: Run full tests**

Run:

```powershell
..\..\.venv\Scripts\python.exe -m pytest -q
```

Expected: all tests pass.

- [ ] **Step 2: Check formatting and status**

Run:

```powershell
git diff --check
git status --short --branch
```

Expected: no whitespace errors and only expected files changed.

- [ ] **Step 3: Commit and push**

Run:

```powershell
git add bybit_weak_intraday/causal_scanner.py backend/app/job_store.py backend/app/main.py backend/app/schemas.py ui/streamlit_app.py tests/test_causal_scanner.py tests/test_backend_api.py docs/superpowers/plans/2026-05-20-causal-backend-ui.md
git commit -m "feat: add causal scan backend ui"
git push -u origin feature/causal-backend-ui
```

- [ ] **Step 4: Create PR**

Run:

```powershell
gh pr create --title "Add causal scan backend and UI" --body "## Summary`n- add archive causal scan wrapper around live-safe signal core`n- add backend causal scan jobs and signals.csv endpoint`n- add Streamlit causal signal scan mode and results view`n`n## Tests`n- python -m py_compile ui/streamlit_app.py`n- python -m pytest -q"
```
