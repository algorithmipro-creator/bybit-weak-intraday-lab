# Causal Live-Scan Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a causal/live-scan-safe signal mode that never uses current-day future data when deciding whether a signal exists.

**Architecture:** Keep the current historical scanner unchanged. Add a new causal module with focused functions for timestamp-safe feature calculation, signal detection and optional post-signal evaluation. The backend/UI can use this later, but this plan only builds the tested core.

**Tech Stack:** Python 3.12, pandas, numpy, pytest.

---

## Core Rule

For any `signal_time`, causal mode may use:

```text
previous-day full ticks/bars
current-day ticks where ts_ns <= signal_ns
current-day bars where bar close time <= signal_time
```

Causal mode must not use:

```text
full current-day turnover
future current-day high/low
future sell share
MFE/MAE
first_barrier outcome
path_max_short over the full day
path_runup over the full day after signal_time
```

Post-signal evaluation can use future ticks, but only after a signal has already been emitted. Keep this separate from signal generation.

## File Structure

Create:

```text
bybit_weak_intraday/causal.py
tests/test_causal.py
```

Modify:

```text
bybit_weak_intraday/__init__.py
README.md
SPECIFICATION.md
docs/ARCHITECTURE.md
docs/ROADMAP.md
```

Do not modify:

```text
bybit_weak_intraday/core.py
bybit_weak_intraday/scanner.py
backend/app/*
ui/*
```

Those integrations belong to later tasks.

## Public API To Build

`bybit_weak_intraday/causal.py` should expose:

```python
from dataclasses import dataclass
from typing import Any

import pandas as pd

from .core import StrategyConfig


@dataclass(frozen=True)
class CausalSignal:
    date: str
    symbol: str
    mode: str
    signal_time_utc: str
    signal_price: float
    score: int
    weak_score: int
    pump_score: int
    turnover_so_far_usdt: float
    prev_turnover_usdt: float
    turnover_ratio_so_far: float
    runup_so_far_pct: float
    peak_time_utc: str
    vwap_at_signal: float
    sell_share_peak_to_signal_pct: float


def truncate_ticks_at(ticks: pd.DataFrame, signal_ns: int) -> pd.DataFrame:
    ...


def sell_share_between(ticks: pd.DataFrame, start_ns: int, end_ns: int) -> float:
    ...


def find_causal_signals(
    symbol: str,
    day: str,
    cur_ticks_raw: pd.DataFrame,
    prev_ticks_raw: pd.DataFrame,
    cfg: StrategyConfig,
) -> list[CausalSignal]:
    ...
```

Implementation notes:

- `cur_ticks_raw` and `prev_ticks_raw` are raw archive-style DataFrames.
- The function should call existing `normalize_ticks()` and `make_bars()`.
- The function returns zero, one or more signals.
- For the first version, emit at most one signal per mode: first weak signal and first pump signal.
- If both modes trigger on the same bar, return both signals; later ranking can decide which one to trade.

## Causal Scoring Definition

### Previous-Day Features

These are safe because previous-day data is fully known:

```text
prev_turnover_usdt
prev_day_ret_pct
prev_day_max_dd_pct
```

### Current-Day Features At A Bar

For each 5-minute bar candidate, use only bars up to and including that bar:

```text
turnover_so_far_usdt
turnover_ratio_so_far = turnover_so_far_usdt / prev_turnover_usdt
runup_so_far_pct
current cumulative VWAP
current close
selected peak so far
sell_share_peak_to_signal_pct
```

### Weak Score

Use the existing score shape, but causal-safe inputs:

```text
+2 prev_day_ret <= -4%
+2 prev_day_max_drawdown <= -9%
+2 turnover_ratio_so_far <= 0.8
+1 runup_so_far between 3% and 12%
+1 selected peak time <= 11:00 UTC
+2 current bar is first close below VWAP after selected peak
+1 sell_share_peak_to_signal >= 52%
```

### Pump Score

Use the existing score shape, but causal-safe inputs:

```text
+2 turnover_ratio_so_far >= 8x
+1 extra turnover_ratio_so_far >= 15x
+2 runup_so_far >= 25%
+1 selected pump peak between 07:00 and 11:30 UTC
+2 current bar is first close below VWAP after selected pump peak
+1 impulse midpoint has been lost by current bar
+1 sell_share_peak_to_signal >= 52%
```

## Task 1: Add Causal Helper Tests

**Files:**

- Create: `tests/test_causal.py`
- Create later in Task 2: `bybit_weak_intraday/causal.py`

