# Signal Decision Demo Auto-Entry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a demo-only signal decision layer that evaluates latest scanner candidates, optionally sends one guarded demo short order, journals every decision, and sends outbound-only Telegram notifications.

**Architecture:** Keep decisioning separate from execution. Add small core modules for candidate normalization, decision journals, decision rules, and Telegram notifications; then wire them through FastAPI routes and Streamlit UI. Existing demo execution safety remains authoritative.

**Tech Stack:** Python 3.12, pandas, requests, FastAPI, Streamlit, pytest, CSV journals, Bybit demo API, Telegram Bot API.

---

## Scope Check

This plan covers one MVP feature: signal decision + demo auto-entry + Telegram notifications. It deliberately excludes schedulers, live trading, Telegram commands, and database storage.

## File Map

- Create `bybit_weak_intraday/signals/__init__.py`: package marker and selected exports.
- Create `bybit_weak_intraday/signals/journal.py`: append/read decision journal CSV.
- Create `bybit_weak_intraday/signals/candidates.py`: normalize scanner job CSV outputs into candidate rows.
- Create `bybit_weak_intraday/signals/decision.py`: pure decision rules and decision row construction.
- Create `bybit_weak_intraday/notifications/__init__.py`: package marker.
- Create `bybit_weak_intraday/notifications/telegram.py`: outbound-only Telegram notifier.
- Modify `ui/bot_monitor.py`: import shared candidate helpers from `bybit_weak_intraday.signals.candidates`.
- Modify `backend/app/settings.py`: add signal and Telegram settings.
- Modify `backend/app/execution_routes.py`: extract reusable demo short placement helper while preserving the current endpoint response shape.
- Create `backend/app/signal_routes.py`: signal decision API.
- Modify `backend/app/main.py`: include signal router.
- Modify `ui/app_navigation.py`: add `Signal Decisions` menu item.
- Modify `ui/streamlit_app.py`: add Signal Decisions page and Telegram status/test controls in Settings.
- Create tests: `tests/test_signal_decision_journal.py`, `tests/test_signal_candidates.py`, `tests/test_signal_decision.py`, `tests/test_telegram_notifications.py`, `tests/test_signal_api.py`.
- Modify tests: `tests/test_bot_monitor.py`, `tests/test_app_navigation.py`, `tests/test_execution_api.py`, `tests/test_streamlit_demo_execution_helpers.py`, `tests/test_ui_summary.py`.

## Task 1: Decision Journal

**Files:**
- Create: `bybit_weak_intraday/signals/__init__.py`
- Create: `bybit_weak_intraday/signals/journal.py`
- Create: `tests/test_signal_decision_journal.py`

- [ ] **Step 1: Write failing journal tests**

Create `tests/test_signal_decision_journal.py`:

```python
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


def test_read_decision_journal_tail_returns_newest_first(tmp_path: Path) -> None:
    path = tmp_path / "signal_decisions.csv"
    append_decision_event(path, {"decision_id": "dec-1", "created_at_utc": "2026-05-22T18:00:00+00:00"})
    append_decision_event(path, {"decision_id": "dec-2", "created_at_utc": "2026-05-22T18:01:00+00:00"})

    frame = read_decision_journal_tail(path, 1)

    assert list(frame["decision_id"]) == ["dec-2"]
    assert list(frame.columns) == DECISION_JOURNAL_COLUMNS
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
..\..\.venv\Scripts\python.exe -m pytest tests/test_signal_decision_journal.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'bybit_weak_intraday.signals'`.

- [ ] **Step 3: Implement decision journal**

Create `bybit_weak_intraday/signals/__init__.py`:

```python
from __future__ import annotations
```

Create `bybit_weak_intraday/signals/journal.py`:

```python
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


def append_decision_event(path: str | Path, event: dict[str, Any]) -> None:
    journal_path = Path(path)
    journal_path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not journal_path.exists() or journal_path.stat().st_size == 0
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
```

- [ ] **Step 4: Run journal tests**

Run:

```powershell
..\..\.venv\Scripts\python.exe -m pytest tests/test_signal_decision_journal.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```powershell
git add bybit_weak_intraday/signals/__init__.py bybit_weak_intraday/signals/journal.py tests/test_signal_decision_journal.py
git commit -m "feat: add signal decision journal"
```

## Task 2: Telegram Notifier

**Files:**
- Create: `bybit_weak_intraday/notifications/__init__.py`
- Create: `bybit_weak_intraday/notifications/telegram.py`
- Create: `tests/test_telegram_notifications.py`

- [ ] **Step 1: Write failing Telegram tests**

Create `tests/test_telegram_notifications.py`:

```python
from __future__ import annotations

import requests

from bybit_weak_intraday.notifications.telegram import TelegramConfig, send_telegram_message, telegram_status


class FakeResponse:
    def __init__(self, payload=None):
        self.payload = payload or {"ok": True}

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, response=None, error: Exception | None = None):
        self.response = response or FakeResponse()
        self.error = error
        self.calls = []

    def post(self, url, *, json, timeout):
        self.calls.append({"url": url, "json": json, "timeout": timeout})
        if self.error:
            raise self.error
        return self.response


def test_telegram_status_redacts_token_and_chat_id() -> None:
    status = telegram_status(TelegramConfig(enabled=True, bot_token="secret-token", chat_id="123"))

    assert status == {"enabled": True, "bot_token_configured": True, "chat_id_configured": True}
    assert "secret-token" not in str(status)
    assert "123" not in str(status)


def test_send_telegram_message_returns_disabled_without_network() -> None:
    session = FakeSession()

    result = send_telegram_message(
        TelegramConfig(enabled=False, bot_token="secret", chat_id="123"),
        "hello",
        session=session,
    )

    assert result.status == "disabled"
    assert session.calls == []


def test_send_telegram_message_returns_not_configured_without_token_or_chat() -> None:
    result = send_telegram_message(TelegramConfig(enabled=True, bot_token="", chat_id=""), "hello", session=FakeSession())

    assert result.status == "not_configured"


def test_send_telegram_message_posts_to_bot_api_without_returning_secret() -> None:
    session = FakeSession()

    result = send_telegram_message(
        TelegramConfig(enabled=True, bot_token="secret-token", chat_id="123"),
        "Signal qualified",
        session=session,
    )

    assert result.status == "sent"
    assert session.calls[0]["url"] == "https://api.telegram.org/botsecret-token/sendMessage"
    assert session.calls[0]["json"] == {"chat_id": "123", "text": "Signal qualified"}
    assert "secret-token" not in str(result)


