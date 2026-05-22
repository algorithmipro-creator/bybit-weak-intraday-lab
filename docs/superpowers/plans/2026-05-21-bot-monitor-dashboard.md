# Bot Monitor Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the selected Executive Overview first-screen Bot Monitor for Bybit Demo connection, account, positions, orders, execution history, and scanner watchlist.

**Architecture:** Add one read-only backend journal endpoint, then move UI data shaping into a small pure helper module. Streamlit renders the monitor from normalized data and leaves the existing Jobs/results area below as a technical archive.

**Tech Stack:** Python, FastAPI, Pydantic settings, pandas, Streamlit, Plotly, pytest.

---

## File Structure

- Modify `backend/app/execution_routes.py`
  - Add `GET /execution/demo/journal?limit=50`.
  - Reuse existing execution token and demo-read safety checks.
  - Read only from `execution_journal_path`.

- Create `ui/bot_monitor.py`
  - Pure data helpers with no Streamlit imports.
  - Normalize wallet, positions, open orders, journal rows, and scanner watchlist rows.
  - Keep parsing defensive for empty strings and missing Bybit fields.

- Modify `ui/streamlit_app.py`
  - Import monitor helpers.
  - Render `Bot Monitor` above `Jobs`.
  - Keep the demo test-short form visible but secondary.
  - Keep existing job launch/results behavior.

- Modify `tests/test_execution_api.py`
  - Add backend journal endpoint tests.

- Create `tests/test_bot_monitor.py`
  - Add tests for the pure monitor helpers.

- Modify `tests/test_streamlit_demo_execution_helpers.py`
  - Assert Bot Monitor appears before Jobs.

---

## Task 1: Backend Journal Endpoint

**Files:**
- Modify: `tests/test_execution_api.py`
- Modify: `backend/app/execution_routes.py`

- [ ] **Step 1: Write failing backend tests**

In `tests/test_execution_api.py`, change the journal import near the top from:

```python
from bybit_weak_intraday.execution.journal import count_daily_test_orders, read_journal
```

to:

```python
from bybit_weak_intraday.execution.journal import append_journal_event, count_daily_test_orders, read_journal
```

Add these tests after `test_execution_status_reports_token_configured_without_exposing_token`:

```python
def test_journal_rejects_missing_token_before_reading_journal(monkeypatch, tmp_path):
    fake_client = _patch_execution(monkeypatch, tmp_path)

    response = client.get("/execution/demo/journal")

    assert response.status_code == 403
    assert response.json()["detail"]["reason"] == "invalid_execution_api_token"
    assert fake_client.client_factory_called["value"] is False


def test_journal_rejects_invalid_token_before_reading_journal(monkeypatch, tmp_path):
    fake_client = _patch_execution(monkeypatch, tmp_path)

    response = client.get("/execution/demo/journal", headers=_auth_headers("wrong-token"))

    assert response.status_code == 403
    assert response.json()["detail"]["reason"] == "invalid_execution_api_token"
    assert fake_client.client_factory_called["value"] is False


def test_journal_returns_recent_rows_newest_first(monkeypatch, tmp_path):
    _patch_execution(monkeypatch, tmp_path)
    journal_path = tmp_path / "execution_journal.csv"
    append_journal_event(
        journal_path,
        {
            "created_at_utc": "2026-05-21T10:00:00+00:00",
            "event_id": "event-1",
            "order_link_id": "bwi-demo-1",
            "mode": "demo",
            "symbol": "ENAUSDT",
            "side": "Sell",
            "status": "accepted",
            "reason": "order_submission_started",
        },
    )
    append_journal_event(
        journal_path,
        {
            "created_at_utc": "2026-05-21T10:01:00+00:00",
            "event_id": "event-2",
            "order_link_id": "bwi-demo-2",
            "mode": "demo",
            "symbol": "JTOUSDT",
            "side": "Sell",
            "status": "sent",
            "reason": "allowed",
        },
    )
    append_journal_event(
        journal_path,
        {
            "created_at_utc": "2026-05-21T10:02:00+00:00",
            "event_id": "event-3",
            "order_link_id": "bwi-demo-3",
            "mode": "demo",
            "symbol": "ENAUSDT",
            "side": "Sell",
            "status": "rejected",
            "reason": "open_position_limit_reached",
        },
    )

    response = client.get("/execution/demo/journal?limit=2", headers=_auth_headers())

    assert response.status_code == 200
    body = response.json()
    assert body["limit"] == 2
    assert body["count"] == 2
    assert [row["event_id"] for row in body["rows"]] == ["event-3", "event-2"]
    assert body["rows"][0]["reason"] == "open_position_limit_reached"


def test_journal_clamps_limit_and_does_not_expose_secrets(monkeypatch, tmp_path):
    _patch_execution(monkeypatch, tmp_path, execution_api_token=EXECUTION_TOKEN)
    journal_path = tmp_path / "execution_journal.csv"
    append_journal_event(
        journal_path,
        {
            "created_at_utc": "2026-05-21T10:00:00+00:00",
            "event_id": "event-1",
            "order_link_id": "bwi-demo-1",
            "mode": "demo",
            "symbol": "ENAUSDT",
            "side": "Sell",
            "status": "sent",
            "reason": "allowed",
            "bybit_ret_msg": "OK",
        },
    )

    too_large = client.get("/execution/demo/journal?limit=9999", headers=_auth_headers())
    too_small = client.get("/execution/demo/journal?limit=0", headers=_auth_headers())

    assert too_large.status_code == 200
    assert too_large.json()["limit"] == 500
    assert too_large.json()["count"] == 1
    assert too_small.status_code == 200
    assert too_small.json()["limit"] == 1
    assert EXECUTION_TOKEN not in str(too_large.json())
    assert "secret" not in str(too_large.json())
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
.\.venv\Scripts\pytest.exe tests/test_execution_api.py::test_journal_rejects_missing_token_before_reading_journal tests/test_execution_api.py::test_journal_rejects_invalid_token_before_reading_journal tests/test_execution_api.py::test_journal_returns_recent_rows_newest_first tests/test_execution_api.py::test_journal_clamps_limit_and_does_not_expose_secrets -q
```