- [ ] **Step 1: Write failing tests for truncation and sell share**

Add this to `tests/test_causal.py`:

```python
from __future__ import annotations

import pandas as pd

from bybit_weak_intraday.core import normalize_ticks
from bybit_weak_intraday.causal import sell_share_between, truncate_ticks_at


def test_truncate_ticks_at_removes_future_rows():
    raw = pd.DataFrame(
        {
            "timestamp": [1773792000, 1773792001, 1773792002],
            "side": ["Buy", "Sell", "Sell"],
            "size": [1, 2, 100],
            "price": [10, 10, 10],
        }
    )
    ticks = normalize_ticks(raw)
    signal_ns = int(ticks.iloc[1]["ts_ns"])

    out = truncate_ticks_at(ticks, signal_ns)

    assert len(out) == 2
    assert out["size"].sum() == 3
    assert out["ts_ns"].max() == signal_ns


def test_sell_share_between_uses_only_interval():
    raw = pd.DataFrame(
        {
            "timestamp": [1773792000, 1773792001, 1773792002, 1773792003],
            "side": ["Buy", "Sell", "Sell", "Buy"],
            "size": [10, 4, 6, 100],
            "price": [1, 1, 1, 1],
        }
    )
    ticks = normalize_ticks(raw)
    start_ns = int(ticks.iloc[0]["ts_ns"])
    end_ns = int(ticks.iloc[2]["ts_ns"])

    sell_share = sell_share_between(ticks, start_ns, end_ns)

    assert sell_share == 50.0
```

- [ ] **Step 2: Run tests to verify import failure**

Run:

```bash
python -m pytest tests/test_causal.py -q
```

Expected:

```text
ModuleNotFoundError: No module named 'bybit_weak_intraday.causal'
```

## Task 2: Implement Causal Helpers

**Files:**

- Create: `bybit_weak_intraday/causal.py`
- Test: `tests/test_causal.py`

- [ ] **Step 1: Add initial helper implementation**

Create `bybit_weak_intraday/causal.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from .core import StrategyConfig, make_bars, normalize_ticks, path_max_short


@dataclass(frozen=True)
class CausalSignal:
    date: str
    symbol: str
    mode: str
    signal_time_utc: str
    signal_price: float
    score: int
    weak_score: int
    pump_score: int
    turnover_so_far_usdt: float
    prev_turnover_usdt: float
    turnover_ratio_so_far: float
    runup_so_far_pct: float
    peak_time_utc: str
    vwap_at_signal: float
    sell_share_peak_to_signal_pct: float


def truncate_ticks_at(ticks: pd.DataFrame, signal_ns: int) -> pd.DataFrame:
    """Return only rows known at signal_ns."""
    return ticks.loc[ticks["ts_ns"] <= signal_ns].copy().reset_index(drop=True)


def sell_share_between(ticks: pd.DataFrame, start_ns: int, end_ns: int) -> float:
    """Quote-volume sell share for start_ns < ts_ns <= end_ns."""
    window = ticks[(ticks["ts_ns"] > start_ns) & (ticks["ts_ns"] <= end_ns)]
    if window.empty:
        return float("nan")
    total = float(window["quote"].sum())
    if total == 0:
        return float("nan")
    sell = float(window.loc[window["side"].str.lower() == "sell", "quote"].sum())
    return sell / total * 100
```

- [ ] **Step 2: Run helper tests**

Run:

```bash
python -m pytest tests/test_causal.py -q
```

Expected:

```text
2 passed
```

- [ ] **Step 3: Commit helpers**

Run:

```bash
git add bybit_weak_intraday/causal.py tests/test_causal.py
git commit -m "feat: add causal signal helpers"
```

## Task 3: Add Weak Causal Signal Test

**Files:**

- Modify: `tests/test_causal.py`
- Modify later: `bybit_weak_intraday/causal.py`

- [ ] **Step 1: Add a fixture builder and weak signal test**

Append to `tests/test_causal.py`:

```python
from bybit_weak_intraday.core import StrategyConfig
from bybit_weak_intraday.causal import find_causal_signals


def _ticks(prices: list[float], sides: list[str], start_ts: int = 1773792000) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": [start_ts + i * 300 for i in range(len(prices))],
            "side": sides,
            "size": [1000 for _ in prices],
            "price": prices,
        }
    )


def test_find_causal_signals_emits_weak_without_future_ticks():
    prev = _ticks(
        prices=[100, 96, 92, 90],
        sides=["Sell", "Sell", "Sell", "Sell"],
        start_ts=1773705600,
    )
    cur = _ticks(
        prices=[90, 94, 96, 95, 93, 91, 89, 200],
        sides=["Buy", "Buy", "Buy", "Sell", "Sell", "Sell", "Sell", "Buy"],
    )
    cfg = StrategyConfig(min_turnover=0, weak_threshold=8, pump_threshold=99)

    signals = find_causal_signals("TESTUSDT", "2026-03-18", cur, prev, cfg)

    weak = [s for s in signals if s.mode == "weak"]
    assert len(weak) == 1
    assert weak[0].symbol == "TESTUSDT"
    assert weak[0].signal_price < weak[0].vwap_at_signal
    assert weak[0].signal_price != 200
    assert weak[0].turnover_so_far_usdt < 200_000
```

Why the final price is `200`:

```text
It is future data after the likely signal. If causal code accidentally uses full-day data, turnover/runup/peak logic will be polluted.
```

- [ ] **Step 2: Run this test to verify failure**

Run:

```bash
python -m pytest tests/test_causal.py::test_find_causal_signals_emits_weak_without_future_ticks -q
```

Expected:

```text
ImportError or AttributeError for find_causal_signals
```

## Task 4: Implement Weak Causal Signal Detection

**Files:**

- Modify: `bybit_weak_intraday/causal.py`
- Test: `tests/test_causal.py`

- [ ] **Step 1: Add internal scoring helpers and weak detection**

Add these functions to `bybit_weak_intraday/causal.py`:

```python
def _previous_day_metrics(prev_ticks_raw: pd.DataFrame, interval: str) -> dict[str, float]:
    prev_ticks = normalize_ticks(prev_ticks_raw)
    prev_bars = make_bars(prev_ticks, interval)
    prev_turnover = float(prev_ticks["quote"].sum())
    prev_ret = (float(prev_ticks["price"].iloc[-1]) / float(prev_ticks["price"].iloc[0]) - 1) * 100
    prev_short, _, _ = path_max_short(prev_bars)
    return {
        "prev_turnover_usdt": prev_turnover,
        "prev_day_ret_pct": prev_ret,
        "prev_day_max_dd_pct": -prev_short * 100,
    }


def _runup_so_far(bars_so_far: pd.DataFrame) -> tuple[float, int, int]:
    lows = bars_so_far["low"].to_numpy(float)
    highs = bars_so_far["high"].to_numpy(float)
    running_low = np.minimum.accumulate(lows)
    runups = highs / running_low - 1
    peak_idx = int(np.nanargmax(runups))
    trough_idx = int(np.nanargmin(lows[: peak_idx + 1]))
    return float(runups[peak_idx]), trough_idx, peak_idx


def _first_vwap_loss_indices(bars: pd.DataFrame) -> set[int]:
    out: set[int] = set()
    seen_peak = False
    running_high = -np.inf
    for i, row in bars.iterrows():
        high = float(row["high"])
        if high > running_high:
            running_high = high
            seen_peak = True
            continue
        if seen_peak and float(row["close"]) < float(row["vwap"]):
            out.add(int(i))
            seen_peak = False
    return out


def find_causal_signals(
    symbol: str,
    day: str,
    cur_ticks_raw: pd.DataFrame,
    prev_ticks_raw: pd.DataFrame,
    cfg: StrategyConfig,
) -> list[CausalSignal]:
    """Find causal weak/pump signals without reading future ticks for decisions."""
    cur_ticks = normalize_ticks(cur_ticks_raw)
    prev = _previous_day_metrics(prev_ticks_raw, cfg.bar_interval)
    bars = make_bars(cur_ticks, cfg.bar_interval)
    if cur_ticks.empty or bars.empty or prev["prev_turnover_usdt"] == 0:
        return []

    signals: list[CausalSignal] = []
    emitted_modes: set[str] = set()
    vwap_loss_indices = _first_vwap_loss_indices(bars)

    for i, row in bars.iterrows():
        if int(i) not in vwap_loss_indices:
            continue

        signal_ns = int(row["dt"].value)
        ticks_so_far = truncate_ticks_at(cur_ticks, signal_ns)
        bars_so_far = bars.iloc[: int(i) + 1].copy()
        turnover_so_far = float(ticks_so_far["quote"].sum())
        turnover_ratio = turnover_so_far / prev["prev_turnover_usdt"]
        runup, _, run_peak = _runup_so_far(bars_so_far)
        peak_idx = int(np.nanargmax(bars_so_far["high"].to_numpy(float)))
        peak_time = bars_so_far.iloc[peak_idx]["dt"]
        sell_share = sell_share_between(cur_ticks, int(peak_time.value), signal_ns)

        weak_score = 0
        if prev["prev_day_ret_pct"] <= -4:
            weak_score += 2
        if prev["prev_day_max_dd_pct"] <= -9:
            weak_score += 2
        if turnover_ratio <= 0.8:
            weak_score += 2
        if 3 <= runup * 100 <= 12:
            weak_score += 1
        if peak_time.hour + peak_time.minute / 60 <= 11:
            weak_score += 1
        weak_score += 2
        if sell_share >= 52:
            weak_score += 1

        pump_score = 0

        if (
            "weak" not in emitted_modes
            and turnover_so_far >= cfg.min_turnover
            and weak_score >= cfg.weak_threshold
        ):
            signals.append(
                CausalSignal(
                    date=str(day),
                    symbol=symbol,
                    mode="weak",
                    signal_time_utc=row["dt"].isoformat(),
                    signal_price=float(row["close"]),
                    score=weak_score,
                    weak_score=weak_score,
                    pump_score=pump_score,
                    turnover_so_far_usdt=turnover_so_far,
                    prev_turnover_usdt=prev["prev_turnover_usdt"],
                    turnover_ratio_so_far=turnover_ratio,
                    runup_so_far_pct=runup * 100,
                    peak_time_utc=peak_time.isoformat(),
                    vwap_at_signal=float(row["vwap"]),
                    sell_share_peak_to_signal_pct=sell_share,
                )
            )
            emitted_modes.add("weak")

    return signals
```

