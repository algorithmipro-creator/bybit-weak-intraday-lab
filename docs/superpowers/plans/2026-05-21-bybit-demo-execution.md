# Bybit Demo Execution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a demo-only Bybit V5 execution slice that can read wallet/positions/open orders and place one guarded USDT perpetual short test order on Bybit Demo.

**Architecture:** Keep execution isolated under `bybit_weak_intraday/execution/` so strategy/scanner code remains exchange-execution agnostic. Backend routes expose demo execution status/read-only data/test-short order, and Streamlit renders a separate `Demo Execution` panel. All order placement flows through safety gates and a local journal; tests mock Bybit and never call the real exchange.

**Tech Stack:** Python, FastAPI, Pydantic settings, requests, pandas, Streamlit, pytest, Bybit V5 REST Demo API.

---

## File Map

- Create `bybit_weak_intraday/execution/__init__.py`: exports execution package symbols.
- Create `bybit_weak_intraday/execution/safety.py`: demo-only config dataclass, symbol whitelist parsing and order safety gates.
- Create `bybit_weak_intraday/execution/journal.py`: CSV journal append/read/count helpers.
- Create `bybit_weak_intraday/execution/orders.py`: Decimal-based instrument parsing, qty rounding, TP/SL price calculation and order payload creation.
- Create `bybit_weak_intraday/execution/bybit_demo.py`: signed Bybit V5 Demo REST client.
- Create `backend/app/execution_routes.py`: FastAPI router for status, read-only endpoints and guarded test short.
- Modify `backend/app/settings.py`: add execution environment settings.
- Modify `backend/app/main.py`: include execution router.
- Modify `ui/streamlit_app.py`: add `Demo Execution` dashboard section.
- Modify `.env.example`: document demo execution environment variables without secrets.
- Create `tests/test_execution_safety.py`: safety gate tests.
- Create `tests/test_execution_journal.py`: journal tests.
- Create `tests/test_execution_orders.py`: sizing/TP/SL/order payload tests.
- Create `tests/test_bybit_demo_client.py`: signed request and endpoint payload tests with fake session.
- Create `tests/test_execution_api.py`: backend route tests with mocked client.

---

### Task 1: Execution Settings And Safety Gates

**Files:**
- Create: `bybit_weak_intraday/execution/__init__.py`
- Create: `bybit_weak_intraday/execution/safety.py`
- Create: `tests/test_execution_safety.py`
- Modify: `backend/app/settings.py`
- Modify: `.env.example`

- [ ] **Step 1: Write failing safety tests**

Create `tests/test_execution_safety.py`:

```python
from __future__ import annotations

from bybit_weak_intraday.execution.safety import (
    DEMO_BASE_URL,
    ExecutionConfig,
    parse_symbol_whitelist,
    validate_position_limit,
    validate_static_demo_order_request,
)


def _config(**overrides) -> ExecutionConfig:
    values = {
        "execution_mode": "demo",
        "execution_enabled": True,
        "api_key": "key",
        "api_secret": "secret",
        "base_url": DEMO_BASE_URL,
        "symbol_whitelist": ("ENAUSDT", "JTOUSDT"),
        "max_demo_notional_usdt": 25.0,
        "max_open_positions": 1,
        "max_daily_test_orders": 3,
    }
    values.update(overrides)
    return ExecutionConfig(**values)


def test_parse_symbol_whitelist_normalizes_symbols() -> None:
    assert parse_symbol_whitelist(" enausdt, JTOUSDT ,,") == ("ENAUSDT", "JTOUSDT")


def test_static_gate_blocks_disabled_mode() -> None:
    decision = validate_static_demo_order_request(
        _config(execution_mode="disabled"),
        symbol="ENAUSDT",
        notional_usdt=10,
        take_profit_pct=0.06,
        stop_loss_pct=0.07,
        daily_test_order_count=0,
    )

    assert not decision.allowed
    assert decision.reason == "execution_mode_not_demo"


def test_static_gate_blocks_when_execution_flag_is_false() -> None:
    decision = validate_static_demo_order_request(
        _config(execution_enabled=False),
        symbol="ENAUSDT",
        notional_usdt=10,
        take_profit_pct=0.06,
        stop_loss_pct=0.07,
        daily_test_order_count=0,
    )

    assert not decision.allowed
    assert decision.reason == "execution_disabled"


def test_static_gate_blocks_mainnet_base_url() -> None:
    decision = validate_static_demo_order_request(
        _config(base_url="https://api.bybit.com"),
        symbol="ENAUSDT",
        notional_usdt=10,
        take_profit_pct=0.06,
        stop_loss_pct=0.07,
        daily_test_order_count=0,
    )

    assert not decision.allowed
    assert decision.reason == "non_demo_base_url"


def test_static_gate_blocks_missing_keys() -> None:
    decision = validate_static_demo_order_request(
        _config(api_key="", api_secret=""),
        symbol="ENAUSDT",
        notional_usdt=10,
        take_profit_pct=0.06,
        stop_loss_pct=0.07,
        daily_test_order_count=0,
    )

    assert not decision.allowed
    assert decision.reason == "missing_demo_api_keys"


def test_static_gate_blocks_non_whitelisted_symbol() -> None:
    decision = validate_static_demo_order_request(
        _config(),
        symbol="BTCUSDT",
        notional_usdt=10,
        take_profit_pct=0.06,
        stop_loss_pct=0.07,
        daily_test_order_count=0,
    )

    assert not decision.allowed
    assert decision.reason == "symbol_not_whitelisted"


def test_static_gate_blocks_oversized_notional() -> None:
    decision = validate_static_demo_order_request(
        _config(max_demo_notional_usdt=25),
        symbol="ENAUSDT",
        notional_usdt=26,
        take_profit_pct=0.06,
        stop_loss_pct=0.07,
        daily_test_order_count=0,
    )

    assert not decision.allowed
    assert decision.reason == "notional_limit_exceeded"


def test_static_gate_blocks_missing_tp_sl() -> None:
    decision = validate_static_demo_order_request(
        _config(),
        symbol="ENAUSDT",
        notional_usdt=10,
        take_profit_pct=0,
        stop_loss_pct=0.07,
        daily_test_order_count=0,
    )

    assert not decision.allowed
    assert decision.reason == "missing_take_profit_or_stop_loss"


def test_static_gate_blocks_daily_order_limit() -> None:
    decision = validate_static_demo_order_request(
        _config(max_daily_test_orders=3),
        symbol="ENAUSDT",
        notional_usdt=10,
        take_profit_pct=0.06,
        stop_loss_pct=0.07,
        daily_test_order_count=3,
    )

    assert not decision.allowed
    assert decision.reason == "daily_test_order_limit_reached"


def test_static_gate_allows_valid_request() -> None:
    decision = validate_static_demo_order_request(
        _config(),
        symbol="enausdt",
        notional_usdt=10,
        take_profit_pct=0.06,
        stop_loss_pct=0.07,
        daily_test_order_count=0,
    )

    assert decision.allowed
    assert decision.reason == "allowed"


def test_position_gate_blocks_open_position_limit() -> None:
    decision = validate_position_limit(_config(max_open_positions=1), open_positions_count=1)

    assert not decision.allowed
    assert decision.reason == "open_position_limit_reached"
```

