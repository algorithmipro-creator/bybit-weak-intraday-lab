# Bot Monitor Signal Decisions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show the latest signal decision rows directly on the Bot Monitor screen.

**Architecture:** Keep execution controls on the Signal Decisions page and add display-only decision visibility to the monitor. The backend already exposes safe public rows through `/signals/decisions`, so the UI only needs to fetch, normalize, and render a compact panel using the existing visual card system.

**Tech Stack:** Python, Streamlit, FastAPI HTTP helpers, pytest, HTML string rendering with escaping.

---

## File Structure

- Modify: `ui/bot_monitor_visual.py`
  - Add `build_signal_decisions_panel_html`.
  - Add row rendering helpers for status/reason/Telegram state.
  - Reuse existing CSS classes and escaping conventions.
- Modify: `ui/streamlit_app.py`
  - Fetch `/signals/decisions?limit=5` inside `render_bot_monitor`.
  - Show a Streamlit warning if the endpoint fails.
  - Render the visual decisions panel after the positions/watchlist panels.
- Modify: `tests/test_bot_monitor_visual.py`
  - Add tests for populated and empty decision panel rendering.
  - Add XSS escaping coverage for decision rows.
- Modify: `tests/test_streamlit_demo_execution_helpers.py`
  - Add a source-level test proving Bot Monitor fetches `/signals/decisions?limit=5`.
  - Keep existing test proving action buttons stay on `render_signal_decisions_page`.

## Task 1: Visual Panel Helper

**Files:**
- Modify: `ui/bot_monitor_visual.py`
- Test: `tests/test_bot_monitor_visual.py`

- [ ] **Step 1: Write failing tests for decision panel rendering**

Add these imports and tests to `tests/test_bot_monitor_visual.py`:

```python
from ui.bot_monitor_visual import build_signal_decisions_panel_html


def test_signal_decisions_panel_renders_latest_decisions() -> None:
    html = build_signal_decisions_panel_html(
        [
            {
                "symbol": "ENAUSDT",
                "status": "qualified",
                "reason": "qualified",
                "telegram_status": "sent",
                "order_link_id": "",
            },
            {
                "symbol": "JTOUSDT",
                "status": "skipped",
                "reason": "dry_run",
                "telegram_status": "sent",
                "order_link_id": "",
            },
        ]
    )

    assert "Signal Decisions" in html
    assert "ENAUSDT" in html
    assert "qualified" in html
    assert "JTOUSDT" in html
    assert "dry_run" in html
    assert "Telegram sent" in html
    assert "bwi-tone-success" in html
    assert "bwi-tone-muted" in html


def test_signal_decisions_panel_renders_empty_state() -> None:
    html = build_signal_decisions_panel_html([])

    assert "Signal Decisions" in html
    assert "No signal decisions yet." in html


def test_signal_decisions_panel_escapes_dynamic_values() -> None:
    html = build_signal_decisions_panel_html(
        [
            {
                "symbol": "<script>alert(1)</script>",
                "status": "<b>error</b>",
                "reason": "<img src=x>",
                "telegram_status": "sent<script>",
                "order_link_id": "<svg>",
            }
        ]
    )

    assert "<script" not in html
    assert "<img" not in html
    assert "<svg" not in html
    assert "&lt;script&gt;" in html
    assert "&lt;img src=x&gt;" in html
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
..\..\.venv\Scripts\python.exe -m pytest tests/test_bot_monitor_visual.py -q
```

Expected: fail because `build_signal_decisions_panel_html` does not exist.

- [ ] **Step 3: Add the minimal visual helper**

In `ui/bot_monitor_visual.py`, add the exported function and helpers near `build_visual_panels_html`:

```python
def build_signal_decisions_panel_html(decision_rows: list[dict]) -> str:
    return _panel_html(
        "Signal Decisions",
        _decision_rows_html(decision_rows),
        "No signal decisions yet.",
    )


def _decision_rows_html(rows: list[dict]) -> str:
    parts = []
    for row in rows[:5]:
        symbol = _value(row.get("symbol"))
        status = _value(row.get("status"))
        reason = _value(row.get("reason"))
        telegram_status = _value(row.get("telegram_status"))
        execution_status = _value(row.get("execution_status"))
        order_link_id = _value(row.get("order_link_id"))
        chip = status
        tone = _decision_tone(status)
        detail_parts = [
            f"<span>Reason {escape(reason)}</span>",
            f"<span>Telegram {escape(telegram_status)}</span>",
        ]
        if execution_status != "n/a":
            detail_parts.append(f"<span>Execution {escape(execution_status)}</span>")
        if order_link_id != "n/a":
            detail_parts.append(f"<span>Order {escape(order_link_id)}</span>")
        parts.append(
            '<div class="bwi-list-row">'
            '<div class="bwi-row-main">'
            f'<div class="bwi-symbol">{escape(symbol)}</div>'
            f'<div class="bwi-chip {_tone_class(tone)}">{escape(chip)}</div>'
            "</div>"
            '<div class="bwi-row-detail">'
            + "".join(detail_parts)
            + "</div></div>"
        )
    return "".join(parts)


def _decision_tone(status: str) -> str:
    normalized = str(status or "").strip().lower()
    if normalized in {"qualified", "entered"}:
        return "success"
    if normalized == "error":
        return "negative"
    if normalized == "skipped":
        return "muted"
    return "neutral"
```