def test_send_telegram_message_sanitizes_transport_errors() -> None:
    result = send_telegram_message(
        TelegramConfig(enabled=True, bot_token="secret-token", chat_id="123"),
        "hello",
        session=FakeSession(error=requests.RequestException("failed with secret-token")),
    )

    assert result.status == "error"
    assert result.error == "telegram_request_failed"
    assert "secret-token" not in str(result)
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
..\..\.venv\Scripts\python.exe -m pytest tests/test_telegram_notifications.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'bybit_weak_intraday.notifications'`.

- [ ] **Step 3: Implement Telegram notifier**

Create `bybit_weak_intraday/notifications/__init__.py`:

```python
from __future__ import annotations
```

Create `bybit_weak_intraday/notifications/telegram.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import requests


class TelegramSession(Protocol):
    def post(self, url: str, *, json: dict, timeout: int):
        ...


@dataclass(frozen=True)
class TelegramConfig:
    enabled: bool = False
    bot_token: str = ""
    chat_id: str = ""
    timeout_seconds: int = 10


@dataclass(frozen=True)
class TelegramResult:
    status: str
    error: str = ""


def telegram_status(config: TelegramConfig) -> dict[str, bool]:
    return {
        "enabled": bool(config.enabled),
        "bot_token_configured": bool(config.bot_token.strip()),
        "chat_id_configured": bool(config.chat_id.strip()),
    }


def send_telegram_message(
    config: TelegramConfig,
    text: str,
    *,
    session: TelegramSession | None = None,
) -> TelegramResult:
    if not config.enabled:
        return TelegramResult(status="disabled")
    token = config.bot_token.strip()
    chat_id = config.chat_id.strip()
    if not token or not chat_id:
        return TelegramResult(status="not_configured")

    client = session or requests.Session()
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        response = client.post(url, json={"chat_id": chat_id, "text": text}, timeout=int(config.timeout_seconds))
        response.raise_for_status()
    except requests.RequestException:
        return TelegramResult(status="error", error="telegram_request_failed")
    return TelegramResult(status="sent")
```

- [ ] **Step 4: Run Telegram tests**

Run:

```powershell
..\..\.venv\Scripts\python.exe -m pytest tests/test_telegram_notifications.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```powershell
git add bybit_weak_intraday/notifications/__init__.py bybit_weak_intraday/notifications/telegram.py tests/test_telegram_notifications.py
git commit -m "feat: add telegram notification client"
```

## Task 3: Shared Scanner Candidate Normalization

**Files:**
- Create: `bybit_weak_intraday/signals/candidates.py`
- Modify: `ui/bot_monitor.py`
- Create: `tests/test_signal_candidates.py`
- Modify: `tests/test_bot_monitor.py`

- [ ] **Step 1: Write failing candidate tests**

Create `tests/test_signal_candidates.py`:

```python
from __future__ import annotations

import pandas as pd

from bybit_weak_intraday.signals.candidates import build_scanner_watchlist, select_latest_scanner_job


def test_select_latest_scanner_job_selects_latest_done_scan_or_causal() -> None:
    jobs = [
        {"job_id": "old", "job_type": "scan", "status": "done", "updated_at": "2026-05-22T10:00:00+00:00"},
        {"job_id": "new", "job_type": "causal_scan", "status": "done", "updated_at": "2026-05-22T11:00:00+00:00"},
        {"job_id": "running", "job_type": "scan", "status": "running", "updated_at": "2026-05-22T12:00:00+00:00"},
    ]

    assert select_latest_scanner_job(jobs)["job_id"] == "new"


def test_build_scanner_watchlist_from_causal_signals() -> None:
    signals = pd.DataFrame(
        [
            {
                "date": "2026-03-18",
                "symbol": "ENAUSDT",
                "mode": "weak",
                "score": 10,
                "signal_time_utc": "2026-03-18T10:00:00+00:00",
                "signal_price": 0.1,
                "turnover_so_far_usdt": 2_000_000,
            }
        ]
    )
    evaluations = pd.DataFrame(
        [{"date": "2026-03-18", "symbol": "ENAUSDT", "signal_time_utc": "2026-03-18T10:00:00+00:00", "outcome": "tp"}]
    )

    watchlist = build_scanner_watchlist("causal_scan", signals=signals, evaluations=evaluations)

    assert list(watchlist.columns) == [
        "symbol",
        "mode",
        "score",
        "time_utc",
        "price",
        "turnover_usdt",
        "status",
        "outcome",
        "pnl_underlying_pct",
    ]
    assert watchlist.loc[0, "status"] == "waiting"
    assert watchlist.loc[0, "outcome"] == "tp"


def test_build_scanner_watchlist_from_regular_scan() -> None:
    trades = pd.DataFrame(
        [
            {
                "symbol": "JTOUSDT",
                "mode": "pump",
                "candidate_score": 9,
                "entry_time_utc": "2026-03-18T11:00:00+00:00",
                "entry_price": 1.23,
                "turnover_usdt": 3_000_000,
            }
        ]
    )

    watchlist = build_scanner_watchlist("scan", trades=trades)

    assert watchlist.loc[0, "symbol"] == "JTOUSDT"
    assert watchlist.loc[0, "score"] == 9
    assert watchlist.loc[0, "status"] == "candidate"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
..\..\.venv\Scripts\python.exe -m pytest tests/test_signal_candidates.py -q
```

Expected: FAIL because `bybit_weak_intraday.signals.candidates` does not exist.

- [ ] **Step 3: Implement candidate module and UI import**

Create `bybit_weak_intraday/signals/candidates.py`:

```python
from __future__ import annotations

import math
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd

WATCHLIST_COLUMNS = [
    "symbol",
    "mode",
    "score",
    "time_utc",
    "price",
    "turnover_usdt",
    "status",
    "outcome",
    "pnl_underlying_pct",
]
WATCHLIST_NUMERIC_COLUMNS = ["score", "price", "turnover_usdt", "pnl_underlying_pct"]


def select_latest_scanner_job(jobs: list[dict] | None) -> dict | None:
    if not isinstance(jobs, (list, tuple)):
        return None
    scanner_jobs = [
        job
        for job in jobs
        if isinstance(job, dict)
        and job.get("status") == "done"
        and job.get("job_type") in ("causal_scan", "scan", "", None)
    ]
    if scanner_jobs:
        return max(scanner_jobs, key=_job_updated_at)
    return None


def build_scanner_watchlist(
    job_type: str,
    *,
    signals: Any = None,
    evaluations: Any = None,
    trades: Any = None,
    max_rows: int = 20,
) -> pd.DataFrame:
    if job_type == "causal_scan":
        watchlist = _causal_watchlist(signals, evaluations)
    else:
        watchlist = _regular_watchlist(trades)
    return watchlist.head(max_rows).reset_index(drop=True)


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, str) and value == "":
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _job_updated_at(job: dict) -> datetime:
    value = job.get("updated_at")
    if not value:
        return datetime.min.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _frame(value: Any) -> pd.DataFrame:
    if value is None:
        return pd.DataFrame()
    if isinstance(value, pd.DataFrame):
        return value.copy()
    if isinstance(value, (list, tuple)) and not all(isinstance(row, Mapping) for row in value):
        return pd.DataFrame()
    try:
        return pd.DataFrame(value)
    except (TypeError, ValueError):
        return pd.DataFrame()


def _causal_watchlist(signals: Any, evaluations: Any) -> pd.DataFrame:
    df = _frame(signals)
    if df.empty:
        return pd.DataFrame(columns=WATCHLIST_COLUMNS)

    evals = _frame(evaluations)
    if not evals.empty and "symbol" in df.columns and "symbol" in evals.columns:
        keys = _causal_evaluation_merge_keys(df, evals)
        keep = keys + [column for column in ["outcome", "pnl_underlying_pct"] if column in evals.columns]
        df = df.merge(evals[keep].drop_duplicates(keys, keep="last"), on=keys, how="left")

    df = df.rename(
        columns={
            "signal_time_utc": "time_utc",
            "signal_price": "price",
            "turnover_so_far_usdt": "turnover_usdt",
        }
    )
    df["status"] = "waiting"
    return _with_watchlist_columns(df)


def _regular_watchlist(trades: Any) -> pd.DataFrame:
    df = _frame(trades)
    if df.empty:
        return pd.DataFrame(columns=WATCHLIST_COLUMNS)
    df = df.rename(
        columns={
            "candidate_score": "score",
            "entry_time_utc": "time_utc",
            "entry_price": "price",
        }
    )
    df["status"] = "candidate"
    return _with_watchlist_columns(df)


def _with_watchlist_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for column in WATCHLIST_COLUMNS:
        if column not in out.columns:
            out[column] = pd.NA
    for column in WATCHLIST_NUMERIC_COLUMNS:
        out[column] = out[column].map(_watchlist_number)
    return out[WATCHLIST_COLUMNS]


def _causal_evaluation_merge_keys(signals: pd.DataFrame, evaluations: pd.DataFrame) -> list[str]:
    signal_keys = ["date", "symbol", "signal_time_utc"]
    if all(key in signals.columns and key in evaluations.columns for key in signal_keys):
        return signal_keys
    return ["symbol"]


def _watchlist_number(value: Any) -> float | Any:
    parsed = _safe_float(value)
    return parsed if parsed is not None else pd.NA
```

In `ui/bot_monitor.py`, delete `WATCHLIST_COLUMNS`, `WATCHLIST_NUMERIC_COLUMNS`, `select_latest_scanner_job()`, `build_scanner_watchlist()`, `_job_updated_at()`, `_frame()`, `_causal_watchlist()`, `_regular_watchlist()`, `_with_watchlist_columns()`, `_causal_evaluation_merge_keys()`, and `_watchlist_number()`. Add this import below the pandas import:

```python
from bybit_weak_intraday.signals.candidates import build_scanner_watchlist, select_latest_scanner_job
```

Keep `safe_float`, `result_rows()`, wallet summary, positions, open orders, `_protections_by_symbol()`, and `_epoch_millis_to_iso()` in `ui/bot_monitor.py`.

- [ ] **Step 4: Run candidate and bot monitor tests**

Run:

```powershell
..\..\.venv\Scripts\python.exe -m pytest tests/test_signal_candidates.py tests/test_bot_monitor.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```powershell
git add bybit_weak_intraday/signals/candidates.py ui/bot_monitor.py tests/test_signal_candidates.py tests/test_bot_monitor.py
git commit -m "feat: share scanner candidate normalization"
```

## Task 4: Pure Signal Decision Rules

**Files:**
- Create: `bybit_weak_intraday/signals/decision.py`
- Create: `tests/test_signal_decision.py`

- [ ] **Step 1: Write failing decision tests**

Create `tests/test_signal_decision.py`:

```python
from __future__ import annotations

from bybit_weak_intraday.signals.decision import DecisionConfig, evaluate_signal_candidate


def _candidate(**overrides):
    row = {
        "symbol": "ENAUSDT",
        "mode": "weak",
        "score": 10,
        "price": 0.1,
        "time_utc": "2026-03-18T10:00:00+00:00",
    }
    row.update(overrides)
    return row


def _config(**overrides):
    values = {
        "min_score": 9,
        "symbol_whitelist": {"ENAUSDT", "JTOUSDT"},
        "execution_mode": "demo",
        "execution_enabled": True,
        "demo_keys_configured": True,
        "auto_entry_enabled": True,
        "notional_usdt": 25.0,
        "max_notional_usdt": 25.0,
        "open_positions_count": 0,
        "max_open_positions": 1,
        "daily_order_count": 0,
        "max_daily_orders": 3,
        "cooldown_active": False,
        "take_profit_pct": 0.06,
        "stop_loss_pct": 0.07,
    }
    values.update(overrides)
    return DecisionConfig(**values)


def test_evaluate_signal_candidate_qualifies_valid_candidate() -> None:
    decision = evaluate_signal_candidate(_candidate(), _config(), job_id="job-1", job_type="causal_scan")

    assert decision["status"] == "qualified"
    assert decision["reason"] == "qualified"
    assert decision["symbol"] == "ENAUSDT"
    assert decision["side"] == "Sell"
    assert decision["job_id"] == "job-1"
    assert decision["notional_usdt"] == 25.0


def test_evaluate_signal_candidate_rejects_score_below_threshold() -> None:
    decision = evaluate_signal_candidate(_candidate(score=8), _config(), job_id="job-1", job_type="scan")

    assert decision["status"] == "rejected"
    assert decision["reason"] == "score_below_threshold"


def test_evaluate_signal_candidate_rejects_symbol_not_whitelisted() -> None:
    decision = evaluate_signal_candidate(_candidate(symbol="BADUSDT"), _config(), job_id="job-1", job_type="scan")

    assert decision["status"] == "rejected"
    assert decision["reason"] == "symbol_not_whitelisted"


def test_evaluate_signal_candidate_rejects_disabled_execution_before_entry() -> None:
    decision = evaluate_signal_candidate(_candidate(), _config(execution_enabled=False), job_id="job-1", job_type="scan")

    assert decision["status"] == "rejected"
    assert decision["reason"] == "execution_disabled"


def test_evaluate_signal_candidate_rejects_auto_entry_disabled_when_order_requested() -> None:
    decision = evaluate_signal_candidate(
        _candidate(),
        _config(auto_entry_enabled=False),
        job_id="job-1",
        job_type="scan",
        require_auto_entry=True,
    )

    assert decision["status"] == "rejected"
    assert decision["reason"] == "auto_entry_disabled"


def test_evaluate_signal_candidate_rejects_missing_price() -> None:
    decision = evaluate_signal_candidate(_candidate(price=None), _config(), job_id="job-1", job_type="scan")

    assert decision["status"] == "rejected"
    assert decision["reason"] == "candidate_missing_price"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