- [ ] **Step 2: Run safety tests and verify failure**

Run:

```powershell
..\..\.venv\Scripts\python.exe -m pytest tests\test_execution_safety.py -q
```

Expected: fail with `ModuleNotFoundError: No module named 'bybit_weak_intraday.execution'`.

- [ ] **Step 3: Create execution package**

Create `bybit_weak_intraday/execution/__init__.py`:

```python
from __future__ import annotations

__all__ = [
    "bybit_demo",
    "journal",
    "orders",
    "safety",
]
```

- [ ] **Step 4: Implement safety gates**

Create `bybit_weak_intraday/execution/safety.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

DEMO_BASE_URL = "https://api-demo.bybit.com"


@dataclass(frozen=True)
class ExecutionConfig:
    execution_mode: str = "disabled"
    execution_enabled: bool = False
    api_key: str = ""
    api_secret: str = ""
    base_url: str = DEMO_BASE_URL
    symbol_whitelist: tuple[str, ...] = ()
    max_demo_notional_usdt: float = 25.0
    max_open_positions: int = 1
    max_daily_test_orders: int = 3


@dataclass(frozen=True)
class SafetyDecision:
    allowed: bool
    reason: str


def parse_symbol_whitelist(value: str | Sequence[str]) -> tuple[str, ...]:
    if isinstance(value, str):
        raw_symbols = value.split(",")
    else:
        raw_symbols = value
    symbols: list[str] = []
    for symbol in raw_symbols:
        normalized = str(symbol).strip().upper()
        if normalized:
            symbols.append(normalized)
    return tuple(dict.fromkeys(symbols))


def _blocked(reason: str) -> SafetyDecision:
    return SafetyDecision(allowed=False, reason=reason)


def validate_static_demo_order_request(
    config: ExecutionConfig,
    *,
    symbol: str,
    notional_usdt: float,
    take_profit_pct: float,
    stop_loss_pct: float,
    daily_test_order_count: int,
) -> SafetyDecision:
    normalized_symbol = symbol.strip().upper()
    if config.execution_mode != "demo":
        return _blocked("execution_mode_not_demo")
    if not config.execution_enabled:
        return _blocked("execution_disabled")
    if config.base_url.rstrip("/") != DEMO_BASE_URL:
        return _blocked("non_demo_base_url")
    if not config.api_key or not config.api_secret:
        return _blocked("missing_demo_api_keys")
    if normalized_symbol not in config.symbol_whitelist:
        return _blocked("symbol_not_whitelisted")
    if notional_usdt <= 0:
        return _blocked("invalid_notional")
    if notional_usdt > config.max_demo_notional_usdt:
        return _blocked("notional_limit_exceeded")
    if take_profit_pct <= 0 or stop_loss_pct <= 0:
        return _blocked("missing_take_profit_or_stop_loss")
    if daily_test_order_count >= config.max_daily_test_orders:
        return _blocked("daily_test_order_limit_reached")
    return SafetyDecision(allowed=True, reason="allowed")


def validate_position_limit(config: ExecutionConfig, *, open_positions_count: int) -> SafetyDecision:
    if open_positions_count >= config.max_open_positions:
        return _blocked("open_position_limit_reached")
    return SafetyDecision(allowed=True, reason="allowed")
```

- [ ] **Step 5: Add settings fields**

Modify `backend/app/settings.py` by importing `DEMO_BASE_URL` and adding fields to `Settings`:

```python
from bybit_weak_intraday.execution.safety import DEMO_BASE_URL
```

Inside `Settings` add:

```python
    execution_mode: str = "disabled"
    execution_enabled: bool = False
    bybit_demo_api_key: str = ""
    bybit_demo_api_secret: str = ""
    bybit_demo_base_url: str = DEMO_BASE_URL
    execution_symbol_whitelist: str = "ENAUSDT,JTOUSDT"
    max_demo_notional_usdt: float = 25.0
    max_open_positions: int = 1
    max_daily_test_orders: int = 3
    execution_journal_path: Path = Path("/app/data/execution_journal.csv")
```

The final file should still create `data_dir`, `cache_dir` and `jobs_dir` at import time. Do not create `execution_journal_path` as a directory.

- [ ] **Step 6: Document environment variables**

Append to `.env.example`:

```text

# Bybit Demo execution settings
# Keep disabled unless you are intentionally testing against a Bybit Demo account.
BWI_EXECUTION_MODE=disabled
BWI_EXECUTION_ENABLED=false
BWI_BYBIT_DEMO_API_KEY=
BWI_BYBIT_DEMO_API_SECRET=
BWI_BYBIT_DEMO_BASE_URL=https://api-demo.bybit.com
BWI_EXECUTION_SYMBOL_WHITELIST=ENAUSDT,JTOUSDT
BWI_MAX_DEMO_NOTIONAL_USDT=25
BWI_MAX_OPEN_POSITIONS=1
BWI_MAX_DAILY_TEST_ORDERS=3
BWI_EXECUTION_JOURNAL_PATH=/app/data/execution_journal.csv
```

- [ ] **Step 7: Verify safety tests pass**

Run:

```powershell
..\..\.venv\Scripts\python.exe -m pytest tests\test_execution_safety.py -q
```

Expected: `11 passed`.

- [ ] **Step 8: Commit safety foundation**

Run:

```powershell
git add .env.example backend/app/settings.py bybit_weak_intraday/execution/__init__.py bybit_weak_intraday/execution/safety.py tests/test_execution_safety.py
git commit -m "feat: add demo execution safety settings"
```

---

### Task 2: Execution Journal

**Files:**
- Create: `bybit_weak_intraday/execution/journal.py`
- Create: `tests/test_execution_journal.py`

- [ ] **Step 1: Write failing journal tests**

Create `tests/test_execution_journal.py`:

```python
from __future__ import annotations

from datetime import date

from bybit_weak_intraday.execution.journal import append_journal_event, count_daily_test_orders, read_journal


def test_append_journal_event_creates_csv_with_expected_columns(tmp_path) -> None:
    path = tmp_path / "execution_journal.csv"

    append_journal_event(
        path,
        {
            "created_at_utc": "2026-05-21T10:00:00+00:00",
            "event_id": "evt-1",
            "order_link_id": "bwi-1",
            "mode": "demo",
            "symbol": "ENAUSDT",
            "side": "Sell",
            "category": "linear",
            "requested_notional_usdt": 10,
            "qty": "1",
            "take_profit": "0.94",
            "stop_loss": "1.07",
            "status": "accepted",
            "reason": "allowed",
            "bybit_ret_code": 0,
            "bybit_ret_msg": "OK",
            "raw_response_path": "",
        },
    )

    frame = read_journal(path)

    assert len(frame) == 1
    assert frame.loc[0, "symbol"] == "ENAUSDT"
    assert frame.loc[0, "status"] == "accepted"
    assert "api_secret" not in frame.columns


def test_count_daily_test_orders_counts_only_accepted_or_sent_rows(tmp_path) -> None:
    path = tmp_path / "execution_journal.csv"
    append_journal_event(path, {"created_at_utc": "2026-05-21T10:00:00+00:00", "status": "accepted"})
    append_journal_event(path, {"created_at_utc": "2026-05-21T11:00:00+00:00", "status": "sent"})
    append_journal_event(path, {"created_at_utc": "2026-05-21T12:00:00+00:00", "status": "rejected"})
    append_journal_event(path, {"created_at_utc": "2026-05-20T12:00:00+00:00", "status": "accepted"})

    assert count_daily_test_orders(path, day=date(2026, 5, 21)) == 2


def test_read_journal_missing_file_returns_empty_frame(tmp_path) -> None:
    frame = read_journal(tmp_path / "missing.csv")

    assert frame.empty
```

- [ ] **Step 2: Run journal tests and verify failure**

Run:

```powershell
..\..\.venv\Scripts\python.exe -m pytest tests\test_execution_journal.py -q
```

Expected: fail with `ModuleNotFoundError: No module named 'bybit_weak_intraday.execution.journal'`.

- [ ] **Step 3: Implement journal helper**

Create `bybit_weak_intraday/execution/journal.py`:

```python
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

JOURNAL_COLUMNS = [
    "created_at_utc",
    "event_id",
    "order_link_id",
    "mode",
    "symbol",
    "side",
    "category",
    "requested_notional_usdt",
    "qty",
    "take_profit",
    "stop_loss",
    "status",
    "reason",
    "bybit_ret_code",
    "bybit_ret_msg",
    "raw_response_path",
]

COUNTED_ORDER_STATUSES = {"accepted", "sent"}


def _row_from_event(event: dict[str, Any]) -> dict[str, Any]:
    return {column: event.get(column, "") for column in JOURNAL_COLUMNS}


def append_journal_event(path: str | Path, event: dict[str, Any]) -> None:
    journal_path = Path(path)
    journal_path.parent.mkdir(parents=True, exist_ok=True)
    row = pd.DataFrame([_row_from_event(event)], columns=JOURNAL_COLUMNS)
    row.to_csv(journal_path, mode="a", header=not journal_path.exists(), index=False)


def read_journal(path: str | Path) -> pd.DataFrame:
    journal_path = Path(path)
    if not journal_path.exists():
        return pd.DataFrame(columns=JOURNAL_COLUMNS)
    return pd.read_csv(journal_path)


def count_daily_test_orders(path: str | Path, *, day: date) -> int:
    frame = read_journal(path)
    if frame.empty or "created_at_utc" not in frame.columns or "status" not in frame.columns:
        return 0
    created = pd.to_datetime(frame["created_at_utc"], errors="coerce", utc=True)
    statuses = frame["status"].astype(str).str.lower()
    mask = (created.dt.date == day) & statuses.isin(COUNTED_ORDER_STATUSES)
    return int(mask.sum())
```

- [ ] **Step 4: Verify journal tests pass**

Run:

```powershell
..\..\.venv\Scripts\python.exe -m pytest tests\test_execution_journal.py -q
```

Expected: `3 passed`.

- [ ] **Step 5: Commit journal**

Run:

```powershell
git add bybit_weak_intraday/execution/journal.py tests/test_execution_journal.py
git commit -m "feat: add demo execution journal"
```

---

### Task 3: Instrument Rules And Test Short Order Payload

**Files:**
- Create: `bybit_weak_intraday/execution/orders.py`
- Create: `tests/test_execution_orders.py`

- [ ] **Step 1: Write failing order tests**

Create `tests/test_execution_orders.py`:

```python
from __future__ import annotations

from decimal import Decimal

import pytest

from bybit_weak_intraday.execution.orders import (
    build_short_market_order_payload,
    calculate_short_tpsl,
    floor_to_step,
    parse_linear_instrument_rules,
    quantity_from_notional,
)


INSTRUMENT_RESPONSE = {
    "result": {
        "list": [
            {
                "symbol": "ENAUSDT",
                "lotSizeFilter": {"qtyStep": "1", "minOrderQty": "1"},
                "priceFilter": {"tickSize": "0.0001"},
            }
        ]
    }
}


def test_parse_linear_instrument_rules_extracts_steps() -> None:
    rules = parse_linear_instrument_rules(INSTRUMENT_RESPONSE)

    assert rules.symbol == "ENAUSDT"
    assert rules.qty_step == Decimal("1")
    assert rules.min_order_qty == Decimal("1")
    assert rules.tick_size == Decimal("0.0001")


def test_floor_to_step_rounds_down() -> None:
    assert floor_to_step(Decimal("12.987"), Decimal("0.1")) == Decimal("12.9")


def test_quantity_from_notional_uses_reference_price_and_min_qty() -> None:
    rules = parse_linear_instrument_rules(INSTRUMENT_RESPONSE)

    assert quantity_from_notional(Decimal("10"), Decimal("0.7432"), rules) == Decimal("13")


def test_quantity_from_notional_rejects_too_small_notional() -> None:
    rules = parse_linear_instrument_rules(INSTRUMENT_RESPONSE)

    with pytest.raises(ValueError, match="quantity_below_min_order_qty"):
        quantity_from_notional(Decimal("0.01"), Decimal("0.7432"), rules)


def test_calculate_short_tpsl_places_tp_below_and_sl_above_reference() -> None:
    rules = parse_linear_instrument_rules(INSTRUMENT_RESPONSE)

    tp, sl = calculate_short_tpsl(Decimal("1.0000"), Decimal("0.06"), Decimal("0.07"), rules)

    assert tp == Decimal("0.9400")
    assert sl == Decimal("1.0700")


def test_build_short_market_order_payload_uses_linear_sell() -> None:
    payload = build_short_market_order_payload(
        symbol="ENAUSDT",
        qty=Decimal("13"),
        take_profit=Decimal("0.9400"),
        stop_loss=Decimal("1.0700"),
        order_link_id="bwi-demo-1",
    )

    assert payload["category"] == "linear"
    assert payload["symbol"] == "ENAUSDT"
    assert payload["side"] == "Sell"
    assert payload["orderType"] == "Market"
    assert payload["qty"] == "13"
    assert payload["takeProfit"] == "0.9400"
    assert payload["stopLoss"] == "1.0700"
    assert payload["positionIdx"] == 0
    assert payload["orderLinkId"] == "bwi-demo-1"
```