Expected: all four tests fail with `404` because `/execution/demo/journal` is not registered.

- [ ] **Step 3: Implement the journal endpoint**

In `backend/app/execution_routes.py`, add `Query` to the FastAPI import:

```python
from fastapi import APIRouter, Header, HTTPException, Query
```

Add this endpoint after `demo_open_orders` and before `place_test_short`:

```python
@router.get("/journal")
def demo_journal(
    limit: int = Query(default=50),
    x_bwi_execution_token: str | None = Header(default=None, alias="X-BWI-Execution-Token"),
) -> dict:
    _require_execution_api_token(x_bwi_execution_token)
    config = execution_config_from_settings()
    _require_demo_read_config(config)
    clamped_limit = max(1, min(int(limit), 500))
    journal = read_journal(journal_path_from_settings())
    if journal.empty:
        rows: list[dict] = []
    else:
        rows = journal.tail(clamped_limit).iloc[::-1].fillna("").to_dict(orient="records")
    return {"rows": rows, "limit": clamped_limit, "count": len(rows)}
```

- [ ] **Step 4: Run endpoint tests to verify they pass**

Run:

```powershell
.\.venv\Scripts\pytest.exe tests/test_execution_api.py::test_journal_rejects_missing_token_before_reading_journal tests/test_execution_api.py::test_journal_rejects_invalid_token_before_reading_journal tests/test_execution_api.py::test_journal_returns_recent_rows_newest_first tests/test_execution_api.py::test_journal_clamps_limit_and_does_not_expose_secrets -q
```

Expected: `4 passed`.

- [ ] **Step 5: Commit backend journal endpoint**

Run:

```powershell
git add backend/app/execution_routes.py tests/test_execution_api.py
git commit -m "feat: expose demo execution journal"
```

---

## Task 2: Pure Bot Monitor Helpers

**Files:**
- Create: `ui/bot_monitor.py`
- Create: `tests/test_bot_monitor.py`

- [ ] **Step 1: Write failing helper tests**

Create `tests/test_bot_monitor.py` with:

```python
from __future__ import annotations

import pandas as pd
import pytest

from ui.bot_monitor import (
    build_scanner_watchlist,
    normalize_open_orders,
    normalize_positions,
    result_rows,
    safe_float,
    select_latest_scanner_job,
    summarize_wallet,
)


def test_safe_float_handles_numbers_strings_and_missing_values() -> None:
    assert safe_float("12.5") == 12.5
    assert safe_float(7) == 7.0
    assert safe_float("") is None
    assert safe_float(None) is None
    assert safe_float("not-a-number") is None


def test_result_rows_extracts_bybit_result_list() -> None:
    assert result_rows({"result": {"list": [{"symbol": "ENAUSDT"}]}}) == [{"symbol": "ENAUSDT"}]
    assert result_rows({"result": {"list": None}}) == []
    assert result_rows(None) == []


def test_summarize_wallet_extracts_account_numbers() -> None:
    payload = {
        "result": {
            "list": [
                {
                    "totalEquity": "1024.80",
                    "totalWalletBalance": "1025.22",
                    "totalAvailableBalance": "1018.12",
                    "totalInitialMargin": "6.68",
                    "totalPerpUPL": "-0.42",
                    "coin": [{"coin": "USDT", "walletBalance": "1025.22"}],
                }
            ]
        }
    }

    summary = summarize_wallet(payload)

    assert summary == {
        "equity": 1024.80,
        "wallet_balance": 1025.22,
        "available_balance": 1018.12,
        "margin_used": 6.68,
        "unrealized_pnl": -0.42,
    }


def test_summarize_wallet_handles_missing_fields() -> None:
    assert summarize_wallet({"result": {"list": [{}]}}) == {
        "equity": None,
        "wallet_balance": None,
        "available_balance": None,
        "margin_used": None,
        "unrealized_pnl": None,
    }


def test_normalize_positions_derives_pnl_pct_and_infers_tpsl_from_orders() -> None:
    positions = {
        "result": {
            "list": [
                {
                    "symbol": "ENAUSDT",
                    "side": "Sell",
                    "size": "95",
                    "avgPrice": "0.10441",
                    "markPrice": "0.10485",
                    "unrealisedPnl": "-0.42",
                    "positionValue": "104.41",
                    "leverage": "5",
                    "positionIM": "20.88",
                    "liqPrice": "",
                }
            ]
        }
    }
    orders = {
        "result": {
            "list": [
                {
                    "symbol": "ENAUSDT",
                    "side": "Buy",
                    "orderType": "Market",
                    "qty": "95",
                    "triggerPrice": "0.09814",
                    "stopOrderType": "TakeProfit",
                    "orderStatus": "Untriggered",
                },
                {
                    "symbol": "ENAUSDT",
                    "side": "Buy",
                    "orderType": "Market",
                    "qty": "95",
                    "triggerPrice": "0.11172",
                    "stopOrderType": "StopLoss",
                    "orderStatus": "Untriggered",
                },
            ]
        }
    }

    rows = normalize_positions(positions, orders)

    assert len(rows) == 1
    row = rows[0]
    assert row["symbol"] == "ENAUSDT"
    assert row["side"] == "Sell"
    assert row["size"] == 95.0
    assert row["entry_price"] == 0.10441
    assert row["mark_price"] == 0.10485
    assert row["unrealized_pnl"] == -0.42
    assert row["pnl_pct"] == pytest.approx(-0.0040226032)
    assert row["leverage"] == 5.0
    assert row["margin"] == 20.88
    assert row["take_profit"] == 0.09814
    assert row["stop_loss"] == 0.11172


def test_normalize_open_orders_keeps_trigger_prices_and_statuses() -> None:
    payload = {
        "result": {
            "list": [
                {
                    "symbol": "ENAUSDT",
                    "side": "Buy",
                    "orderType": "Market",
                    "qty": "95",
                    "price": "",
                    "triggerPrice": "0.09814",
                    "stopOrderType": "TakeProfit",
                    "orderStatus": "Untriggered",
                    "createdTime": "1779365707000",
                }
            ]
        }
    }

    rows = normalize_open_orders(payload)

    assert rows == [
        {
            "symbol": "ENAUSDT",
            "side": "Buy",
            "order_type": "Market",
            "qty": 95.0,
            "price": None,
            "trigger_price": 0.09814,
            "stop_order_type": "TakeProfit",
            "status": "Untriggered",
            "created_time": "2026-05-21T11:35:07+00:00",
        }
    ]


def test_select_latest_scanner_job_prefers_latest_causal_scan() -> None:
    jobs = [
        {"job_id": "scan-new", "job_type": "scan", "status": "done", "updated_at": "2026-05-21T12:00:00+00:00"},
        {"job_id": "causal-old", "job_type": "causal_scan", "status": "done", "updated_at": "2026-05-21T10:00:00+00:00"},
    ]

    assert select_latest_scanner_job(jobs)["job_id"] == "causal-old"


def test_select_latest_scanner_job_falls_back_to_regular_scan() -> None:
    jobs = [
        {"job_id": "scan-old", "job_type": "scan", "status": "done", "updated_at": "2026-05-21T09:00:00+00:00"},
        {"job_id": "scan-new", "job_type": "scan", "status": "done", "updated_at": "2026-05-21T12:00:00+00:00"},
        {"job_id": "running-causal", "job_type": "causal_scan", "status": "running", "updated_at": "2026-05-21T13:00:00+00:00"},
    ]

    assert select_latest_scanner_job(jobs)["job_id"] == "scan-new"


def test_build_scanner_watchlist_from_causal_signals() -> None:
    signals = pd.DataFrame(
        [
            {
                "symbol": "JTOUSDT",
                "mode": "pump",
                "score": 10,
                "signal_time_utc": "2026-03-18T10:00:00+00:00",
                "signal_price": 2.5,
                "turnover_so_far_usdt": 1_500_000,
            }
        ]
    )
    evaluations = pd.DataFrame([{"symbol": "JTOUSDT", "outcome": "tp", "pnl_underlying_pct": 0.06}])

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
    assert watchlist.loc[0, "symbol"] == "JTOUSDT"
    assert watchlist.loc[0, "status"] == "waiting"
    assert watchlist.loc[0, "outcome"] == "tp"
```