..\..\.venv\Scripts\python.exe -m pytest tests/test_signal_decision.py -q
```

Expected: FAIL because `bybit_weak_intraday.signals.decision` does not exist.

- [ ] **Step 3: Implement decision rules**

Create `bybit_weak_intraday/signals/decision.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


@dataclass(frozen=True)
class DecisionConfig:
    min_score: float
    symbol_whitelist: set[str]
    execution_mode: str
    execution_enabled: bool
    demo_keys_configured: bool
    auto_entry_enabled: bool
    notional_usdt: float
    max_notional_usdt: float
    open_positions_count: int
    max_open_positions: int
    daily_order_count: int
    max_daily_orders: int
    cooldown_active: bool
    take_profit_pct: float
    stop_loss_pct: float


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _float_or_none(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed == parsed else None


def _base_decision(candidate: dict[str, Any], config: DecisionConfig, *, job_id: str, job_type: str) -> dict[str, Any]:
    return {
        "created_at_utc": _utc_now_iso(),
        "decision_id": uuid4().hex,
        "job_id": job_id,
        "job_type": job_type,
        "symbol": str(candidate.get("symbol") or "").strip().upper(),
        "mode": candidate.get("mode") or "",
        "score": _float_or_none(candidate.get("score")) or 0.0,
        "side": "Sell",
        "notional_usdt": float(config.notional_usdt),
        "take_profit_pct": float(config.take_profit_pct),
        "stop_loss_pct": float(config.stop_loss_pct),
        "candidate_price": candidate.get("price") or "",
        "candidate_time_utc": candidate.get("time_utc") or "",
    }


def _finish(row: dict[str, Any], status: str, reason: str) -> dict[str, Any]:
    row["status"] = status
    row["reason"] = reason
    return row


def evaluate_signal_candidate(
    candidate: dict[str, Any],
    config: DecisionConfig,
    *,
    job_id: str,
    job_type: str,
    require_auto_entry: bool = False,
) -> dict[str, Any]:
    row = _base_decision(candidate, config, job_id=job_id, job_type=job_type)
    if row["score"] < float(config.min_score):
        return _finish(row, "rejected", "score_below_threshold")
    if row["symbol"] not in config.symbol_whitelist:
        return _finish(row, "rejected", "symbol_not_whitelisted")
    if _float_or_none(row["candidate_price"]) is None:
        return _finish(row, "rejected", "candidate_missing_price")
    if config.execution_mode != "demo":
        return _finish(row, "rejected", "execution_mode_not_demo")
    if not config.execution_enabled:
        return _finish(row, "rejected", "execution_disabled")
    if not config.demo_keys_configured:
        return _finish(row, "rejected", "missing_demo_keys")
    if float(config.notional_usdt) > float(config.max_notional_usdt):
        return _finish(row, "rejected", "notional_limit_exceeded")
    if int(config.open_positions_count) >= int(config.max_open_positions):
        return _finish(row, "rejected", "max_open_positions_reached")
    if int(config.daily_order_count) >= int(config.max_daily_orders):
        return _finish(row, "rejected", "daily_limit_reached")
    if config.cooldown_active:
        return _finish(row, "rejected", "cooldown_active")
    if require_auto_entry and not config.auto_entry_enabled:
        return _finish(row, "rejected", "auto_entry_disabled")
    return _finish(row, "qualified", "qualified")
```

- [ ] **Step 4: Run decision tests**

Run:

```powershell
..\..\.venv\Scripts\python.exe -m pytest tests/test_signal_decision.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```powershell
git add bybit_weak_intraday/signals/decision.py tests/test_signal_decision.py
git commit -m "feat: add signal decision rules"
```

## Task 5: Reusable Demo Short Placement

**Files:**
- Modify: `backend/app/execution_routes.py`
- Modify: `tests/test_execution_api.py`

- [ ] **Step 1: Write failing extraction test**

Append to `tests/test_execution_api.py`:

```python
def test_submit_demo_short_order_helper_preserves_endpoint_behavior(monkeypatch, tmp_path):
    fake_client = _patch_execution(monkeypatch, tmp_path)
    config = execution_routes.execution_config_from_settings()
    req = execution_routes.TestShortRequest(
        symbol="ENAUSDT",
        notional_usdt=10,
        take_profit_pct=0.06,
        stop_loss_pct=0.07,
    )
    event = execution_routes.demo_short_event_from_request(req, config=config)

    body = execution_routes.submit_demo_short_order(req, config=config, event=event)

    assert body["status"] == "sent"
    assert body["symbol"] == "ENAUSDT"
    assert fake_client.place_calls
    journal = read_journal(tmp_path / "execution_journal.csv")
    assert list(journal["status"]) == ["accepted", "sent"]
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
..\..\.venv\Scripts\python.exe -m pytest tests/test_execution_api.py::test_submit_demo_short_order_helper_preserves_endpoint_behavior -q
```

Expected: FAIL because `demo_short_event_from_request` and `submit_demo_short_order` do not exist.

- [ ] **Step 3: Extract helper and preserve endpoint behavior**

In `backend/app/execution_routes.py`, add:

```python
def demo_short_event_from_request(req: TestShortRequest, *, config: ExecutionConfig, event_id: str | None = None) -> dict:
    resolved_event_id = event_id or uuid4().hex
    symbol = req.symbol.strip().upper()
    return {
        "created_at_utc": _utc_now_iso(),
        "event_id": resolved_event_id,
        "order_link_id": f"bwi-demo-{resolved_event_id[:18]}",
        "mode": config.execution_mode,
        "symbol": symbol,
        "side": "Sell",
        "category": "linear",
        "requested_notional_usdt": req.notional_usdt,
    }
```

Add the reusable helper below `demo_short_event_from_request()`:

```python
def submit_demo_short_order(req: TestShortRequest, *, config: ExecutionConfig, event: dict) -> dict:
    symbol = req.symbol.strip().upper()
    order_link_id = str(event["order_link_id"])
    journal_path = journal_path_from_settings()
    decision = validate_static_demo_order_request(
        config,
        symbol=symbol,
        notional_usdt=float(req.notional_usdt),
        take_profit_pct=float(req.take_profit_pct),
        stop_loss_pct=float(req.stop_loss_pct),
        daily_test_order_count=0,
    )
    if not decision.allowed:
        _reject(decision.reason, event=event)

    with _ORDER_LOCK:
        daily_count = count_daily_test_orders(journal_path, datetime.now(timezone.utc).date())
        decision = validate_static_demo_order_request(
            config,
            symbol=symbol,
            notional_usdt=float(req.notional_usdt),
            take_profit_pct=float(req.take_profit_pct),
            stop_loss_pct=float(req.stop_loss_pct),
            daily_test_order_count=daily_count,
        )
        if not decision.allowed:
            _reject(decision.reason, event=event)

        client = demo_client_from_config(config)
        try:
            positions = client.positions()
            position_decision = validate_position_limit(config, open_positions_count=_open_positions_count(positions))
            if not position_decision.allowed:
                _reject(position_decision.reason, event=event)

            instrument_response = client.instruments_info(symbol)
            ticker_response = client.ticker(symbol)
            rules = parse_linear_instrument_rules(instrument_response)
            reference_price = _last_price(ticker_response)
            qty = quantity_from_notional(Decimal(str(req.notional_usdt)), reference_price, rules)
            take_profit, stop_loss = calculate_short_tpsl(
                reference_price,
                Decimal(str(req.take_profit_pct)),
                Decimal(str(req.stop_loss_pct)),
                rules,
            )
            _append_event(
                event,
                qty=_decimal_to_str(qty),
                take_profit=_decimal_to_str(take_profit),
                stop_loss=_decimal_to_str(stop_loss),
                status="accepted",
                reason="order_submission_started",
            )
            response = client.place_short_market_order(
                symbol=symbol,
                qty=_decimal_to_str(qty),
                take_profit=_decimal_to_str(take_profit),
                stop_loss=_decimal_to_str(stop_loss),
                order_link_id=order_link_id,
            )
        except BybitDemoAPIError as exc:
            _append_event(
                event,
                status="error",
                reason="bybit_api_error",
                bybit_ret_code=exc.ret_code,
                bybit_ret_msg=exc.ret_msg,
            )
            raise HTTPException(status_code=502, detail=_bybit_error_detail(exc)) from exc
        except (ValueError, KeyError, TypeError, InvalidOperation) as exc:
            _append_event(event, status="error", reason="order_preparation_error", bybit_ret_msg=str(exc))
            raise HTTPException(status_code=400, detail={"status": "error", "reason": "order_preparation_error"}) from exc
        except requests.RequestException as exc:
            _append_event(event, status="error", reason="bybit_transport_error", bybit_ret_msg="request_failed")
            raise HTTPException(status_code=502, detail=_transport_error_detail()) from exc

        _append_event(
            event,
            qty=_decimal_to_str(qty),
            take_profit=_decimal_to_str(take_profit),
            stop_loss=_decimal_to_str(stop_loss),
            status="sent",
            reason="allowed",
            bybit_ret_code=response.get("retCode", ""),
            bybit_ret_msg=response.get("retMsg", ""),
        )
    return {
        "status": "sent",
        "symbol": symbol,
        "qty": _decimal_to_str(qty),
        "take_profit": _decimal_to_str(take_profit),
        "stop_loss": _decimal_to_str(stop_loss),
        "order_link_id": order_link_id,
        "bybit_response": response,
    }
```

Replace the current body of `place_test_short()` with:

```python
    _require_execution_api_token(x_bwi_execution_token)
    config = execution_config_from_settings()
    event = demo_short_event_from_request(req, config=config)
    return submit_demo_short_order(req, config=config, event=event)
```

- [ ] **Step 4: Run execution tests**

Run:

```powershell
..\..\.venv\Scripts\python.exe -m pytest tests/test_execution_api.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```powershell
git add backend/app/execution_routes.py tests/test_execution_api.py
git commit -m "refactor: extract reusable demo short placement"
```

## Task 6: Signal Backend API

**Files:**
- Modify: `backend/app/settings.py`
- Create: `backend/app/signal_routes.py`
- Modify: `backend/app/main.py`
- Create: `tests/test_signal_api.py`
- Modify: `tests/test_ui_summary.py`

- [ ] **Step 1: Write failing API tests**

Create `tests/test_signal_api.py` with focused API tests:

```python
from __future__ import annotations

import pandas as pd
from fastapi.testclient import TestClient

from backend.app import job_store, main, signal_routes
from bybit_weak_intraday.signals.journal import read_decision_journal

client = TestClient(main.app)
TOKEN = "signal-token"


def _headers(token: str = TOKEN) -> dict[str, str]:
    return {"X-BWI-Execution-Token": token}


def _patch_signal_settings(monkeypatch, tmp_path, **overrides):
    monkeypatch.setattr(signal_routes.settings, "execution_api_token", TOKEN)
    monkeypatch.setattr(signal_routes.settings, "signal_decision_journal_path", tmp_path / "signal_decisions.csv")
    monkeypatch.setattr(signal_routes.settings, "signal_min_score", 9.0)
    monkeypatch.setattr(signal_routes.settings, "signal_auto_entry_enabled", False)
    monkeypatch.setattr(signal_routes.settings, "signal_default_notional_usdt", 25.0)
    monkeypatch.setattr(signal_routes.settings, "signal_take_profit_pct", 0.06)
    monkeypatch.setattr(signal_routes.settings, "signal_stop_loss_pct", 0.07)
    monkeypatch.setattr(signal_routes.settings, "telegram_enabled", False)
    monkeypatch.setattr(signal_routes.settings, "telegram_bot_token", "")
    monkeypatch.setattr(signal_routes.settings, "telegram_chat_id", "")
    for key, value in overrides.items():
        monkeypatch.setattr(signal_routes.settings, key, value)


def test_telegram_status_redacts_config(monkeypatch, tmp_path):
    _patch_signal_settings(
        monkeypatch,
        tmp_path,
        telegram_enabled=True,
        telegram_bot_token="secret-token",
        telegram_chat_id="123",
    )

    response = client.get("/signals/telegram/status")

    assert response.status_code == 200
    assert response.json() == {"enabled": True, "bot_token_configured": True, "chat_id_configured": True}
    assert "secret-token" not in response.text
    assert "123" not in response.text


def test_telegram_test_requires_execution_token(monkeypatch, tmp_path):
    _patch_signal_settings(monkeypatch, tmp_path)

    response = client.post("/signals/telegram/test")

    assert response.status_code == 403


def test_evaluate_latest_writes_decision(monkeypatch, tmp_path):
    _patch_signal_settings(monkeypatch, tmp_path)
    monkeypatch.setattr(
        signal_routes,
        "load_latest_candidates",
        lambda max_candidates=20: (
            {"job_id": "job-1", "job_type": "causal_scan"},
            pd.DataFrame([{"symbol": "ENAUSDT", "mode": "weak", "score": 10, "price": 0.1, "time_utc": "2026-03-18T10:00:00+00:00"}]),
        ),
    )
    monkeypatch.setattr(signal_routes, "execution_config_from_settings", lambda: signal_routes.ExecutionConfig(
        execution_mode="demo",
        execution_enabled=True,
        api_key="key",
        api_secret="secret",
        base_url=signal_routes.DEMO_BASE_URL,
        symbol_whitelist={"ENAUSDT"},
        max_demo_notional_usdt=25.0,
        max_open_positions=1,
        max_daily_test_orders=3,
    ))
    monkeypatch.setattr(signal_routes, "current_open_positions_count", lambda config: 0)
    monkeypatch.setattr(signal_routes, "count_daily_test_orders", lambda path, day: 0)

    response = client.post("/signals/evaluate-latest", headers=_headers(), json={"max_candidates": 20, "notify": False})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "evaluated"
    assert body["decisions"][0]["status"] == "qualified"
    frame = read_decision_journal(tmp_path / "signal_decisions.csv")
    assert frame.loc[0, "symbol"] == "ENAUSDT"


def test_demo_auto_entry_rejects_when_disabled(monkeypatch, tmp_path):
    _patch_signal_settings(monkeypatch, tmp_path, signal_auto_entry_enabled=False)

    response = client.post("/signals/demo-auto-entry", headers=_headers(), json={"max_candidates": 20})

    assert response.status_code == 400
    assert response.json()["detail"]["reason"] == "auto_entry_disabled"
```

- [ ] **Step 2: Run API tests to verify failure**

Run:

```powershell
..\..\.venv\Scripts\python.exe -m pytest tests/test_signal_api.py -q
```

Expected: FAIL because `backend.app.signal_routes` does not exist and settings fields are missing.

- [ ] **Step 3: Add settings**

In `backend/app/settings.py`, add:

```python
signal_min_score: float = 9.0
signal_auto_entry_enabled: bool = False
signal_default_notional_usdt: float = 25.0
signal_take_profit_pct: float = 0.06
signal_stop_loss_pct: float = 0.07
signal_cooldown_minutes: int = 60
signal_decision_journal_path: Path = Path("data/signal_decisions.csv")
telegram_enabled: bool = False
telegram_bot_token: str = ""
telegram_chat_id: str = ""
```

Also ensure the parent directory exists:

```python
settings.signal_decision_journal_path.parent.mkdir(parents=True, exist_ok=True)
```

Update `tests/test_ui_summary.py` defaults test to assert:

```python
assert settings.signal_decision_journal_path == Path("data/signal_decisions.csv")
assert settings.signal_auto_entry_enabled is False
assert settings.telegram_enabled is False
```

- [ ] **Step 4: Implement signal routes**

Create `backend/app/signal_routes.py` with:

```python
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

from bybit_weak_intraday.notifications.telegram import TelegramConfig, send_telegram_message, telegram_status
from bybit_weak_intraday.signals.candidates import build_scanner_watchlist, select_latest_scanner_job
from bybit_weak_intraday.signals.decision import DecisionConfig, evaluate_signal_candidate
from bybit_weak_intraday.signals.journal import append_decision_event, read_decision_journal_tail

from .execution_routes import (
    DEMO_BASE_URL,
    ExecutionConfig,
    TestShortRequest,
    count_daily_test_orders,
    demo_short_event_from_request,
    execution_config_from_settings,
    journal_path_from_settings,
    submit_demo_short_order,
    _open_positions_count,
    _require_execution_api_token,
    demo_client_from_config,
)
from .job_store import job_dir, list_jobs
from .settings import settings

router = APIRouter(prefix="/signals", tags=["signals"])


class EvaluateLatestRequest(BaseModel):
    max_candidates: int = Field(default=20, ge=1, le=200)
    notify: bool = True


class DemoAutoEntryRequest(EvaluateLatestRequest):
    dry_run: bool = False
```

After the request models, add the helper functions below:

```python
def decision_journal_path_from_settings() -> Path:
    return Path(settings.signal_decision_journal_path)


def telegram_config_from_settings() -> TelegramConfig:
    return TelegramConfig(
        enabled=bool(settings.telegram_enabled),
        bot_token=settings.telegram_bot_token,
        chat_id=settings.telegram_chat_id,
    )


def current_open_positions_count(config: ExecutionConfig) -> int:
    if config.execution_mode != "demo" or not config.api_key.strip() or not config.api_secret.strip():
        return 0
    return _open_positions_count(demo_client_from_config(config).positions())


def load_latest_candidates(max_candidates: int = 20) -> tuple[dict | None, pd.DataFrame]:
    jobs = list_jobs()
    latest = select_latest_scanner_job(jobs)
    if not latest:
        return None, pd.DataFrame()
    job_id = latest["job_id"]
    job_type = latest.get("job_type") or "scan"
    directory = job_dir(job_id)
    if job_type == "causal_scan":
        signals = pd.read_csv(directory / "signals.csv") if (directory / "signals.csv").exists() else pd.DataFrame()
        evaluations = pd.read_csv(directory / "evaluations.csv") if (directory / "evaluations.csv").exists() else pd.DataFrame()
        return latest, build_scanner_watchlist(job_type, signals=signals, evaluations=evaluations, max_rows=max_candidates)
    trades = pd.read_csv(directory / "trades.csv") if (directory / "trades.csv").exists() else pd.DataFrame()
    return latest, build_scanner_watchlist(job_type, trades=trades, max_rows=max_candidates)

def _today_utc():
    return datetime.now(timezone.utc).date()


def _cooldown_active(symbol: str) -> bool:
    cooldown_minutes = int(settings.signal_cooldown_minutes)
    if cooldown_minutes <= 0:
        return False
    frame = read_decision_journal_tail(decision_journal_path_from_settings(), 1000)
    if frame.empty:
        return False
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=cooldown_minutes)
    symbol_rows = frame[frame["symbol"].astype(str).str.upper() == symbol.upper()]
    for row in symbol_rows.to_dict(orient="records"):
        if row.get("status") not in {"entered", "qualified"}:
            continue
        created = str(row.get("created_at_utc") or "")
        try:
            created_at = datetime.fromisoformat(created.replace("Z", "+00:00"))
        except ValueError:
            continue
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        if created_at.astimezone(timezone.utc) >= cutoff:
            return True
    return False