- [ ] **Step 2: Run order tests and verify failure**

Run:

```powershell
..\..\.venv\Scripts\python.exe -m pytest tests\test_execution_orders.py -q
```

Expected: fail with `ModuleNotFoundError: No module named 'bybit_weak_intraday.execution.orders'`.

- [ ] **Step 3: Implement order helpers**

Create `bybit_weak_intraday/execution/orders.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN, ROUND_UP
from typing import Any


@dataclass(frozen=True)
class InstrumentRules:
    symbol: str
    qty_step: Decimal
    min_order_qty: Decimal
    tick_size: Decimal


def _first_result_item(response: dict[str, Any]) -> dict[str, Any]:
    items = ((response.get("result") or {}).get("list") or [])
    if not items:
        raise ValueError("instrument_not_found")
    return items[0]


def parse_linear_instrument_rules(response: dict[str, Any]) -> InstrumentRules:
    item = _first_result_item(response)
    lot = item.get("lotSizeFilter") or {}
    price = item.get("priceFilter") or {}
    return InstrumentRules(
        symbol=str(item["symbol"]).upper(),
        qty_step=Decimal(str(lot["qtyStep"])),
        min_order_qty=Decimal(str(lot["minOrderQty"])),
        tick_size=Decimal(str(price["tickSize"])),
    )


def floor_to_step(value: Decimal, step: Decimal) -> Decimal:
    return (value / step).to_integral_value(rounding=ROUND_DOWN) * step


def ceil_to_step(value: Decimal, step: Decimal) -> Decimal:
    return (value / step).to_integral_value(rounding=ROUND_UP) * step


def quantity_from_notional(notional_usdt: Decimal, reference_price: Decimal, rules: InstrumentRules) -> Decimal:
    if reference_price <= 0:
        raise ValueError("invalid_reference_price")
    qty = floor_to_step(notional_usdt / reference_price, rules.qty_step)
    if qty < rules.min_order_qty:
        raise ValueError("quantity_below_min_order_qty")
    return qty


def calculate_short_tpsl(
    reference_price: Decimal,
    take_profit_pct: Decimal,
    stop_loss_pct: Decimal,
    rules: InstrumentRules,
) -> tuple[Decimal, Decimal]:
    if reference_price <= 0:
        raise ValueError("invalid_reference_price")
    if take_profit_pct <= 0 or stop_loss_pct <= 0:
        raise ValueError("invalid_tpsl_pct")
    take_profit = floor_to_step(reference_price * (Decimal("1") - take_profit_pct), rules.tick_size)
    stop_loss = ceil_to_step(reference_price * (Decimal("1") + stop_loss_pct), rules.tick_size)
    if take_profit >= reference_price:
        raise ValueError("short_take_profit_not_below_reference")
    if stop_loss <= reference_price:
        raise ValueError("short_stop_loss_not_above_reference")
    return take_profit, stop_loss


def _decimal_to_str(value: Decimal) -> str:
    return format(value, "f")


def build_short_market_order_payload(
    *,
    symbol: str,
    qty: Decimal,
    take_profit: Decimal,
    stop_loss: Decimal,
    order_link_id: str,
) -> dict[str, Any]:
    return {
        "category": "linear",
        "symbol": symbol.strip().upper(),
        "side": "Sell",
        "orderType": "Market",
        "qty": _decimal_to_str(qty),
        "timeInForce": "IOC",
        "positionIdx": 0,
        "reduceOnly": False,
        "takeProfit": _decimal_to_str(take_profit),
        "stopLoss": _decimal_to_str(stop_loss),
        "orderLinkId": order_link_id,
    }
```

- [ ] **Step 4: Verify order tests pass**

Run:

```powershell
..\..\.venv\Scripts\python.exe -m pytest tests\test_execution_orders.py -q
```

Expected: `6 passed`.

- [ ] **Step 5: Commit order helpers**

Run:

```powershell
git add bybit_weak_intraday/execution/orders.py tests/test_execution_orders.py
git commit -m "feat: add demo short order helpers"
```

---

### Task 4: Signed Bybit Demo Client

**Files:**
- Create: `bybit_weak_intraday/execution/bybit_demo.py`
- Create: `tests/test_bybit_demo_client.py`

- [ ] **Step 1: Write failing client tests**

Create `tests/test_bybit_demo_client.py`:

```python
from __future__ import annotations

import json

from bybit_weak_intraday.execution.bybit_demo import BybitDemoClient, sign_v5_payload
from bybit_weak_intraday.execution.safety import DEMO_BASE_URL


class FakeResponse:
    def __init__(self, payload: dict):
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self.payload


class FakeSession:
    def __init__(self):
        self.calls: list[dict] = []

    def request(self, method, url, *, params=None, json=None, headers=None, timeout=None):
        self.calls.append(
            {
                "method": method,
                "url": url,
                "params": params,
                "json": json,
                "headers": headers,
                "timeout": timeout,
            }
        )
        return FakeResponse({"retCode": 0, "retMsg": "OK", "result": {"list": []}})


def test_sign_v5_payload_is_stable_for_known_input() -> None:
    signature = sign_v5_payload(
        api_secret="secret",
        timestamp_ms="1700000000000",
        api_key="key",
        recv_window="5000",
        payload='{"category":"linear","symbol":"ENAUSDT"}',
    )

    assert signature == "cfb791c426ed91fc50bf2b87a369064f48f388e7a43aae49aff43942ce900baa"


def test_wallet_balance_uses_demo_base_url_and_auth_headers() -> None:
    session = FakeSession()
    client = BybitDemoClient(api_key="key", api_secret="secret", session=session, timestamp_ms=lambda: "1700000000000")

    client.wallet_balance()

    call = session.calls[0]
    assert call["method"] == "GET"
    assert call["url"] == f"{DEMO_BASE_URL}/v5/account/wallet-balance"
    assert call["params"] == {"accountType": "UNIFIED", "coin": "USDT"}
    assert call["headers"]["X-BAPI-API-KEY"] == "key"
    assert call["headers"]["X-BAPI-TIMESTAMP"] == "1700000000000"
    assert "X-BAPI-SIGN" in call["headers"]


def test_place_short_market_order_posts_expected_body() -> None:
    session = FakeSession()
    client = BybitDemoClient(api_key="key", api_secret="secret", session=session, timestamp_ms=lambda: "1700000000000")

    client.place_short_market_order(
        symbol="ENAUSDT",
        qty="13",
        take_profit="0.94",
        stop_loss="1.07",
        order_link_id="bwi-demo-1",
    )

    call = session.calls[0]
    assert call["method"] == "POST"
    assert call["url"] == f"{DEMO_BASE_URL}/v5/order/create"
    assert call["json"]["category"] == "linear"
    assert call["json"]["side"] == "Sell"
    assert call["json"]["orderType"] == "Market"
    assert call["json"]["qty"] == "13"
    assert call["json"]["takeProfit"] == "0.94"
    assert call["json"]["stopLoss"] == "1.07"
    json.dumps(call["json"], separators=(",", ":"))
```