- [ ] **Step 4: Run tests to verify the helper passes**

Run:

```bash
..\..\.venv\Scripts\python.exe -m pytest tests/test_bot_monitor_visual.py -q
```

Expected: all tests in `tests/test_bot_monitor_visual.py` pass.

- [ ] **Step 5: Commit Task 1**

Run:

```bash
git add ui/bot_monitor_visual.py tests/test_bot_monitor_visual.py
git commit -m "feat: render signal decisions monitor panel"
```

## Task 2: Bot Monitor Integration

**Files:**
- Modify: `ui/streamlit_app.py`
- Modify: `tests/test_streamlit_demo_execution_helpers.py`

- [ ] **Step 1: Write failing source-level test for monitor fetch**

Add this test to `tests/test_streamlit_demo_execution_helpers.py`:

```python
def test_bot_monitor_loads_latest_signal_decisions() -> None:
    bot_monitor_source = _function_source("render_bot_monitor")

    assert '"/signals/decisions?limit=5"' in bot_monitor_source
    assert "build_signal_decisions_panel_html" in bot_monitor_source
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
..\..\.venv\Scripts\python.exe -m pytest tests/test_streamlit_demo_execution_helpers.py::test_bot_monitor_loads_latest_signal_decisions -q
```

Expected: fail because `render_bot_monitor` does not yet fetch signal decisions.

- [ ] **Step 3: Import the new helper**

In `ui/streamlit_app.py`, update the existing import from `ui.bot_monitor_visual` to include:

```python
build_signal_decisions_panel_html,
```

- [ ] **Step 4: Fetch decisions inside `render_bot_monitor`**

Inside `render_bot_monitor`, after scanner watchlist loading, add:

```python
    decisions_payload, decisions_error = api_json_or_error("/signals/decisions?limit=5", api_url)
    decision_rows = []
    if isinstance(decisions_payload, dict) and isinstance(decisions_payload.get("rows"), list):
        decision_rows = [row for row in decisions_payload["rows"] if isinstance(row, dict)]
```

After the existing health/status warnings, add:

```python
    if decisions_error:
        st.warning(f"Signal decisions unavailable: {decisions_error}")
```

- [ ] **Step 5: Render the panel after visual positions/watchlist panels**

After `_render_variant_a_visual_overview(...)` and the existing connection-token message, add:

```python
    st.markdown(
        build_signal_decisions_panel_html(decision_rows),
        unsafe_allow_html=True,
    )
```

Keep `_render_monitor_visual_charts(...)` after this panel so the top half of the screen remains operational status first.

- [ ] **Step 6: Run the focused integration test**

Run:

```bash
..\..\.venv\Scripts\python.exe -m pytest tests/test_streamlit_demo_execution_helpers.py::test_bot_monitor_loads_latest_signal_decisions -q
```

Expected: pass.

- [ ] **Step 7: Run the existing Streamlit helper tests**

Run:

```bash
..\..\.venv\Scripts\python.exe -m pytest tests/test_streamlit_demo_execution_helpers.py -q
```

Expected: pass. Confirm the existing test `test_signal_decisions_page_owns_decision_controls` still passes, meaning action buttons stayed off the monitor.

- [ ] **Step 8: Commit Task 2**

Run:

```bash
git add ui/streamlit_app.py tests/test_streamlit_demo_execution_helpers.py
git commit -m "feat: show signal decisions on bot monitor"
```

## Task 3: Verification and Local UI Check

**Files:**
- No code changes expected unless verification finds a defect.

- [ ] **Step 1: Run focused UI tests**

Run:

```bash
..\..\.venv\Scripts\python.exe -m pytest tests/test_bot_monitor_visual.py tests/test_streamlit_demo_execution_helpers.py -q
```

Expected: all selected tests pass.

- [ ] **Step 2: Run full test suite**

Run:

```bash
..\..\.venv\Scripts\python.exe -m pytest -q
```

Expected: all tests pass.

- [ ] **Step 3: Start local backend and UI if they are not already running**

Use the already configured ports when possible:

```powershell
$env:BWI_DATA_DIR='C:\app\data'
$env:BWI_CACHE_DIR='C:\app\data\bybit_archive_cache'
$env:BWI_JOBS_DIR='C:\app\data\jobs'
$env:PYTHONPATH=(Get-Location).Path
..\..\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8002
```

For Streamlit:

```powershell
$env:BWI_BACKEND_URL='http://127.0.0.1:8002'
..\..\.venv\Scripts\python.exe -m streamlit run ui/streamlit_app.py --server.address 127.0.0.1 --server.port 8503
```

Expected: Bot Monitor opens at `http://127.0.0.1:8503` and shows the Signal Decisions panel with recent rows or the empty state.

- [ ] **Step 4: Verify git status**

Run:

```bash
git status --short
```

Expected: clean worktree after commits, except intentionally ignored local runtime files outside the feature worktree.

## Self-Review

- Spec coverage: the plan adds display-only decision visibility, preserves separate action controls, handles empty/error states, escapes dynamic values, and keeps demo/live safety unchanged.
- Placeholder scan: no implementation step relies on unspecified behavior.
- Type consistency: decision rows are dictionaries matching the existing backend public decision fields.
