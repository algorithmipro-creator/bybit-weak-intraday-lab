# Capital Backtest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a research-only account-level backtest view that converts scan trade `pnl_underlying_pct` into equity, return, drawdown, and per-trade account PnL.

**Architecture:** Keep account math in a pure `ui/account_backtest.py` helper so Streamlit only renders controls and charts. The helper consumes completed scan `trades.csv` DataFrames and returns a summary dict plus an equity-curve DataFrame. No backend schema or scanner output changes are required.

**Tech Stack:** Python, pandas, pytest, Streamlit, Plotly.

---

### Task 1: Account Backtest Helper

**Files:**
- Create: `ui/account_backtest.py`
- Create: `tests/test_account_backtest.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_account_backtest.py` with tests for one winning trade after fees, compounding, max drawdown, skipped missing PnL rows, and empty input:

```python
from __future__ import annotations

import pandas as pd
import pytest

from ui.account_backtest import AccountBacktestSettings, run_account_backtest


def test_account_backtest_single_winner_after_fees():
    trades = pd.DataFrame(
        [
            {
                "date": "2026-03-18",
                "symbol": "AAAUSDT",
                "mode": "weak",
                "outcome": "tp",
                "entry_time_utc": "2026-03-18T10:00:00+00:00",
                "exit_time_utc": "2026-03-18T11:00:00+00:00",
                "pnl_underlying_pct": 6.0,
            }
        ]
    )

    summary, curve = run_account_backtest(trades, AccountBacktestSettings())

    assert summary["trades"] == 1
    assert summary["skipped_trades"] == 0
    assert summary["final_equity_usd"] == pytest.approx(10058.8)
    assert summary["total_return_pct"] == pytest.approx(0.588)
    assert curve.loc[0, "gross_pnl_usd"] == pytest.approx(60.0)
    assert curve.loc[0, "costs_usd"] == pytest.approx(1.2)
    assert curve.loc[0, "net_pnl_usd"] == pytest.approx(58.8)


def test_account_backtest_compounds_by_exit_order():
    trades = pd.DataFrame(
        [
            {"symbol": "BBB", "entry_time_utc": "2026-03-18T10:00:00+00:00", "exit_time_utc": "2026-03-18T12:00:00+00:00", "pnl_underlying_pct": -7.0},
            {"symbol": "AAA", "entry_time_utc": "2026-03-18T09:00:00+00:00", "exit_time_utc": "2026-03-18T11:00:00+00:00", "pnl_underlying_pct": 6.0},
        ]
    )
    settings = AccountBacktestSettings(entry_fee_pct=0.0, exit_fee_pct=0.0)

    summary, curve = run_account_backtest(trades, settings)

    assert curve["symbol"].tolist() == ["AAA", "BBB"]
    assert curve.loc[0, "equity_after_usd"] == pytest.approx(10060.0)
    assert curve.loc[1, "equity_after_usd"] == pytest.approx(9989.58)
    assert summary["final_equity_usd"] == pytest.approx(9989.58)


def test_account_backtest_reports_max_drawdown():
    trades = pd.DataFrame(
        [
            {"symbol": "AAA", "entry_time_utc": "2026-03-18T09:00:00+00:00", "exit_time_utc": "2026-03-18T10:00:00+00:00", "pnl_underlying_pct": 10.0},
            {"symbol": "BBB", "entry_time_utc": "2026-03-18T10:00:00+00:00", "exit_time_utc": "2026-03-18T11:00:00+00:00", "pnl_underlying_pct": -20.0},
        ]
    )
    settings = AccountBacktestSettings(entry_fee_pct=0.0, exit_fee_pct=0.0)

    summary, _ = run_account_backtest(trades, settings)

    assert summary["max_drawdown_pct"] == pytest.approx(2.0)


def test_account_backtest_skips_missing_pnl_rows():
    trades = pd.DataFrame(
        [
            {"symbol": "AAA", "entry_time_utc": "2026-03-18T09:00:00+00:00", "exit_time_utc": "2026-03-18T10:00:00+00:00", "pnl_underlying_pct": None},
            {"symbol": "BBB", "entry_time_utc": "2026-03-18T10:00:00+00:00", "exit_time_utc": "2026-03-18T11:00:00+00:00", "pnl_underlying_pct": 5.0},
        ]
    )
    settings = AccountBacktestSettings(entry_fee_pct=0.0, exit_fee_pct=0.0)

    summary, curve = run_account_backtest(trades, settings)

    assert summary["trades"] == 1
    assert summary["skipped_trades"] == 1
    assert len(curve) == 1


def test_account_backtest_empty_input_is_stable():
    summary, curve = run_account_backtest(pd.DataFrame(), AccountBacktestSettings())

    assert summary["trades"] == 0
    assert summary["skipped_trades"] == 0
    assert summary["final_equity_usd"] == 10000.0
    assert summary["total_return_pct"] == 0.0
    assert curve.empty
```