- [ ] **Step 2: Run client tests and verify failure**

Run:

```powershell
..\..\.venv\Scripts\python.exe -m pytest tests\test_bybit_demo_client.py -q
```

Expected: fail with `ModuleNotFoundError: No module named 'bybit_weak_intraday.execution.bybit_demo'`.

- [ ] **Step 3: Implement signed client**

Create `bybit_weak_intraday/execution/bybit_demo.py`:

```python
from __future__ import annotations

import hashlib
import hmac
import json
import time
from decimal import Decimal
from typing import Any, Callable
from urllib.parse import urlencode

import requests

from bybit_weak_intraday.execution.orders import build_short_market_order_payload
from bybit_weak_intraday.execution.safety import DEMO_BASE_URL


def sign_v5_payload(*, api_secret: str, timestamp_ms: str, api_key: str, recv_window: str, payload: str) -> str:
    raw = f"{timestamp_ms}{api_key}{recv_window}{payload}"
    return hmac.new(api_secret.encode("utf-8"), raw.encode("utf-8"), hashlib.sha256).hexdigest()


def _compact_json(body: dict[str, Any]) -> str:
    return json.dumps(body, separators=(",", ":"), ensure_ascii=False)


class BybitDemoClient:
    def __init__(
        self,
        *,
        api_key: str,
        api_secret: str,
        base_url: str = DEMO_BASE_URL,
        recv_window: str = "5000",
        session: requests.Session | None = None,
        timeout: int = 30,
        timestamp_ms: Callable[[], str] | None = None,
    ) -> None:
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = base_url.rstrip("/")
        self.recv_window = recv_window
        self.session = session or requests.Session()
        self.timeout = timeout
        self.timestamp_ms = timestamp_ms or (lambda: str(int(time.time() * 1000)))

    def _headers(self, payload: str) -> dict[str, str]:
        timestamp = self.timestamp_ms()
        return {
            "X-BAPI-API-KEY": self.api_key,
            "X-BAPI-TIMESTAMP": timestamp,
            "X-BAPI-RECV-WINDOW": self.recv_window,
            "X-BAPI-SIGN": sign_v5_payload(
                api_secret=self.api_secret,
                timestamp_ms=timestamp,
                api_key=self.api_key,
                recv_window=self.recv_window,
                payload=payload,
            ),
            "Content-Type": "application/json",
        }

    def _request(self, method: str, path: str, *, params: dict[str, Any] | None = None, body: dict[str, Any] | None = None) -> dict[str, Any]:
        method = method.upper()
        params = params or {}
        if method == "GET":
            payload = urlencode(params)
            request_body = None
        else:
            request_body = body or {}
            payload = _compact_json(request_body)
        response = self.session.request(
            method,
            f"{self.base_url}{path}",
            params=params if method == "GET" else None,
            json=request_body,
            headers=self._headers(payload),
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def instruments_info(self, symbol: str) -> dict[str, Any]:
        return self._request("GET", "/v5/market/instruments-info", params={"category": "linear", "symbol": symbol.upper()})

    def ticker(self, symbol: str) -> dict[str, Any]:
        return self._request("GET", "/v5/market/tickers", params={"category": "linear", "symbol": symbol.upper()})

    def wallet_balance(self, coin: str = "USDT") -> dict[str, Any]:
        return self._request("GET", "/v5/account/wallet-balance", params={"accountType": "UNIFIED", "coin": coin.upper()})

    def positions(self, symbol: str | None = None) -> dict[str, Any]:
        params = {"category": "linear"}
        if symbol:
            params["symbol"] = symbol.upper()
        return self._request("GET", "/v5/position/list", params=params)

    def open_orders(self, symbol: str | None = None) -> dict[str, Any]:
        params = {"category": "linear", "openOnly": 0}
        if symbol:
            params["symbol"] = symbol.upper()
        return self._request("GET", "/v5/order/realtime", params=params)

    def place_short_market_order(
        self,
        *,
        symbol: str,
        qty: str,
        take_profit: str,
        stop_loss: str,
        order_link_id: str,
    ) -> dict[str, Any]:
        body = build_short_market_order_payload(
            symbol=symbol,
            qty=Decimal(qty),
            take_profit=Decimal(take_profit),
            stop_loss=Decimal(stop_loss),
            order_link_id=order_link_id,
        )
        return self._request("POST", "/v5/order/create", body=body)
```

- [ ] **Step 4: Verify signature test**

Run:

```powershell
..\..\.venv\Scripts\python.exe -m pytest tests\test_bybit_demo_client.py::test_sign_v5_payload_is_stable_for_known_input -q
```

Expected: pass with expected signature `cfb791c426ed91fc50bf2b87a369064f48f388e7a43aae49aff43942ce900baa`.

- [ ] **Step 5: Verify client tests pass**

Run:

```powershell
..\..\.venv\Scripts\python.exe -m pytest tests\test_bybit_demo_client.py -q
```

Expected: `3 passed`.

- [ ] **Step 6: Commit client**

Run:

```powershell
git add bybit_weak_intraday/execution/bybit_demo.py tests/test_bybit_demo_client.py
git commit -m "feat: add bybit demo rest client"
```

---

### Task 5: Demo Execution API Routes

**Files:**
- Create: `backend/app/execution_routes.py`
- Create: `tests/test_execution_api.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Write failing API tests**

Create `tests/test_execution_api.py`:

```python
from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from backend.app import main
from backend.app import execution_routes
from bybit_weak_intraday.execution.safety import DEMO_BASE_URL, ExecutionConfig

client = TestClient(main.app)


class FakeClient:
    def instruments_info(self, symbol):
        return {
            "retCode": 0,
            "result": {
                "list": [
                    {
                        "symbol": symbol,
                        "lotSizeFilter": {"qtyStep": "1", "minOrderQty": "1"},
                        "priceFilter": {"tickSize": "0.0001"},
                    }
                ]
            },
        }

    def ticker(self, symbol):
        return {"retCode": 0, "result": {"list": [{"symbol": symbol, "lastPrice": "1.0000"}]}}

    def wallet_balance(self):
        return {"retCode": 0, "result": {"list": [{"accountType": "UNIFIED"}]}}

    def positions(self, symbol=None):
        return {"retCode": 0, "result": {"list": []}}

    def open_orders(self, symbol=None):
        return {"retCode": 0, "result": {"list": []}}

    def place_short_market_order(self, **kwargs):
        return {"retCode": 0, "retMsg": "OK", "result": {"orderId": "demo-order-1", **kwargs}}


