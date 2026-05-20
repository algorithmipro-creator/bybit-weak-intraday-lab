# Causal Post-Signal Evaluation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add post-signal evaluation for causal signals so each live-safe signal can be evaluated with MFE, MAE, TP/SL outcome, PnL, and time-to-exit after the signal is emitted.

**Architecture:** Keep `signals.csv` as the no-lookahead signal artifact. Add a separate `evaluations.csv` artifact produced after signal generation using future ticks. Reuse existing `first_barrier` short-path logic so causal evaluation matches historical TP/SL semantics.

**Tech Stack:** Python, pandas, FastAPI, Streamlit, Plotly, pytest.

---

### Task 1: Pure Causal Evaluation Helpers

**Files:**
- Modify: `bybit_weak_intraday/causal_scanner.py`
- Modify: `tests/test_causal_scanner.py`

- [ ] **Step 1: Write failing tests**

Add tests for `evaluate_causal_signal` and `evaluations_to_frame`. The first test must prove future ticks before the signal are ignored.

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
..\..\.venv\Scripts\python.exe -m pytest tests/test_causal_scanner.py -q
```

Expected: fail because `evaluate_causal_signal` and `evaluations_to_frame` do not exist.

- [ ] **Step 3: Implement evaluation helpers**

Add:

```text
CAUSAL_EVALUATION_COLUMNS
evaluate_causal_signal(signal, cur_ticks_raw, cfg) -> dict
evaluate_causal_signals(signals, cur_ticks_raw, cfg) -> DataFrame
evaluations_to_frame(rows) -> DataFrame
```

Evaluation must add:

```text
entry_time_utc
entry_price
tp_pct
sl_pct
mfe_after_entry_pct
mae_after_entry_pct
outcome
exit_time_utc
exit_price
pnl_underlying_pct
minutes_to_exit
```

- [ ] **Step 4: Run tests**

Run:

```powershell
..\..\.venv\Scripts\python.exe -m pytest tests/test_causal_scanner.py -q
```

Expected: causal scanner tests pass.

### Task 2: Archive Causal Scan Outputs

**Files:**
- Modify: `bybit_weak_intraday/causal_scanner.py`
- Modify: `tests/test_causal_scanner.py`

- [ ] **Step 1: Add output function tests**

Add a test for a function named `run_archive_causal_scan_outputs` using monkeypatches for archive download/load and causal signal finding.

- [ ] **Step 2: Implement output function**

Add:

```python
def run_archive_causal_scan_outputs(
    start: str | dt.date,
    end: str | dt.date,
    symbols: Iterable[str] | None = None,
    full_universe: bool = False,
    include_majors: bool = False,
    max_symbols: int = 0,
    cache_dir: str | Path = "./bybit_archive_cache",
    cfg: StrategyConfig | None = None,
    sleep: float = 0.15,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    # Return signals and post-signal evaluations from one archive pass.
```

It must return `(signals, evaluations)` without downloading files twice.

### Task 3: Backend Evaluation Artifact

**Files:**
- Modify: `backend/app/job_store.py`
- Modify: `backend/app/main.py`
- Modify: `tests/test_backend_api.py`

- [ ] **Step 1: Add backend API tests**

Add a test that a done `causal_scan` job exposes both `signals_url` and `evaluations_url`.

- [ ] **Step 2: Implement backend artifact**

Write both `signals.csv` and `evaluations.csv` in `_run_causal_scan_job`. Add:

```text
evaluations_rows
evaluations_path
GET /jobs/{job_id}/evaluations.csv
```

### Task 4: Streamlit Evaluation View

**Files:**
- Modify: `ui/streamlit_app.py`

- [ ] **Step 1: Load evaluations for causal jobs**

For done causal jobs, fetch `/jobs/{job_id}/evaluations.csv` in addition to `signals.csv`.

- [ ] **Step 2: Render evaluation overview**

Show evaluation metrics with `trade_result_summary(evaluations)` and tabs:

```text
Signals
Evaluations
Charts
```

Charts should include MFE vs MAE and outcome histogram when evaluation rows exist.

### Task 5: Verify And Publish

**Files:**
- All changed files.

- [ ] **Step 1: Run verification**

Run:

```powershell
..\..\.venv\Scripts\python.exe -m py_compile ui\streamlit_app.py bybit_weak_intraday\causal_scanner.py backend\app\main.py backend\app\job_store.py
..\..\.venv\Scripts\python.exe -m pytest -q
git diff --check
```

- [ ] **Step 2: Commit and PR**

Commit, push `feature/causal-post-signal-eval`, and open a PR titled `Add causal post-signal evaluation`.