- [ ] **Step 2: Run helper tests to verify they fail**

Run:

```powershell
.\.venv\Scripts\pytest.exe tests/test_bot_monitor.py -q
```

Expected: fails with `ModuleNotFoundError: No module named 'ui.bot_monitor'`.

- [ ] **Step 3: Create the helper module**

Create `ui/bot_monitor.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pandas as pd


def safe_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def result_rows(payload: dict | None) -> list[dict]:
    if not payload:
        return []
    rows = ((payload.get("result") or {}).get("list") or []) or []
    return [row for row in rows if isinstance(row, dict)]


def _first_non_empty(row: dict, names: list[str]) -> Any:
    for name in names:
        value = row.get(name)
        if value is not None and str(value).strip() != "":
            return value
    return None


def _pick_float(row: dict, names: list[str]) -> float | None:
    return safe_float(_first_non_empty(row, names))


def _timestamp_ms_to_iso(value: Any) -> str:
    number = safe_float(value)
    if number is None:
        return ""
    return datetime.fromtimestamp(number / 1000, tz=timezone.utc).isoformat()


def summarize_wallet(payload: dict | None) -> dict[str, float | None]:
    account = result_rows(payload)[0] if result_rows(payload) else {}
    coins = account.get("coin") if isinstance(account.get("coin"), list) else []
    usdt = next((coin for coin in coins if str(coin.get("coin", "")).upper() == "USDT"), {})
    return {
        "equity": _pick_float(account, ["totalEquity"]) or _pick_float(usdt, ["equity"]),
        "wallet_balance": _pick_float(account, ["totalWalletBalance"]) or _pick_float(usdt, ["walletBalance"]),
        "available_balance": _pick_float(account, ["totalAvailableBalance", "availableToWithdraw"])
        or _pick_float(usdt, ["availableToWithdraw"]),
        "margin_used": _pick_float(account, ["totalInitialMargin", "totalMaintenanceMargin"]),
        "unrealized_pnl": _pick_float(account, ["totalPerpUPL"]) or _pick_float(usdt, ["unrealisedPnl", "unrealizedPnl"]),
    }


def _infer_tpsl_by_symbol(orders_payload: dict | None) -> dict[str, dict[str, float | None]]:
    by_symbol: dict[str, dict[str, float | None]] = {}
    for order in result_rows(orders_payload):
        symbol = str(order.get("symbol") or "").upper()
        if not symbol:
            continue
        bucket = by_symbol.setdefault(symbol, {"take_profit": None, "stop_loss": None})
        trigger = safe_float(order.get("triggerPrice"))
        stop_order_type = str(order.get("stopOrderType") or "").lower()
        if "takeprofit" in stop_order_type or "take_profit" in stop_order_type:
            bucket["take_profit"] = trigger
        if "stoploss" in stop_order_type or "stop_loss" in stop_order_type:
            bucket["stop_loss"] = trigger
    return by_symbol


def normalize_positions(payload: dict | None, orders_payload: dict | None = None) -> list[dict]:
    inferred_tpsl = _infer_tpsl_by_symbol(orders_payload)
    rows: list[dict] = []
    for position in result_rows(payload):
        symbol = str(position.get("symbol") or "").upper()
        size = safe_float(position.get("size"))
        if not symbol or size in (None, 0):
            continue
        position_value = _pick_float(position, ["positionValue"])
        unrealized_pnl = _pick_float(position, ["unrealisedPnl", "unrealizedPnl"])
        pnl_pct = None
        if position_value not in (None, 0) and unrealized_pnl is not None:
            pnl_pct = unrealized_pnl / position_value
        inferred = inferred_tpsl.get(symbol, {})
        rows.append(
            {
                "symbol": symbol,
                "side": position.get("side") or "",
                "size": size,
                "entry_price": _pick_float(position, ["avgPrice", "entryPrice"]),
                "mark_price": _pick_float(position, ["markPrice"]),
                "unrealized_pnl": unrealized_pnl,
                "pnl_pct": pnl_pct,
                "leverage": _pick_float(position, ["leverage"]),
                "margin": _pick_float(position, ["positionIM", "positionInitialMargin", "positionBalance"]),
                "liq_price": _pick_float(position, ["liqPrice"]),
                "take_profit": _pick_float(position, ["takeProfit"]) or inferred.get("take_profit"),
                "stop_loss": _pick_float(position, ["stopLoss"]) or inferred.get("stop_loss"),
            }
        )
    return rows


def normalize_open_orders(payload: dict | None) -> list[dict]:
    rows: list[dict] = []
    for order in result_rows(payload):
        rows.append(
            {
                "symbol": str(order.get("symbol") or "").upper(),
                "side": order.get("side") or "",
                "order_type": order.get("orderType") or "",
                "qty": safe_float(order.get("qty")),
                "price": safe_float(order.get("price")),
                "trigger_price": safe_float(order.get("triggerPrice")),
                "stop_order_type": order.get("stopOrderType") or "",
                "status": order.get("orderStatus") or "",
                "created_time": _timestamp_ms_to_iso(order.get("createdTime")),
            }
        )
    return rows


def select_latest_scanner_job(jobs: list[dict]) -> dict | None:
    done_jobs = [job for job in jobs if job.get("status") == "done"]
    causal_jobs = [job for job in done_jobs if job.get("job_type") == "causal_scan"]
    scan_jobs = [job for job in done_jobs if job.get("job_type") in (None, "", "scan")]
    candidates = causal_jobs if causal_jobs else scan_jobs
    if not candidates:
        return None
    return sorted(candidates, key=lambda job: job.get("updated_at") or job.get("created_at") or "", reverse=True)[0]


def _empty_watchlist() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
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
    )


def build_scanner_watchlist(
    job_type: str,
    *,
    signals: pd.DataFrame | None = None,
    evaluations: pd.DataFrame | None = None,
    trades: pd.DataFrame | None = None,
    max_rows: int = 20,
) -> pd.DataFrame:
    if job_type == "causal_scan":
        if signals is None or signals.empty:
            return _empty_watchlist()
        work = signals.copy()
        work["status"] = "waiting"
        work = work.rename(
            columns={
                "signal_time_utc": "time_utc",
                "signal_price": "price",
                "turnover_so_far_usdt": "turnover_usdt",
            }
        )
        if evaluations is not None and not evaluations.empty and "symbol" in evaluations.columns:
            eval_cols = [col for col in ["symbol", "outcome", "pnl_underlying_pct"] if col in evaluations.columns]
            work = work.merge(evaluations[eval_cols].drop_duplicates("symbol"), on="symbol", how="left")
        else:
            work["outcome"] = ""
            work["pnl_underlying_pct"] = None
    else:
        if trades is None or trades.empty:
            return _empty_watchlist()
        work = trades.copy()
        work["status"] = "candidate"
        work = work.rename(
            columns={
                "candidate_score": "score",
                "entry_time_utc": "time_utc",
                "entry_price": "price",
                "turnover_usdt": "turnover_usdt",
            }
        )
        if "outcome" not in work.columns:
            work["outcome"] = ""
        if "pnl_underlying_pct" not in work.columns:
            work["pnl_underlying_pct"] = None

    for column in _empty_watchlist().columns:
        if column not in work.columns:
            work[column] = None
    return work[list(_empty_watchlist().columns)].head(max_rows).reset_index(drop=True)
```