def _decision_config(config: ExecutionConfig, *, symbol: str) -> DecisionConfig:
    return DecisionConfig(
        min_score=float(settings.signal_min_score),
        symbol_whitelist=set(config.symbol_whitelist),
        execution_mode=config.execution_mode,
        execution_enabled=bool(config.execution_enabled),
        demo_keys_configured=bool(config.api_key.strip() and config.api_secret.strip()),
        auto_entry_enabled=bool(settings.signal_auto_entry_enabled),
        notional_usdt=float(settings.signal_default_notional_usdt),
        max_notional_usdt=float(config.max_demo_notional_usdt),
        open_positions_count=current_open_positions_count(config),
        max_open_positions=int(config.max_open_positions),
        daily_order_count=count_daily_test_orders(journal_path_from_settings(), _today_utc()),
        max_daily_orders=int(config.max_daily_test_orders),
        cooldown_active=_cooldown_active(symbol),
        take_profit_pct=float(settings.signal_take_profit_pct),
        stop_loss_pct=float(settings.signal_stop_loss_pct),
    )


def _public_decision(row: dict) -> dict:
    return {
        "decision_id": row.get("decision_id", ""),
        "symbol": row.get("symbol", ""),
        "status": row.get("status", ""),
        "reason": row.get("reason", ""),
        "order_link_id": row.get("order_link_id", ""),
        "execution_status": row.get("execution_status", ""),
        "telegram_status": row.get("telegram_status", ""),
        "telegram_error": row.get("telegram_error", ""),
    }