- [ ] **Step 2: Verify tests fail**

Run:

```powershell
..\..\.venv\Scripts\python.exe -m pytest tests/test_account_backtest.py -q
```

Expected: fail with `ModuleNotFoundError: No module named 'ui.account_backtest'`.

- [ ] **Step 3: Implement helper**

Create `ui/account_backtest.py` with:

```python
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class AccountBacktestSettings:
    initial_equity_usd: float = 10_000.0
    position_size_pct: float = 10.0
    leverage: float = 1.0
    entry_fee_pct: float = 0.06
    exit_fee_pct: float = 0.06
    slippage_pct: float = 0.0
    funding_pct: float = 0.0


def run_account_backtest(trades: pd.DataFrame, settings: AccountBacktestSettings) -> tuple[dict[str, float], pd.DataFrame]:
    validate_account_backtest_settings(settings)
    # Return a summary dict and an equity-curve DataFrame using the formulas below.
```

Implement validation and the account loop with these formulas:

```python
margin_allocated = equity_before * settings.position_size_pct / 100
notional = margin_allocated * settings.leverage
gross_pnl_usd = notional * pnl_underlying_pct / 100
cost_rate = settings.entry_fee_pct + settings.exit_fee_pct + settings.slippage_pct + settings.funding_pct
costs_usd = notional * cost_rate / 100
net_pnl_usd = gross_pnl_usd - costs_usd
equity_after = equity_before + net_pnl_usd
account_return_pct = net_pnl_usd / equity_before * 100
```

- [ ] **Step 4: Verify helper tests pass**

Run:

```powershell
..\..\.venv\Scripts\python.exe -m pytest tests/test_account_backtest.py -q
```

Expected: `5 passed`.

### Task 2: Streamlit Account Backtest UI

**Files:**
- Modify: `ui/streamlit_app.py`
- Test: `tests/test_account_backtest.py`

- [ ] **Step 1: Import helper**

Add:

```python
from ui.account_backtest import AccountBacktestSettings, run_account_backtest
```

- [ ] **Step 2: Add renderer**

Add `render_account_backtest(trades: pd.DataFrame)` near existing render helpers. It should show controls for initial equity, position size, leverage, entry fee, exit fee, slippage, funding; then show metrics for final equity, total return, net PnL, max drawdown, win rate, skipped trades; then draw an equity curve and per-trade net PnL chart when curve rows exist.

- [ ] **Step 3: Call renderer for completed scan jobs**

In the completed scan branch, call `render_account_backtest(trades)` after `render_scan_overview(trades)` and before the tabs.

- [ ] **Step 4: Compile Streamlit**

Run:

```powershell
..\..\.venv\Scripts\python.exe -m py_compile ui\streamlit_app.py
```

Expected: exit code `0`.

### Task 3: Verification And Integration

**Files:**
- Modify: `docs/superpowers/plans/2026-05-20-capital-backtest.md` only if implementation reality differs.

- [ ] **Step 1: Run full tests**

Run:

```powershell
..\..\.venv\Scripts\python.exe -m pytest -q
```

Expected: all tests pass.

- [ ] **Step 2: Check diff**

Run:

```powershell
git diff --check
git status --short --branch
```

Expected: no whitespace errors; only expected feature files modified.

- [ ] **Step 3: Commit**

Run:

```powershell
git add ui/account_backtest.py ui/streamlit_app.py tests/test_account_backtest.py docs/superpowers/plans/2026-05-20-capital-backtest.md
git commit -m "feat: add account capital backtest"
```

- [ ] **Step 4: Push and PR**

Run:

```powershell
git push -u origin feature/capital-backtest
gh pr create --title "Add account capital backtest" --body "## Summary`n- add fixed-fraction account backtest helper`n- add Streamlit controls, account metrics, equity curve, and per-trade account PnL chart`n- cover capital calculations with pytest`n`n## Tests`n- python -m py_compile ui/streamlit_app.py`n- python -m pytest -q"
```

Expected: PR URL printed.