- [ ] **Step 4: Run helper tests to verify they pass**

Run:

```powershell
.\.venv\Scripts\pytest.exe tests/test_bot_monitor.py -q
```

Expected: `10 passed`.

- [ ] **Step 5: Commit helper module**

Run:

```powershell
git add ui/bot_monitor.py tests/test_bot_monitor.py
git commit -m "feat: add bot monitor data helpers"
```

---

## Task 3: Streamlit Bot Monitor Render

**Files:**
- Modify: `tests/test_streamlit_demo_execution_helpers.py`
- Modify: `ui/streamlit_app.py`

- [ ] **Step 1: Write failing source-order test**

In `tests/test_streamlit_demo_execution_helpers.py`, replace:

```python
def test_demo_execution_section_renders_before_jobs_table() -> None:
    source = Path("ui/streamlit_app.py").read_text(encoding="utf-8")

    assert source.index("render_demo_execution(api_url, execution_token)") < source.index('st.header("Jobs")')
```

with:

```python
def test_bot_monitor_section_renders_before_jobs_table() -> None:
    source = Path("ui/streamlit_app.py").read_text(encoding="utf-8")

    assert source.index("render_bot_monitor(api_url, execution_token)") < source.index('st.header("Jobs")')
```

- [ ] **Step 2: Run source-order test to verify it fails**

Run:

```powershell
.\.venv\Scripts\pytest.exe tests/test_streamlit_demo_execution_helpers.py::test_bot_monitor_section_renders_before_jobs_table -q
```

Expected: fails with `ValueError: substring not found`.

- [ ] **Step 3: Add imports to Streamlit**

In `ui/streamlit_app.py`, add this import after the existing `ui.account_backtest` import:

```python
from ui.bot_monitor import (
    build_scanner_watchlist,
    normalize_open_orders,
    normalize_positions,
    select_latest_scanner_job,
    summarize_wallet,
)
```

- [ ] **Step 4: Add small formatting helpers**

In `ui/streamlit_app.py`, after `money`, add:

```python
def signed_money(value: Any) -> str:
    parsed = None if value is None or pd.isna(value) else float(value)
    if parsed is None:
        return "n/a"
    sign = "+" if parsed > 0 else ""
    return f"{sign}${parsed:,.2f}"


def compact_count(value: Any) -> str:
    if value is None or pd.isna(value):
        return "0"
    return str(int(value))
```

- [ ] **Step 5: Add Bot Monitor render functions**

In `ui/streamlit_app.py`, add these functions before `render_demo_execution`:

```python
def _frame_from_rows(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def _load_scanner_watchlist(api_url: str, jobs: list[dict]) -> pd.DataFrame:
    selected = select_latest_scanner_job(jobs)
    if not selected:
        return pd.DataFrame()
    job_id = selected["job_id"]
    job_type = selected.get("job_type") or "scan"
    try:
        if job_type == "causal_scan":
            signals = csv_to_frame(api_get(f"/jobs/{job_id}/signals.csv", api_url).text)
            evaluations = csv_to_frame(api_get(f"/jobs/{job_id}/evaluations.csv", api_url).text)
            return build_scanner_watchlist("causal_scan", signals=signals, evaluations=evaluations)
        trades = csv_to_frame(api_get(f"/jobs/{job_id}/trades.csv", api_url).text)
        return build_scanner_watchlist("scan", trades=trades)
    except Exception:
        return pd.DataFrame()


def render_bot_monitor(api_url: str, execution_token: str) -> None:
    execution_token = execution_token.strip()
    st.header("Bot Monitor")

    health_payload, health_error = api_json_or_error("/health", api_url)
    status_payload, status_error = api_json_or_error("/execution/demo/status", api_url)
    if status_error:
        st.error(f"Execution status unavailable: {status_error}")
        return

    status_payload = status_payload or {}
    limits = status_payload.get("limits") or {}
    status_cols = st.columns(6)
    status_cols[0].metric("Backend", "error" if health_error else "ok")
    status_cols[1].metric("Mode", status_payload.get("mode") or "unknown")
    status_cols[2].metric("Execution", "enabled" if status_payload.get("enabled") else "disabled")
    status_cols[3].metric("API keys", "configured" if status_payload.get("configured") else "missing")
    status_cols[4].metric("Token", "configured" if status_payload.get("api_token_configured") else "missing")
    status_cols[5].metric("Max notional", money(limits.get("max_demo_notional_usdt")))

    st.caption("Bybit Demo monitor. It reads account state and local scanner results; it does not auto-enter signals.")

    if not execution_token:
        st.info("Enter the execution API token in the sidebar to load wallet, positions, orders, and execution history.")
        watchlist = _load_scanner_watchlist(api_url, _safe_jobs(api_url))
        if not watchlist.empty:
            st.subheader("Scanner Watchlist")
            st.dataframe(watchlist, use_container_width=True, hide_index=True)
        return

    wallet_payload, wallet_error = api_json_or_error("/execution/demo/wallet", api_url, token=execution_token)
    positions_payload, positions_error = api_json_or_error("/execution/demo/positions", api_url, token=execution_token)
    orders_payload, orders_error = api_json_or_error("/execution/demo/open-orders", api_url, token=execution_token)
    journal_payload, journal_error = api_json_or_error("/execution/demo/journal?limit=25", api_url, token=execution_token)
    jobs = _safe_jobs(api_url)

    wallet_summary = summarize_wallet(wallet_payload)
    position_rows = normalize_positions(positions_payload, orders_payload)
    order_rows = normalize_open_orders(orders_payload)
    watchlist = _load_scanner_watchlist(api_url, jobs)

    if wallet_summary["margin_used"] is None and position_rows:
        margins = [row.get("margin") for row in position_rows if row.get("margin") is not None]
        wallet_summary["margin_used"] = sum(margins) if margins else None

    account_cols = st.columns(8)
    account_cols[0].metric("Equity", money(wallet_summary["equity"]))
    account_cols[1].metric("Wallet", money(wallet_summary["wallet_balance"]))
    account_cols[2].metric("Available", money(wallet_summary["available_balance"]))
    account_cols[3].metric("Margin used", money(wallet_summary["margin_used"]))
    account_cols[4].metric("Unrealized PnL", signed_money(wallet_summary["unrealized_pnl"]))
    account_cols[5].metric("Positions", compact_count(len(position_rows)))
    account_cols[6].metric("Open orders", compact_count(len(order_rows)))
    account_cols[7].metric("Scanner signals", compact_count(len(watchlist)))

    if wallet_error:
        st.warning(f"Wallet unavailable: {wallet_error}")
    if positions_error:
        st.warning(f"Positions unavailable: {positions_error}")
    if orders_error:
        st.warning(f"Open orders unavailable: {orders_error}")

    left, right = st.columns([1.35, 1.0])
    with left:
        st.subheader("Open Positions")
        positions_frame = _frame_from_rows(position_rows)
        if positions_frame.empty:
            st.info("No open positions returned by Bybit Demo.")
        else:
            st.dataframe(positions_frame, use_container_width=True, hide_index=True)
    with right:
        st.subheader("Scanner Watchlist")
        if watchlist.empty:
            st.info("No completed scanner job is available yet.")
        else:
            st.dataframe(watchlist, use_container_width=True, hide_index=True)

    lower_left, lower_right = st.columns(2)
    with lower_left:
        st.subheader("Open Orders")
        orders_frame = _frame_from_rows(order_rows)
        if orders_frame.empty:
            st.info("No open orders returned by Bybit Demo.")
        else:
            st.dataframe(orders_frame, use_container_width=True, hide_index=True)
    with lower_right:
        st.subheader("Execution History")
        if journal_error:
            st.warning(f"Execution journal unavailable: {journal_error}")
        else:
            journal_rows = (journal_payload or {}).get("rows") or []
            journal_frame = _frame_from_rows(journal_rows)
            if journal_frame.empty:
                st.info("No local execution journal rows yet.")
            else:
                display_cols = [
                    col
                    for col in [
                        "created_at_utc",
                        "symbol",
                        "side",
                        "requested_notional_usdt",
                        "qty",
                        "take_profit",
                        "stop_loss",
                        "status",
                        "reason",
                        "bybit_ret_code",
                        "bybit_ret_msg",
                    ]
                    if col in journal_frame.columns
                ]
                st.dataframe(journal_frame[display_cols], use_container_width=True, hide_index=True)

    with st.expander("Controlled demo test short", expanded=False):
        render_demo_test_short_form(api_url, execution_token, status_payload)
```