def _decision_message(row: dict) -> str:
    title = "Demo order sent" if row.get("status") == "entered" else "Signal decision"
    return (
        f"{title}\n"
        f"{row.get('symbol', '')} | {row.get('mode', '')} | score {row.get('score', '')}\n"
        f"Reason: {row.get('reason', '')}\n"
        f"Notional: ${float(row.get('notional_usdt') or 0):.2f} | "
        f"TP: {float(row.get('take_profit_pct') or 0):.2%} | "
        f"SL: {float(row.get('stop_loss_pct') or 0):.2%}"
    )


def _append_and_notify(row: dict, *, notify: bool) -> dict:
    if notify:
        result = send_telegram_message(telegram_config_from_settings(), _decision_message(row))
        row["telegram_status"] = result.status
        row["telegram_error"] = result.error
    else:
        row["telegram_status"] = "disabled"
        row["telegram_error"] = ""
    append_decision_event(decision_journal_path_from_settings(), row)
    return row


def _no_candidates_decision(job: dict | None) -> dict:
    return {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "decision_id": f"no-candidates-{int(datetime.now(timezone.utc).timestamp())}",
        "job_id": (job or {}).get("job_id", ""),
        "job_type": (job or {}).get("job_type", ""),
        "status": "skipped",
        "reason": "no_scanner_candidates",
        "side": "Sell",
        "details": "latest scanner job has no candidate rows",
    }