def _patch_execution(monkeypatch, tmp_path: Path, *, enabled: bool = True, whitelist=("ENAUSDT",)):
    config = ExecutionConfig(
        execution_mode="demo",
        execution_enabled=enabled,
        api_key="key",
        api_secret="secret",
        base_url=DEMO_BASE_URL,
        symbol_whitelist=tuple(whitelist),
        max_demo_notional_usdt=25,
        max_open_positions=1,
        max_daily_test_orders=3,
    )
    monkeypatch.setattr(execution_routes, "execution_config_from_settings", lambda: config)
    monkeypatch.setattr(execution_routes, "journal_path_from_settings", lambda: tmp_path / "execution_journal.csv")
    monkeypatch.setattr(execution_routes, "demo_client_from_config", lambda cfg: FakeClient())


def test_execution_status_works_without_keys(monkeypatch, tmp_path):
    config = ExecutionConfig(
        execution_mode="disabled",
        execution_enabled=False,
        api_key="",
        api_secret="",
        base_url=DEMO_BASE_URL,
        symbol_whitelist=("ENAUSDT",),
    )
    monkeypatch.setattr(execution_routes, "execution_config_from_settings", lambda: config)
    monkeypatch.setattr(execution_routes, "journal_path_from_settings", lambda: tmp_path / "execution_journal.csv")

    response = client.get("/execution/demo/status")

    assert response.status_code == 200
    body = response.json()
    assert body["execution_mode"] == "disabled"
    assert body["configured"] is False
    assert "api_secret" not in body


def test_place_test_short_rejects_when_disabled(monkeypatch, tmp_path):
    _patch_execution(monkeypatch, tmp_path, enabled=False)

    response = client.post(
        "/execution/demo/place-test-short",
        json={"symbol": "ENAUSDT", "notional_usdt": 10, "take_profit_pct": 0.06, "stop_loss_pct": 0.07},
    )

    assert response.status_code == 400
    assert response.json()["detail"]["reason"] == "execution_disabled"


def test_place_test_short_rejects_unknown_symbol(monkeypatch, tmp_path):
    _patch_execution(monkeypatch, tmp_path, whitelist=("JTOUSDT",))

    response = client.post(
        "/execution/demo/place-test-short",
        json={"symbol": "ENAUSDT", "notional_usdt": 10, "take_profit_pct": 0.06, "stop_loss_pct": 0.07},
    )

    assert response.status_code == 400
    assert response.json()["detail"]["reason"] == "symbol_not_whitelisted"