- [ ] **Step 6: Add safe jobs loader**

In `ui/streamlit_app.py`, add this helper before `render_bot_monitor`:

```python
def _safe_jobs(api_url: str) -> list[dict]:
    try:
        payload = api_get("/jobs", api_url).json()
        return payload if isinstance(payload, list) else []
    except Exception:
        return []
```

- [ ] **Step 7: Extract the test-short form**

In `ui/streamlit_app.py`, add this function before `render_bot_monitor`:

```python
def render_demo_test_short_form(api_url: str, execution_token: str, status_payload: dict) -> None:
    whitelist = status_payload.get("whitelist") or []
    default_symbol = str(whitelist[0]) if whitelist else "ENAUSDT"
    with st.form("demo_test_short_form"):
        form_cols = st.columns(4)
        symbol = form_cols[0].text_input("Symbol", default_symbol).strip().upper()
        notional = form_cols[1].number_input("Notional USDT", min_value=1.0, value=5.0, step=1.0, format="%.2f")
        take_profit = form_cols[2].number_input("Take profit %", min_value=0.1, value=6.0, step=0.5, format="%.2f")
        stop_loss = form_cols[3].number_input("Stop loss %", min_value=0.1, value=7.0, step=0.5, format="%.2f")
        submit = st.form_submit_button("Place Demo Test Short")

    if submit:
        payload = {
            "symbol": symbol,
            "notional_usdt": float(notional),
            "take_profit_pct": float(take_profit) / 100.0,
            "stop_loss_pct": float(stop_loss) / 100.0,
        }
        try:
            response = api_post("/execution/demo/place-test-short", payload, api_url, token=execution_token)
            st.success("Demo test short submitted.")
            st.json(response.json())
        except Exception as exc:
            st.error(f"Demo test short rejected or failed: {_safe_error(exc, execution_token)}")
```

- [ ] **Step 8: Replace the old top-level demo section call**

In `ui/streamlit_app.py`, replace:

```python
st.divider()
render_demo_execution(api_url, execution_token)

st.header("Jobs")
```

with:

```python
st.divider()
render_bot_monitor(api_url, execution_token)

st.header("Jobs")
```

Leave `render_demo_execution` in the file during this task if removing it would force a large edit. It can be removed in a small cleanup after tests are green.

- [ ] **Step 9: Run source-order test to verify it passes**

Run:

```powershell
.\.venv\Scripts\pytest.exe tests/test_streamlit_demo_execution_helpers.py::test_bot_monitor_section_renders_before_jobs_table -q
```

Expected: `1 passed`.