def _reason_from_http_exception(exc: HTTPException) -> str:
    if isinstance(exc.detail, dict):
        return str(exc.detail.get("reason") or exc.detail.get("status") or "order_rejected")
    return "order_rejected"


@router.get("/telegram/status")
def signal_telegram_status() -> dict:
    return telegram_status(telegram_config_from_settings())


@router.post("/telegram/test")
def signal_telegram_test(x_bwi_execution_token: str | None = Header(default=None, alias="X-BWI-Execution-Token")) -> dict:
    _require_execution_api_token(x_bwi_execution_token)
    result = send_telegram_message(telegram_config_from_settings(), "Bybit Weak Intraday Lab test message")
    return {"status": result.status, "error": result.error}


@router.get("/decisions")
def signal_decisions(limit: int = Query(default=100, ge=1, le=500)) -> dict:
    frame = read_decision_journal_tail(decision_journal_path_from_settings(), limit)
    rows = [] if frame.empty else frame.to_dict(orient="records")
    return {"rows": rows, "limit": limit, "count": len(rows)}


@router.post("/evaluate-latest")
def evaluate_latest_signals(
    req: EvaluateLatestRequest,
    x_bwi_execution_token: str | None = Header(default=None, alias="X-BWI-Execution-Token"),
) -> dict:
    _require_execution_api_token(x_bwi_execution_token)
    job, candidates = load_latest_candidates(req.max_candidates)
    if candidates.empty:
        row = _append_and_notify(_no_candidates_decision(job), notify=req.notify)
        return {"status": "evaluated", "count": 1, "decisions": [_public_decision(row)]}

    config = execution_config_from_settings()
    decisions = []
    job_id = str((job or {}).get("job_id") or "")
    job_type = str((job or {}).get("job_type") or "")
    for candidate in candidates.to_dict(orient="records"):
        symbol = str(candidate.get("symbol") or "").strip().upper()
        decision = evaluate_signal_candidate(
            candidate,
            _decision_config(config, symbol=symbol),
            job_id=job_id,
            job_type=job_type,
        )
        decisions.append(_public_decision(_append_and_notify(decision, notify=req.notify)))
    return {"status": "evaluated", "count": len(decisions), "decisions": decisions}


@router.post("/demo-auto-entry")
def demo_auto_entry(
    req: DemoAutoEntryRequest,
    x_bwi_execution_token: str | None = Header(default=None, alias="X-BWI-Execution-Token"),
) -> dict:
    _require_execution_api_token(x_bwi_execution_token)
    if not req.dry_run and not settings.signal_auto_entry_enabled:
        raise HTTPException(status_code=400, detail={"status": "rejected", "reason": "auto_entry_disabled"})

    job, candidates = load_latest_candidates(req.max_candidates)
    if candidates.empty:
        row = _append_and_notify(_no_candidates_decision(job), notify=req.notify)
        return {"status": "evaluated", "count": 1, "decisions": [_public_decision(row)]}

    config = execution_config_from_settings()
    decisions = []
    entry_already_used = False
    job_id = str((job or {}).get("job_id") or "")
    job_type = str((job or {}).get("job_type") or "")
    for candidate in candidates.to_dict(orient="records"):
        symbol = str(candidate.get("symbol") or "").strip().upper()
        decision = evaluate_signal_candidate(
            candidate,
            _decision_config(config, symbol=symbol),
            job_id=job_id,
            job_type=job_type,
            require_auto_entry=not req.dry_run,
        )
        if entry_already_used and decision.get("status") == "qualified":
            decision["status"] = "skipped"
            decision["reason"] = "already_entered_this_run"
        elif decision.get("status") == "qualified" and req.dry_run:
            decision["status"] = "skipped"
            decision["reason"] = "dry_run"
            entry_already_used = True
        elif decision.get("status") == "qualified":
            order_req = TestShortRequest(
                symbol=symbol,
                notional_usdt=float(settings.signal_default_notional_usdt),
                take_profit_pct=float(settings.signal_take_profit_pct),
                stop_loss_pct=float(settings.signal_stop_loss_pct),
            )
            event = demo_short_event_from_request(order_req, config=config, event_id=str(decision["decision_id"]))
            try:
                order_result = submit_demo_short_order(order_req, config=config, event=event)
                decision["status"] = "entered"
                decision["reason"] = "order_sent"
                decision["order_link_id"] = order_result.get("order_link_id", "")
                decision["execution_status"] = order_result.get("status", "")
            except HTTPException as exc:
                decision["status"] = "error" if exc.status_code >= 500 else "rejected"
                decision["reason"] = _reason_from_http_exception(exc)
                decision["execution_status"] = "error"
            entry_already_used = True
        decisions.append(_public_decision(_append_and_notify(decision, notify=req.notify)))

    response_status = "entered" if any(row["status"] == "entered" for row in decisions) else "evaluated"
    return {"status": response_status, "count": len(decisions), "decisions": decisions}
