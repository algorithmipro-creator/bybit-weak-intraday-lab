# Backend Safety Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add baseline backend safety controls before scheduler, alerts or public VPS usage.

**Architecture:** Keep the file-based job runner. Add request-level validation in `ScanRequest`, strict job id path safety in `job_store.py`/`main.py`, and FastAPI API tests with `TestClient`.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, pytest, httpx.

---

## Scope

Implement:

- strict `job_id` validation;
- scan date order and max date-range limits;
- mandatory `max_symbols` cap for full-universe scans;
- API tests for health, scan validation and job id validation;
- docs describing private deployment and current auth boundary.

Do not implement:

- JWT;
- scheduler;
- alerts;
- database migration;
- live trading.

## Safety Rules

```text
job_id must match ^[a-f0-9]{12}$
regular scan date range must be <= 31 days
full-universe scan date range must be <= 7 days
full-universe scan must set max_symbols between 1 and 500
manual symbol list must contain <= 500 symbols
```

## Files

Create:

```text
tests/test_backend_api.py
```

Modify:

```text
requirements.txt
backend/app/schemas.py
backend/app/job_store.py
backend/app/main.py
README.md
SPECIFICATION.md
deploy/README_VPS.md
```

## Tasks

### Task 1: Add Failing API Tests

- [ ] Add `httpx>=0.27` to `requirements.txt`.
- [ ] Install dependencies locally with `python -m pip install -r requirements.txt`.
- [ ] Create `tests/test_backend_api.py`.
- [ ] Add tests for:
  - `/health` returns 200;
  - reversed dates are rejected;
  - large regular ranges are rejected;
  - full-universe without `max_symbols` is rejected;
  - invalid job id path is rejected;
  - `job_dir("../bad")` raises `ValueError`;
  - valid scan request queues without starting a real scan by monkeypatching `create_job` and `executor.submit`.
- [ ] Run `python -m pytest tests/test_backend_api.py -q` and verify validation tests fail before implementation.

### Task 2: Implement ScanRequest Limits

- [ ] Add constants in `backend/app/schemas.py`:
  - `MAX_SCAN_DAYS = 31`
  - `MAX_FULL_UNIVERSE_DAYS = 7`
  - `MAX_REQUEST_SYMBOLS = 500`
- [ ] Use Pydantic validators to normalize symbols and validate date ranges.
- [ ] Require `max_symbols > 0` for `full_universe=true`.
- [ ] Run backend API tests.

### Task 3: Implement Job ID Safety

- [ ] Add `JOB_ID_PATTERN` and `validate_job_id()` in `backend/app/job_store.py`.
- [ ] Call validation in `job_dir()`.
- [ ] Add FastAPI path validation in `backend/app/main.py`.
- [ ] Run backend API tests.

### Task 4: Update Docs

- [ ] Document backend safety limits in `README.md`.
- [ ] Document public deployment boundary in `SPECIFICATION.md`.
- [ ] Keep `deploy/README_VPS.md` clear that API should not be exposed without protection.
- [ ] Run all tests.

### Task 5: Final Verification

- [ ] Run `python -m pytest -q`.
- [ ] Check `git status --short --branch`.
- [ ] Commit and push branch.
- [ ] Create Pull Request.