- [ ] **Step 10: Run Streamlit helper tests**

Run:

```powershell
.\.venv\Scripts\pytest.exe tests/test_streamlit_demo_execution_helpers.py tests/test_bot_monitor.py -q
```

Expected: all tests in both files pass.

- [ ] **Step 11: Commit Streamlit monitor render**

Run:

```powershell
git add ui/streamlit_app.py tests/test_streamlit_demo_execution_helpers.py
git commit -m "feat: render bot monitor dashboard"
```

---

## Task 4: Keep Jobs Flow Stable

**Files:**
- Modify: `ui/streamlit_app.py`

- [ ] **Step 1: Run existing backend and UI tests around jobs**

Run:

```powershell
.\.venv\Scripts\pytest.exe tests/test_backend_api.py tests/test_ui_summary.py tests/test_table_totals.py -q
```

Expected: pass. If a failure shows that Bot Monitor changed the `/jobs` flow, keep the old `Jobs` block behavior and adjust only duplicated `/jobs` fetches.

- [ ] **Step 2: Remove duplicated raw demo account tables from the primary path**

If `render_demo_execution(api_url, execution_token)` is no longer called, keep it unused for one commit or remove the function in the same task after all tests pass. If removing it, also remove only tests that reference the removed function name and keep the token/header tests for `api_get`, `api_post`, `_safe_error`, and `_result_list`.

The preferred final state in `ui/streamlit_app.py` is:

```python
st.divider()
render_bot_monitor(api_url, execution_token)

st.header("Jobs")
```

and no top-level call to:

```python
render_demo_execution(api_url, execution_token)
```

- [ ] **Step 3: Run targeted UI tests again**

Run:

```powershell
.\.venv\Scripts\pytest.exe tests/test_streamlit_demo_execution_helpers.py tests/test_bot_monitor.py -q
```

Expected: all targeted UI tests pass.

- [ ] **Step 4: Commit stability cleanup**

Run:

```powershell
git add ui/streamlit_app.py tests/test_streamlit_demo_execution_helpers.py
git commit -m "refactor: keep demo controls secondary"
```

---

## Task 5: Verification And Local Runtime Check

**Files:**
- Verify repository state.

- [ ] **Step 1: Run full test suite**

Run:

```powershell
.\.venv\Scripts\pytest.exe -q
```

Expected: all tests pass.

- [ ] **Step 2: Run Python compile check**

Run:

```powershell
.\.venv\Scripts\python.exe -m py_compile backend/app/execution_routes.py ui/bot_monitor.py ui/streamlit_app.py
```

Expected: exit code `0`.

- [ ] **Step 3: Run whitespace diff check**

Run:

```powershell
git diff --check
```

Expected: no output and exit code `0`.

- [ ] **Step 4: Restart local backend and UI**

Stop the old local processes only if they are the project servers on ports `8000` and `8501`. Then start:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

and:

```powershell
.\.venv\Scripts\python.exe -m streamlit run ui\streamlit_app.py --server.address 127.0.0.1 --server.port 8501 --server.headless true --browser.gatherUsageStats false
```

Expected:

```text
Backend: http://127.0.0.1:8000/health returns {"status":"ok",...}
UI: http://127.0.0.1:8501 opens with Bot Monitor before Jobs
```

- [ ] **Step 5: Manual UI checks**

Open `http://127.0.0.1:8501` and verify:

```text
Bot Monitor appears above Jobs.
Without token: connection status and scanner watchlist area still render.
With token: wallet/account metrics render.
Open Positions shows readable rows for the demo position when Bybit returns one.
Open Orders shows TP/SL trigger orders when Bybit returns them.
Execution History shows local journal rows.
Jobs section still launches scans and opens existing results.
No API key, API secret, or execution token appears in the UI.
```

- [ ] **Step 6: Commit final verification notes if docs changed**

If no docs changed during verification, do not create an empty commit. If README or docs were updated with a new UI note, run:

```powershell
git add README.md docs
git commit -m "docs: describe bot monitor dashboard"
```

---

## Self-Review Checklist

- Spec coverage:
  - Backend journal endpoint: Task 1.
  - Account status, wallet, positions, orders, journal: Tasks 2 and 3.
  - Scanner watchlist: Tasks 2 and 3.
  - Existing Jobs retained: Tasks 3 and 4.
  - Tests and verification: Tasks 1, 2, 3, 4, 5.
  - Demo-only safety and no secrets: Tasks 1, 3, 5.

- Marker scan:
  - This plan contains no deferred-work markers or unspecified file paths.

- Type consistency:
  - Backend endpoint returns `{"rows": list, "limit": int, "count": int}`.
  - UI helper names in tests match the implementation names.
  - Streamlit imports match `ui/bot_monitor.py`.