```

In `backend/app/main.py`, add:

```python
from .signal_routes import router as signal_router
app.include_router(signal_router)
```

- [ ] **Step 5: Run API tests**

Run:

```powershell
..\..\.venv\Scripts\python.exe -m pytest tests/test_signal_api.py tests/test_ui_summary.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```powershell
git add backend/app/settings.py backend/app/signal_routes.py backend/app/main.py tests/test_signal_api.py tests/test_ui_summary.py
git commit -m "feat: add signal decision api"
```

## Task 7: Streamlit Signal Decisions UI

**Files:**
- Modify: `ui/app_navigation.py`
- Modify: `ui/streamlit_app.py`
- Modify: `tests/test_app_navigation.py`
- Modify: `tests/test_streamlit_demo_execution_helpers.py`

- [ ] **Step 1: Write failing UI tests**

Update `tests/test_app_navigation.py`:

```python
def test_nav_pages_match_clean_monitor_design() -> None:
    assert NAV_PAGES == ("Monitor", "Reports", "Scanner Jobs", "Signal Decisions", "Execution History", "Settings")
```

Append to `tests/test_streamlit_demo_execution_helpers.py`:

```python
def test_signal_decisions_page_owns_decision_controls() -> None:
    source = Path("ui/streamlit_app.py").read_text(encoding="utf-8")
    page_source = _function_source("render_signal_decisions_page")
    settings_source = _function_source("render_settings_page")

    assert "render_signal_decisions_page" in source
    assert "/signals/evaluate-latest" in page_source
    assert "/signals/demo-auto-entry" in page_source
    assert "/signals/decisions?limit=100" in page_source
    assert "Evaluate latest" in page_source
    assert "Demo auto-entry" in page_source
    assert "Dry-run auto-entry" in page_source
    assert "/signals/telegram/status" in settings_source
    assert "/signals/telegram/test" in settings_source
```

- [ ] **Step 2: Run UI tests to verify failure**

Run:

```powershell
..\..\.venv\Scripts\python.exe -m pytest tests/test_app_navigation.py tests/test_streamlit_demo_execution_helpers.py::test_signal_decisions_page_owns_decision_controls -q
```

Expected: FAIL because nav page and renderer do not exist.

- [ ] **Step 3: Add navigation and page**

In `ui/app_navigation.py`, update:

```python
NAV_PAGES = ("Monitor", "Reports", "Scanner Jobs", "Signal Decisions", "Execution History", "Settings")
```

In `ui/streamlit_app.py`, add:

```python
def render_signal_decisions_page(api_url: str, execution_token: str) -> None:
    st.header("Signal Decisions")
    c1, c2, c3 = st.columns(3)
    if c1.button("Evaluate latest", type="primary"):
        try:
            response = api_post(
                "/signals/evaluate-latest",
                {"max_candidates": 20, "notify": True},
                api_url,
                token=execution_token,
            )
            st.success("Latest candidates evaluated.")
            st.json(response.json())
        except Exception as exc:
            st.error(f"Signal evaluation failed: {_safe_error(exc, execution_token)}")

    if c2.button("Dry-run auto-entry"):
        try:
            response = api_post(
                "/signals/demo-auto-entry",
                {"max_candidates": 20, "notify": True, "dry_run": True},
                api_url,
                token=execution_token,
            )
            st.success("Dry-run auto-entry evaluated.")
            st.json(response.json())
        except Exception as exc:
            st.error(f"Dry-run auto-entry failed: {_safe_error(exc, execution_token)}")

    if c3.button("Demo auto-entry"):
        try:
            response = api_post(
                "/signals/demo-auto-entry",
                {"max_candidates": 20, "notify": True, "dry_run": False},
                api_url,
                token=execution_token,
            )
            st.success("Demo auto-entry completed.")
            st.json(response.json())
        except Exception as exc:
            st.error(f"Demo auto-entry failed: {_safe_error(exc, execution_token)}")

    payload, error = api_json_or_error("/signals/decisions?limit=100", api_url)
    if error:
        st.warning(f"Signal decisions unavailable: {error}")
        return
    rows = payload.get("rows") if isinstance(payload, dict) else []
    frame = _frame_from_rows(rows)
    if frame.empty:
        st.info("No signal decisions yet.")
        return
    st.dataframe(frame, use_container_width=True, hide_index=True)
```

In the main router:

```python
elif page == "Signal Decisions":
    render_signal_decisions_page(api_url, execution_token)
```

In `render_settings_page()`, add Telegram status/test section:

```python
    st.subheader("Telegram")
    telegram_payload, telegram_error = api_json_or_error("/signals/telegram/status", api_url)
    if telegram_error:
        st.warning(f"Telegram status unavailable: {telegram_error}")
    else:
        st.json(telegram_payload)
    if st.button("Send Telegram test message"):
        try:
            response = api_post("/signals/telegram/test", {}, api_url, token=execution_token)
            st.success("Telegram test requested.")
            st.json(response.json())
        except Exception as exc:
            st.error(f"Telegram test failed: {_safe_error(exc, execution_token)}")
```

- [ ] **Step 4: Run UI tests**

Run:

```powershell
..\..\.venv\Scripts\python.exe -m pytest tests/test_app_navigation.py tests/test_streamlit_demo_execution_helpers.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```powershell
git add ui/app_navigation.py ui/streamlit_app.py tests/test_app_navigation.py tests/test_streamlit_demo_execution_helpers.py
git commit -m "feat: add signal decisions ui"
```

## Task 8: Full Verification and Push

**Files:**
- Verify all changed files.

- [ ] **Step 1: Run full test suite**

Run:

```powershell
..\..\.venv\Scripts\python.exe -m pytest -q
```

Expected: all tests PASS.

- [ ] **Step 2: Check branch status**

Run:

```powershell
git status --short --branch
git log --oneline origin/main..HEAD
```

Expected: clean tree with feature commits ahead of `origin/main`.

- [ ] **Step 3: Push branch**

Run:

```powershell
git push -u origin feature/signal-decision-demo-auto-entry
```

Expected: branch pushed.

- [ ] **Step 4: Create PR**

Run:

```powershell
gh pr create --base main --head feature/signal-decision-demo-auto-entry --title "Add signal decision demo auto-entry" --body "## Summary
- add signal decision journal and rules
- add demo auto-entry API using existing demo execution safety
- add outbound Telegram notifications and Signal Decisions UI

## Test Plan
- [x] pytest -q"
```

Expected: PR URL is printed.

## Self-Review Checklist

- Spec coverage: decision journal Task 1, Telegram Task 2, candidates Task 3, decision rules Task 4, reusable execution Task 5, API Task 6, UI Task 7, verification Task 8.
- Telegram remains outbound-only; no command handling is planned.
- Auto-entry remains demo-only and disabled by default.
- Existing execution safety remains authoritative through Task 5 extraction.
- No database or scheduler is included.