- [ ] **Step 2: Run causal tests**

Run:

```bash
python -m pytest tests/test_causal.py -q
```

Expected:

```text
3 passed
```

- [ ] **Step 3: Run all tests**

Run:

```bash
python -m pytest -q
```

Expected:

```text
all tests pass
```

- [ ] **Step 4: Commit weak causal detection**

Run:

```bash
git add bybit_weak_intraday/causal.py tests/test_causal.py
git commit -m "feat: add weak causal signal detection"
```

## Task 5: Add Pump Causal Signal Test

**Files:**

- Modify: `tests/test_causal.py`
- Modify later: `bybit_weak_intraday/causal.py`

- [ ] **Step 1: Add pump test**

Append to `tests/test_causal.py`:

```python
def test_find_causal_signals_emits_pump_after_vwap_loss():
    prev = _ticks(
        prices=[10, 10, 10, 10],
        sides=["Buy", "Sell", "Buy", "Sell"],
        start_ts=1773705600,
    )
    cur = _ticks(
        prices=[10, 12, 15, 14, 13, 11, 10.5],
        sides=["Buy", "Buy", "Buy", "Sell", "Sell", "Sell", "Sell"],
    )
    cfg = StrategyConfig(min_turnover=0, weak_threshold=99, pump_threshold=8)

    signals = find_causal_signals("PUMPUSDT", "2026-03-18", cur, prev, cfg)

    pump = [s for s in signals if s.mode == "pump"]
    assert len(pump) == 1
    assert pump[0].pump_score >= 8
    assert pump[0].runup_so_far_pct >= 25
    assert pump[0].signal_price < pump[0].vwap_at_signal
```

- [ ] **Step 2: Run pump test to verify failure**

Run:

```bash
python -m pytest tests/test_causal.py::test_find_causal_signals_emits_pump_after_vwap_loss -q
```

Expected:

```text
FAIL because pump mode is not implemented yet
```

## Task 6: Implement Pump Causal Signal Detection

**Files:**

- Modify: `bybit_weak_intraday/causal.py`
- Test: `tests/test_causal.py`

- [ ] **Step 1: Add pump scoring inside the loop**

Replace the placeholder:

```python
pump_score = 0
```

with:

```python
pump_score = 0
if turnover_ratio >= 8:
    pump_score += 2
if turnover_ratio >= 15:
    pump_score += 1
if runup * 100 >= 25:
    pump_score += 2
pump_peak_time = bars_so_far.iloc[run_peak]["dt"]
pump_peak_hour = pump_peak_time.hour + pump_peak_time.minute / 60
if 7 <= pump_peak_hour <= 11.5:
    pump_score += 1
pump_score += 2
low = float(bars_so_far.iloc[0 : run_peak + 1]["low"].min())
high = float(bars_so_far.iloc[run_peak]["high"])
midpoint = low + 0.5 * (high - low)
if float(row["close"]) < midpoint:
    pump_score += 1
pump_sell_share = sell_share_between(cur_ticks, int(pump_peak_time.value), signal_ns)
if pump_sell_share >= 52:
    pump_score += 1
```