def test_place_test_short_uses_mock_client_and_writes_journal(monkeypatch, tmp_path):
    _patch_execution(monkeypatch, tmp_path)

    response = client.post(
        "/execution/demo/place-test-short",
        json={"symbol": "ENAUSDT", "notional_usdt": 10, "take_profit_pct": 0.06, "stop_loss_pct": 0.07},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "sent"
    assert body["symbol"] == "ENAUSDT"
    assert body["qty"] == "10"
    assert body["take_profit"] == "0.9400"
    assert body["stop_loss"] == "1.0700"
    assert (tmp_path / "execution_journal.csv").exists()
```

- [ ] **Step 2: Run API tests and verify failure**

Run:

```powershell
..\..\.venv\Scripts\python.exe -m pytest tests\test_execution_api.py -q
```

Expected: fail because `backend.app.execution_routes` does not exist or `/execution/demo/status` returns `404`.

- [ ] **Step 3: Implement execution routes**

Create `backend/app/execution_routes.py`:

```python
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from bybit_weak_intraday.execution.bybit_demo import BybitDemoClient
from bybit_weak_intraday.execution.journal import append_journal_event, count_daily_test_orders, read_journal
from bybit_weak_intraday.execution.orders import (
    calculate_short_tpsl,
    parse_linear_instrument_rules,
    quantity_from_notional,
)
from bybit_weak_intraday.execution.safety import (
    ExecutionConfig,
    parse_symbol_whitelist,
    validate_position_limit,
    validate_static_demo_order_request,
)

from .settings import settings

router = APIRouter(prefix="/execution/demo", tags=["execution-demo"])


class TestShortRequest(BaseModel):
    symbol: str = Field(..., min_length=3, max_length=30)
    notional_usdt: float = Field(..., gt=0)
    take_profit_pct: float = Field(..., gt=0, le=1)
    stop_loss_pct: float = Field(..., gt=0, le=1)


def execution_config_from_settings() -> ExecutionConfig:
    return ExecutionConfig(
        execution_mode=settings.execution_mode,
        execution_enabled=settings.execution_enabled,
        api_key=settings.bybit_demo_api_key,
        api_secret=settings.bybit_demo_api_secret,
        base_url=settings.bybit_demo_base_url,
        symbol_whitelist=parse_symbol_whitelist(settings.execution_symbol_whitelist),
        max_demo_notional_usdt=float(settings.max_demo_notional_usdt),
        max_open_positions=int(settings.max_open_positions),
        max_daily_test_orders=int(settings.max_daily_test_orders),
    )


def journal_path_from_settings() -> Path:
    return Path(settings.execution_journal_path)


def demo_client_from_config(config: ExecutionConfig) -> BybitDemoClient:
    return BybitDemoClient(api_key=config.api_key, api_secret=config.api_secret, base_url=config.base_url)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _reject(reason: str, *, event: dict, status_code: int = 400) -> None:
    event["status"] = "rejected"
    event["reason"] = reason
    append_journal_event(journal_path_from_settings(), event)
    raise HTTPException(status_code=status_code, detail={"status": "rejected", "reason": reason})


def _result_list(response: dict) -> list[dict]:
    return ((response.get("result") or {}).get("list") or [])


def _open_positions_count(response: dict) -> int:
    count = 0
    for row in _result_list(response):
        size = Decimal(str(row.get("size") or "0"))
        if size != 0:
            count += 1
    return count


def _last_price(response: dict) -> Decimal:
    items = _result_list(response)
    if not items:
        raise ValueError("ticker_not_found")
    return Decimal(str(items[0]["lastPrice"]))


@router.get("/status")
def execution_status() -> dict:
    config = execution_config_from_settings()
    journal = read_journal(journal_path_from_settings())
    return {
        "execution_mode": config.execution_mode,
        "execution_enabled": config.execution_enabled,
        "configured": bool(config.api_key and config.api_secret),
        "base_url": config.base_url,
        "symbol_whitelist": list(config.symbol_whitelist),
        "max_demo_notional_usdt": config.max_demo_notional_usdt,
        "max_open_positions": config.max_open_positions,
        "max_daily_test_orders": config.max_daily_test_orders,
        "journal_rows": int(len(journal)),
    }


@router.get("/wallet")
def demo_wallet() -> dict:
    config = execution_config_from_settings()
    if not config.api_key or not config.api_secret:
        raise HTTPException(status_code=400, detail={"reason": "missing_demo_api_keys"})
    return demo_client_from_config(config).wallet_balance()


@router.get("/positions")
def demo_positions(symbol: str | None = None) -> dict:
    config = execution_config_from_settings()
    if not config.api_key or not config.api_secret:
        raise HTTPException(status_code=400, detail={"reason": "missing_demo_api_keys"})
    return demo_client_from_config(config).positions(symbol=symbol)


@router.get("/open-orders")
def demo_open_orders(symbol: str | None = None) -> dict:
    config = execution_config_from_settings()
    if not config.api_key or not config.api_secret:
        raise HTTPException(status_code=400, detail={"reason": "missing_demo_api_keys"})
    return demo_client_from_config(config).open_orders(symbol=symbol)


@router.post("/place-test-short")
def place_test_short(req: TestShortRequest) -> dict:
    config = execution_config_from_settings()
    symbol = req.symbol.strip().upper()
    event_id = uuid4().hex
    order_link_id = f"bwi-demo-{event_id[:18]}"
    event = {
        "created_at_utc": _utc_now_iso(),
        "event_id": event_id,
        "order_link_id": order_link_id,
        "mode": config.execution_mode,
        "symbol": symbol,
        "side": "Sell",
        "category": "linear",
        "requested_notional_usdt": req.notional_usdt,
    }
    daily_count = count_daily_test_orders(journal_path_from_settings(), day=datetime.now(timezone.utc).date())
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
    response = client.place_short_market_order(
        symbol=symbol,
        qty=str(qty),
        take_profit=str(take_profit),
        stop_loss=str(stop_loss),
        order_link_id=order_link_id,
    )
    event.update(
        {
            "qty": str(qty),
            "take_profit": str(take_profit),
            "stop_loss": str(stop_loss),
            "status": "sent",
            "reason": "allowed",
            "bybit_ret_code": response.get("retCode", ""),
            "bybit_ret_msg": response.get("retMsg", ""),
        }
    )
    append_journal_event(journal_path_from_settings(), event)
    return {
        "status": "sent",
        "symbol": symbol,
        "qty": str(qty),
        "take_profit": str(take_profit),
        "stop_loss": str(stop_loss),
        "order_link_id": order_link_id,
        "bybit_response": response,
    }
```

- [ ] **Step 4: Include router in FastAPI app**

Modify `backend/app/main.py`.

Add import:

```python
from .execution_routes import router as execution_router
```

After CORS middleware setup, add:

```python
app.include_router(execution_router)
```

- [ ] **Step 5: Verify API tests pass**

Run:

```powershell
..\..\.venv\Scripts\python.exe -m pytest tests\test_execution_api.py -q
```

Expected: `4 passed`.

- [ ] **Step 6: Commit API routes**

Run:

```powershell
git add backend/app/execution_routes.py backend/app/main.py tests/test_execution_api.py
git commit -m "feat: add demo execution api routes"
```

---

### Task 6: Streamlit Demo Execution View

**Files:**
- Modify: `ui/streamlit_app.py`

- [ ] **Step 1: Add API helpers for optional JSON calls**

In `ui/streamlit_app.py`, add near existing API helpers:

```python
def api_json_or_error(path: str, api_url: str) -> tuple[dict | None, str | None]:
    try:
        response = api_get(path, api_url)
        return response.json(), None
    except Exception as exc:
        return None, str(exc)
```

- [ ] **Step 2: Add Demo Execution renderer**

Add this function near existing render helpers:

```python
def _result_list(payload: dict | None) -> list[dict]:
    if not payload:
        return []
    return ((payload.get("result") or {}).get("list") or [])


def render_demo_execution(api_url: str) -> None:
    st.subheader("Bybit Demo Execution")
    status_payload, status_error = api_json_or_error("/execution/demo/status", api_url)
    if status_error:
        st.error(f"Execution status unavailable: {status_error}")
        return

    status_payload = status_payload or {}
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Mode", status_payload.get("execution_mode", "unknown"))
    c2.metric("Enabled", "yes" if status_payload.get("execution_enabled") else "no")
    c3.metric("Configured", "yes" if status_payload.get("configured") else "no")
    c4.metric("Journal rows", int(status_payload.get("journal_rows") or 0))
    st.caption("Bybit Demo only. Mainnet execution is blocked by backend safety gates.")

    read_left, read_right = st.columns(2)
    with read_left:
        wallet_payload, wallet_error = api_json_or_error("/execution/demo/wallet", api_url)
        if wallet_error:
            st.info(f"Wallet unavailable: {wallet_error}")
        else:
            st.dataframe(pd.DataFrame(_result_list(wallet_payload)), use_container_width=True, hide_index=True)

    with read_right:
        positions_payload, positions_error = api_json_or_error("/execution/demo/positions", api_url)
        if positions_error:
            st.info(f"Positions unavailable: {positions_error}")
        else:
            st.dataframe(pd.DataFrame(_result_list(positions_payload)), use_container_width=True, hide_index=True)

    orders_payload, orders_error = api_json_or_error("/execution/demo/open-orders", api_url)
    if orders_error:
        st.info(f"Open orders unavailable: {orders_error}")
    else:
        st.dataframe(pd.DataFrame(_result_list(orders_payload)), use_container_width=True, hide_index=True)

    with st.form("demo_test_short_form"):
        st.caption("Controlled test short order. Use tiny notional on a whitelisted symbol.")
        symbol = st.text_input("Symbol", "ENAUSDT")
        notional = st.number_input("Notional USDT", min_value=1.0, value=10.0, step=1.0, format="%.2f")
        take_profit = st.number_input("Take profit %", min_value=0.1, value=6.0, step=0.5, format="%.2f")
        stop_loss = st.number_input("Stop loss %", min_value=0.1, value=7.0, step=0.5, format="%.2f")
        submit = st.form_submit_button("Place Demo Test Short")

    if submit:
        payload = {
            "symbol": symbol,
            "notional_usdt": float(notional),
            "take_profit_pct": float(take_profit) / 100,
            "stop_loss_pct": float(stop_loss) / 100,
        }
        try:
            response = api_post("/execution/demo/place-test-short", payload, api_url)
            st.success("Demo test short submitted.")
            st.json(response.json())
        except Exception as exc:
            st.error(f"Demo test short rejected or failed: {exc}")
```

- [ ] **Step 3: Render section in the app**

After the job result rendering block in `ui/streamlit_app.py`, add:

```python
st.divider()
render_demo_execution(api_url)
```

- [ ] **Step 4: Compile Streamlit**

Run:

```powershell
..\..\.venv\Scripts\python.exe -m py_compile ui\streamlit_app.py
```

Expected: exit code `0`.

- [ ] **Step 5: Commit UI**

Run:

```powershell
git add ui/streamlit_app.py
git commit -m "feat: add demo execution dashboard"
```

---

### Task 7: Verification, Docs And PR

**Files:**
- Modify: `README.md`
- Modify: `SPECIFICATION.md`
- Modify: `docs/ROADMAP.md`
- Modify: `docs/superpowers/plans/2026-05-21-bybit-demo-execution.md`

- [ ] **Step 1: Update README safety wording**

In `README.md`, keep the existing "No live orders" warning and add this note near the API or Roadmap section:

```markdown
## Bybit Demo Execution

The project includes a guarded Bybit Demo execution slice for testing tiny USDT perpetual short orders against `https://api-demo.bybit.com`.

This is not mainnet trading. Order placement is disabled by default and requires `BWI_EXECUTION_MODE=demo`, `BWI_EXECUTION_ENABLED=true`, demo API keys, a whitelisted symbol and small notional limits.
```

- [ ] **Step 2: Update specification**

In `SPECIFICATION.md`, add a subsection under architecture or roadmap:

```markdown
### Demo Execution Boundary

The first execution layer targets Bybit Demo Trading only. It can read wallet, positions and open orders, and can place a guarded tiny `linear` short test order. Mainnet execution and automatic signal-to-order routing remain out of scope until a separate design and risk review.
```

- [ ] **Step 3: Update roadmap**

In `docs/ROADMAP.md`, under Phase 5, add:

```markdown
Initial demo execution slice:

1. Demo-only Bybit V5 connector.
2. Wallet/positions/open-orders view.
3. Guarded tiny test short order.
4. Local execution journal.

Auto-entry from causal signals remains a later phase after this slice is manually verified on Bybit Demo.
```

- [ ] **Step 4: Run targeted tests**

Run:

```powershell
..\..\.venv\Scripts\python.exe -m pytest tests\test_execution_safety.py tests\test_execution_journal.py tests\test_execution_orders.py tests\test_bybit_demo_client.py tests\test_execution_api.py tests\test_streamlit_demo_execution_helpers.py -q
```

Expected: `85 passed`.

Note: later hardening added an execution API token, extra safety tests and Streamlit helper tests, so the final branch reports a larger test count.

- [ ] **Step 5: Run full verification**

Run:

```powershell
..\..\.venv\Scripts\python.exe -m py_compile backend\app\main.py backend\app\execution_routes.py ui\streamlit_app.py bybit_weak_intraday\execution\bybit_demo.py bybit_weak_intraday\execution\journal.py bybit_weak_intraday\execution\orders.py bybit_weak_intraday\execution\safety.py
..\..\.venv\Scripts\python.exe -m pytest -q
git diff --check
git status --short --branch
```

Expected:

```text
py_compile exits 0
pytest reports `128 passed`
git diff --check prints no errors
git status shows only expected docs changes before the final commit
```

- [ ] **Step 6: Commit docs and plan**

Run:

```powershell
git add README.md SPECIFICATION.md docs/ROADMAP.md docs/superpowers/plans/2026-05-21-bybit-demo-execution.md
git commit -m "docs: describe demo execution boundary"
```

- [ ] **Step 7: Push and create PR**

Run:

```powershell
git push -u origin feature/bybit-demo-execution
gh pr create --title "Add Bybit Demo execution slice" --body "## Summary`n- add guarded Bybit Demo execution settings, safety gates, journal and order helpers`n- add signed demo REST client plus backend execution routes`n- add Streamlit Demo Execution panel for wallet, positions, open orders and tiny test short`n`n## Safety`n- mainnet order placement blocked`n- execution disabled by default`n- tests mock Bybit and do not call the exchange`n`n## Tests`n- python -m py_compile backend/app/main.py backend/app/execution_routes.py ui/streamlit_app.py bybit_weak_intraday/execution/bybit_demo.py bybit_weak_intraday/execution/journal.py bybit_weak_intraday/execution/orders.py bybit_weak_intraday/execution/safety.py`n- python -m pytest -q"
```

Expected: PR URL printed.

---

## Manual Demo Verification After Merge

Run this only after the code PR is merged and only with Bybit Demo keys:

```powershell
$env:BWI_EXECUTION_MODE='demo'
$env:BWI_EXECUTION_ENABLED='false'
$env:BWI_BYBIT_DEMO_API_KEY=$env:LOCAL_BYBIT_DEMO_API_KEY
$env:BWI_BYBIT_DEMO_API_SECRET=$env:LOCAL_BYBIT_DEMO_API_SECRET
$env:BWI_BYBIT_DEMO_BASE_URL='https://api-demo.bybit.com'
$env:BWI_EXECUTION_SYMBOL_WHITELIST='ENAUSDT'
$env:BWI_EXECUTION_API_TOKEN='local-demo-token-change-me'
```

Start API/UI. First verify:

```powershell
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8000/execution/demo/status
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8000/execution/demo/wallet -Headers @{'X-BWI-Execution-Token'=$env:BWI_EXECUTION_API_TOKEN}
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8000/execution/demo/positions -Headers @{'X-BWI-Execution-Token'=$env:BWI_EXECUTION_API_TOKEN}
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8000/execution/demo/open-orders -Headers @{'X-BWI-Execution-Token'=$env:BWI_EXECUTION_API_TOKEN}
```

Then enable order placement only for the tiny test:

```powershell
$env:BWI_EXECUTION_ENABLED='true'
```

Submit one test short from the UI or with:

```powershell
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8000/execution/demo/place-test-short `
  -Method POST `
  -Headers @{'X-BWI-Execution-Token'=$env:BWI_EXECUTION_API_TOKEN} `
  -ContentType 'application/json' `
  -Body '{"symbol":"ENAUSDT","notional_usdt":10,"take_profit_pct":0.06,"stop_loss_pct":0.07}'
```

Expected:

```text
response status 200 or a structured Bybit demo rejection
execution_journal.csv contains the attempt
no request is ever sent to api.bybit.com
```

---

## Self-Review Notes

- Spec coverage: settings, safety gates, signed demo client, read-only endpoints, controlled test short, journal, UI, docs and tests are covered.
- Out of scope remains explicit: no mainnet execution, no signal auto-entry, no scheduler-triggered orders.
- Test isolation: all automated tests use fake clients/sessions and must not call real Bybit.
- Type consistency: `ExecutionConfig`, `SafetyDecision`, `BybitDemoClient`, `TestShortRequest` and journal column names are introduced before they are used in later tasks.