Then add this block after the weak block:

```python
        if (
            "pump" not in emitted_modes
            and turnover_so_far >= cfg.min_turnover
            and pump_score >= cfg.pump_threshold
        ):
            signals.append(
                CausalSignal(
                    date=str(day),
                    symbol=symbol,
                    mode="pump",
                    signal_time_utc=row["dt"].isoformat(),
                    signal_price=float(row["close"]),
                    score=pump_score,
                    weak_score=weak_score,
                    pump_score=pump_score,
                    turnover_so_far_usdt=turnover_so_far,
                    prev_turnover_usdt=prev["prev_turnover_usdt"],
                    turnover_ratio_so_far=turnover_ratio,
                    runup_so_far_pct=runup * 100,
                    peak_time_utc=pump_peak_time.isoformat(),
                    vwap_at_signal=float(row["vwap"]),
                    sell_share_peak_to_signal_pct=pump_sell_share,
                )
            )
            emitted_modes.add("pump")
```

- [ ] **Step 2: Run causal tests**

Run:

```bash
python -m pytest tests/test_causal.py -q
```

Expected:

```text
4 passed
```

- [ ] **Step 3: Run all tests**

Run:

```bash
python -m pytest -q
```

Expected:

```text
all tests pass
```

- [ ] **Step 4: Commit pump detection**

Run:

```bash
git add bybit_weak_intraday/causal.py tests/test_causal.py
git commit -m "feat: add pump causal signal detection"
```

## Task 7: Add Public Export And Documentation

**Files:**

- Modify: `bybit_weak_intraday/__init__.py`
- Modify: `README.md`
- Modify: `SPECIFICATION.md`
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/ROADMAP.md`

- [ ] **Step 1: Export causal API**

Update `bybit_weak_intraday/__init__.py`:

```python
from .causal import CausalSignal, find_causal_signals

__all__ = ["CausalSignal", "find_causal_signals"]
```

- [ ] **Step 2: Add README section**

Add to `README.md` after `Important Research Caveat`:

```markdown
## Causal Signal Mode

The repository includes a separate causal signal mode in `bybit_weak_intraday/causal.py`.

Historical scanner output is useful for labeling and research. Causal signal output is designed to use only data available at the signal timestamp.

This distinction is important:

- historical mode can analyze what happened during the full day;
- causal mode can only evaluate what was known before or at the candidate signal bar.
```

- [ ] **Step 3: Update specification**

Add to `SPECIFICATION.md` under `10. Known Limitations`:

```markdown
### 10.4 Causal Mode Requirement

Causal mode must keep signal generation separate from post-signal evaluation. Signal generation cannot use MFE, MAE, full-day current turnover, future sell share or future high/low. Post-signal evaluation may use future ticks only after a signal has already been emitted.
```

- [ ] **Step 4: Run tests**

Run:

```bash
python -m pytest -q
```

Expected:

```text
all tests pass
```

- [ ] **Step 5: Commit docs**

Run:

```bash
git add bybit_weak_intraday/__init__.py README.md SPECIFICATION.md docs/ARCHITECTURE.md docs/ROADMAP.md
git commit -m "docs: document causal signal mode"
```

## Task 8: Final Verification

**Files:**

- Review all changed files.

- [ ] **Step 1: Run full test suite**

Run:

```bash
python -m pytest -q
```

Expected:

```text
all tests pass
```

- [ ] **Step 2: Check repository status**

Run:

```bash
git status --short --branch
```

Expected:

```text
## main...origin/main [ahead by N]
```

or clean after pushing.

- [ ] **Step 3: Push branch**

Run:

```bash
git push
```

Expected:

```text
changes pushed to origin/main
```

## Self-Review Notes

Spec coverage:

- Causal/live-scan: covered by Tasks 1-7.
- TP/SL optimizer: intentionally not covered; next separate plan.
- Scheduler: intentionally not covered; depends on backend safety.
- Alerts: intentionally not covered; depends on causal signals and scheduler.
- Paper trading: intentionally not covered; depends on causal signals.
- Backend safety: intentionally not covered; next plan before scheduler.
- Live trading: explicitly out of scope.

Placeholder scan:

- No `TBD` or `TODO` placeholders.
- All tasks include exact files, commands and expected results.

Type consistency:

- `CausalSignal`, `truncate_ticks_at`, `sell_share_between` and `find_causal_signals` are defined before use.
- Test imports match planned module paths.
