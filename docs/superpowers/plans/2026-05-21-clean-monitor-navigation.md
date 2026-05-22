# Clean Monitor Navigation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the overloaded Streamlit first screen with a connection-first app flow and a clean Bot Monitor main page.

**Architecture:** Add a small pure navigation/session helper module, then refactor `ui/streamlit_app.py` into page render functions. The Monitor page keeps only the simplified live overview, while Scanner Jobs, Reports, Execution History and Settings become secondary pages.

**Tech Stack:** Python 3.12, Streamlit, pandas, Plotly, pytest, existing FastAPI backend endpoints.

---

## File Structure

- Create `ui/app_navigation.py`
  - Pure helpers for page names and session state keys.
  - No Streamlit import.

- Create `tests/test_app_navigation.py`
  - Tests for default session values, connection state and page validation.

- Modify `tests/test_streamlit_demo_execution_helpers.py`
  - Add source-level tests proving the connection-first flow and page separation exist.

- Modify `ui/streamlit_app.py`
  - Add `render_connection_screen`.
  - Add `render_app_menu`.
  - Add page functions:
    - `render_monitor_page`;
    - `render_scanner_jobs_page`;
    - `render_reports_page`;
    - `render_execution_history_page`;
    - `render_settings_page`.
  - Move current sidebar scan settings and Jobs area into secondary page functions.
  - Remove raw position/order/journal tables from the Monitor page.
  - Move controlled demo test short form into Settings.

- Keep existing files:
  - `ui/bot_monitor.py`;
  - `ui/bot_monitor_visual.py`;
  - backend execution routes.

---

## Task 1: Add Pure Navigation State Helpers

**Files:**
- Create: `ui/app_navigation.py`
- Create: `tests/test_app_navigation.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_app_navigation.py`:

```python
from __future__ import annotations

from ui.app_navigation import (
    NAV_PAGES,
    connection_values,
    disconnect,
    ensure_navigation_state,
    is_connected,
    mark_connected,
    normalize_page,
)


def test_nav_pages_match_clean_monitor_design() -> None:
    assert NAV_PAGES == ("Monitor", "Reports", "Scanner Jobs", "Execution History", "Settings")


def test_ensure_navigation_state_sets_defaults_without_overwriting_existing_values() -> None:
    state = {"bwi_api_url": "http://custom:8000", "bwi_selected_page": "Reports"}

    ensure_navigation_state(state, default_api_url="http://default:8000")

    assert state["bwi_api_url"] == "http://custom:8000"
    assert state["bwi_execution_token"] == ""
    assert state["bwi_connected"] is False
    assert state["bwi_selected_page"] == "Reports"


def test_mark_connected_stores_session_local_connection_values() -> None:
    state = {}
    ensure_navigation_state(state, default_api_url="http://default:8000")

    mark_connected(state, api_url="http://api:8000/", execution_token="  token  ")

    assert is_connected(state) is True
    assert connection_values(state) == {
        "api_url": "http://api:8000",
        "execution_token": "token",
        "selected_page": "Monitor",
    }


def test_disconnect_clears_token_and_returns_to_monitor() -> None:
    state = {"bwi_connected": True, "bwi_execution_token": "secret", "bwi_selected_page": "Reports"}

    disconnect(state)

    assert state["bwi_connected"] is False
    assert state["bwi_execution_token"] == ""
    assert state["bwi_selected_page"] == "Monitor"


def test_normalize_page_rejects_unknown_pages() -> None:
    assert normalize_page("Reports") == "Reports"
    assert normalize_page("bad-page") == "Monitor"
    assert normalize_page(None) == "Monitor"
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```powershell
..\..\.venv\Scripts\pytest.exe tests/test_app_navigation.py -q
```

Expected: fails with `ModuleNotFoundError: No module named 'ui.app_navigation'`.

- [ ] **Step 3: Implement helper module**

Create `ui/app_navigation.py`:

```python
from __future__ import annotations

from collections.abc import MutableMapping
from typing import Any


NAV_PAGES = ("Monitor", "Reports", "Scanner Jobs", "Execution History", "Settings")
API_URL_KEY = "bwi_api_url"
EXECUTION_TOKEN_KEY = "bwi_execution_token"
CONNECTED_KEY = "bwi_connected"
SELECTED_PAGE_KEY = "bwi_selected_page"


def ensure_navigation_state(state: MutableMapping[str, Any], *, default_api_url: str) -> None:
    state.setdefault(API_URL_KEY, default_api_url.rstrip("/"))
    state.setdefault(EXECUTION_TOKEN_KEY, "")
    state.setdefault(CONNECTED_KEY, False)
    state[SELECTED_PAGE_KEY] = normalize_page(state.get(SELECTED_PAGE_KEY))


def mark_connected(state: MutableMapping[str, Any], *, api_url: str, execution_token: str) -> None:
    state[API_URL_KEY] = api_url.rstrip("/")
    state[EXECUTION_TOKEN_KEY] = execution_token.strip()
    state[CONNECTED_KEY] = True
    state[SELECTED_PAGE_KEY] = "Monitor"


def disconnect(state: MutableMapping[str, Any]) -> None:
    state[CONNECTED_KEY] = False
    state[EXECUTION_TOKEN_KEY] = ""
    state[SELECTED_PAGE_KEY] = "Monitor"


def is_connected(state: MutableMapping[str, Any]) -> bool:
    return bool(state.get(CONNECTED_KEY))


def normalize_page(value: Any) -> str:
    return value if value in NAV_PAGES else "Monitor"


def connection_values(state: MutableMapping[str, Any]) -> dict[str, str]:
    return {
        "api_url": str(state.get(API_URL_KEY) or "").rstrip("/"),
        "execution_token": str(state.get(EXECUTION_TOKEN_KEY) or "").strip(),
        "selected_page": normalize_page(state.get(SELECTED_PAGE_KEY)),
    }
```

- [ ] **Step 4: Run tests to verify GREEN**

Run:

```powershell
..\..\.venv\Scripts\pytest.exe tests/test_app_navigation.py -q
```

Expected: `5 passed`.

- [ ] **Step 5: Commit**

Run:

```powershell
git add ui/app_navigation.py tests/test_app_navigation.py
git commit -m "feat: add clean monitor navigation state"
```

---

## Task 2: Add Source Tests For Connection-First Flow

**Files:**
- Modify: `tests/test_streamlit_demo_execution_helpers.py`

- [ ] **Step 1: Add failing source tests**

Append these helpers and tests to `tests/test_streamlit_demo_execution_helpers.py`:

```python
def _function_source(name: str) -> str:
    source = Path("ui/streamlit_app.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.get_source_segment(source, node) or ""
    raise AssertionError(f"Function {name} not found")


def test_streamlit_app_defines_clean_navigation_pages() -> None:
    source = Path("ui/streamlit_app.py").read_text(encoding="utf-8")

    assert "render_connection_screen" in source
    assert "render_app_menu" in source
    assert "render_monitor_page" in source
    assert "render_scanner_jobs_page" in source
    assert "render_reports_page" in source
    assert "render_execution_history_page" in source
    assert "render_settings_page" in source


def test_monitor_page_does_not_render_jobs_or_connection_inputs() -> None:
    monitor_source = _function_source("render_monitor_page")

    assert "render_bot_monitor" in monitor_source
    assert 'st.header("Jobs")' not in monitor_source
    assert "Start job" not in monitor_source
    assert "Execution API token" not in monitor_source
    assert "Backend API URL" not in monitor_source


def test_connection_screen_owns_connection_inputs() -> None:
    connection_source = _function_source("render_connection_screen")

    assert "Backend API URL" in connection_source
    assert "Execution API token" in connection_source
    assert "Connect" in connection_source


def test_secondary_menu_contains_clean_monitor_sections() -> None:
    menu_source = _function_source("render_app_menu")

    for label in ["Monitor", "Reports", "Scanner Jobs", "Execution History", "Settings"]:
        assert label in menu_source
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```powershell
..\..\.venv\Scripts\pytest.exe tests/test_streamlit_demo_execution_helpers.py::test_streamlit_app_defines_clean_navigation_pages tests/test_streamlit_demo_execution_helpers.py::test_monitor_page_does_not_render_jobs_or_connection_inputs tests/test_streamlit_demo_execution_helpers.py::test_connection_screen_owns_connection_inputs tests/test_streamlit_demo_execution_helpers.py::test_secondary_menu_contains_clean_monitor_sections -q
```

Expected: fails because the new page functions do not exist.

- [ ] **Step 3: Commit tests only**

Do not commit red tests by themselves. Leave them staged/unstaged for Task 3 implementation.

---

## Task 3: Add Connection Screen And Top-Level Router

**Files:**
- Modify: `ui/streamlit_app.py`
- Modify: `tests/test_streamlit_demo_execution_helpers.py`

- [ ] **Step 1: Add navigation imports**

In `ui/streamlit_app.py`, add after the `ui.account_backtest` import:

```python
from ui.app_navigation import (
    NAV_PAGES,
    SELECTED_PAGE_KEY,
    connection_values,
    disconnect,
    ensure_navigation_state,
    is_connected,
    mark_connected,
)
```

- [ ] **Step 2: Add connection check helper**

Add before `render_demo_test_short_form`:

```python
def validate_connection(api_url: str, execution_token: str) -> tuple[bool, list[str]]:
    messages: list[str] = []
    health_payload, health_error = api_json_or_error("/health", api_url)
    status_payload, status_error = api_json_or_error("/execution/demo/status", api_url)

    if health_error:
        messages.append(f"Backend unavailable: {health_error}")
    elif health_payload:
        messages.append("Backend online")

    if status_error:
        messages.append(f"Execution status unavailable: {status_error}")
    else:
        status_payload = status_payload or {}
        messages.append(f"Mode: {status_payload.get('mode') or 'unknown'}")
        messages.append("Keys configured" if status_payload.get("configured") else "Keys missing")

    if not execution_token.strip():
        messages.append("Execution token is required")
        return False, messages

    wallet_payload, wallet_error = api_json_or_error("/execution/demo/wallet", api_url, token=execution_token)
    if wallet_error:
        messages.append(f"Token/account check failed: {wallet_error}")
        return False, messages
    if wallet_payload is not None:
        messages.append("Token accepted")

    return health_error is None and status_error is None, messages
```

- [ ] **Step 3: Add connection screen**

Add before `render_bot_monitor`:

```python
def render_connection_screen(default_api_url: str) -> None:
    st.title("Bybit Demo Connection")
    st.caption("Connect once, then monitor the demo bot without keeping setup controls open.")
    api_url = st.text_input("Backend API URL", st.session_state.get("bwi_api_url", default_api_url)).rstrip("/")
    execution_token = st.text_input("Execution API token", type="password")
    connect = st.button("Connect", type="primary")

    if connect:
        ok, messages = validate_connection(api_url, execution_token)
        for message in messages:
            if "failed" in message.lower() or "unavailable" in message.lower() or "required" in message.lower():
                st.error(message)
            else:
                st.info(message)
        if ok:
            mark_connected(st.session_state, api_url=api_url, execution_token=execution_token)
            st.rerun()
```

- [ ] **Step 4: Add menu and page stubs**

Add after `render_bot_monitor`:

```python
def render_app_menu() -> str:
    current = st.session_state.get(SELECTED_PAGE_KEY, "Monitor")
    index = NAV_PAGES.index(current) if current in NAV_PAGES else 0
    page = st.radio("Menu", NAV_PAGES, index=index, horizontal=True, label_visibility="collapsed")
    st.session_state[SELECTED_PAGE_KEY] = page
    return page


def render_monitor_page(api_url: str, execution_token: str) -> None:
    render_bot_monitor(api_url, execution_token)


def render_reports_page(api_url: str, auto_refresh: bool) -> None:
    st.header("Reports")
    st.info("Open a completed job from Scanner Jobs to review reports and result charts.")


def render_scanner_jobs_page(api_url: str, auto_refresh: bool) -> None:
    st.header("Scanner Jobs")
    st.info("Scanner controls move here in the next task.")


def render_execution_history_page(api_url: str, execution_token: str) -> None:
    st.header("Execution History")
    st.info("Execution journal moves here in the next task.")


def render_settings_page(api_url: str, execution_token: str) -> None:
    st.header("Settings")
    st.info("Connection and demo test controls move here in the next task.")
```

- [ ] **Step 5: Replace top-level connection/sidebar block**

Replace the existing top-level `with st.sidebar:` block and immediate app body with this minimal router. This is temporary; later tasks fill secondary pages:

```python
ensure_navigation_state(st.session_state, default_api_url=DEFAULT_API)

if not is_connected(st.session_state):
    render_connection_screen(DEFAULT_API)
    st.stop()

connection = connection_values(st.session_state)
api_url = connection["api_url"]
execution_token = connection["execution_token"]
auto_refresh = True

top_left, top_right = st.columns([1, 0.18])
with top_left:
    page = render_app_menu()
with top_right:
    if st.button("Disconnect"):
        disconnect(st.session_state)
        st.rerun()

if page == "Monitor":
    render_monitor_page(api_url, execution_token)
elif page == "Reports":
    render_reports_page(api_url, auto_refresh)
elif page == "Scanner Jobs":
    render_scanner_jobs_page(api_url, auto_refresh)
elif page == "Execution History":
    render_execution_history_page(api_url, execution_token)
elif page == "Settings":
    render_settings_page(api_url, execution_token)
```

Do not delete the old Jobs code yet if this makes the edit too large. It can remain below temporarily only if it is unreachable. The next task must move it into page functions and remove the old top-level path.

- [ ] **Step 6: Run source tests**

Run:

```powershell
..\..\.venv\Scripts\pytest.exe tests/test_streamlit_demo_execution_helpers.py -q
```

Expected: all tests pass.

- [ ] **Step 7: Run compile check**

Run:

```powershell
..\..\.venv\Scripts\python.exe -m py_compile ui/streamlit_app.py ui/app_navigation.py
```

Expected: exit code `0`.

- [ ] **Step 8: Commit**

Run:

```powershell
git add ui/streamlit_app.py tests/test_streamlit_demo_execution_helpers.py
git commit -m "feat: add connection-first app shell"
```

---

## Task 4: Move Scanner Jobs Out Of Monitor

**Files:**
- Modify: `ui/streamlit_app.py`
- Modify: `tests/test_streamlit_demo_execution_helpers.py`

- [ ] **Step 1: Add source test proving scanner controls are isolated**

Add to `tests/test_streamlit_demo_execution_helpers.py`:

```python
def test_scanner_jobs_page_owns_scan_controls_and_jobs_table() -> None:
    scanner_source = _function_source("render_scanner_jobs_page")
    monitor_source = _function_source("render_monitor_page")

    assert "Start job" in scanner_source
    assert 'st.header("Jobs")' in scanner_source
    assert "Job type" in scanner_source
    assert "Start job" not in monitor_source
    assert 'st.header("Jobs")' not in monitor_source
```

- [ ] **Step 2: Run test to verify RED**

Run:

```powershell
..\..\.venv\Scripts\pytest.exe tests/test_streamlit_demo_execution_helpers.py::test_scanner_jobs_page_owns_scan_controls_and_jobs_table -q
```

Expected: fails because scanner controls have not been moved into `render_scanner_jobs_page`.

- [ ] **Step 3: Move scan settings into `render_scanner_jobs_page`**

Replace the stub `render_scanner_jobs_page` with a function that contains the old sidebar scan settings and job start logic, but uses normal page controls rather than `st.sidebar`:

```python
def render_scanner_jobs_page(api_url: str, auto_refresh: bool) -> None:
    st.header("Scanner Jobs")
    with st.expander("Scan settings", expanded=True):
        job_mode = st.radio("Job type", ["Archive scan", "Causal signal scan", "TP/SL optimizer"], horizontal=True)
        start = st.text_input("Start date", "2026-03-18")
        end = st.text_input("End date", "2026-03-27")
        symbols_raw = st.text_area("Symbols", "EIGENUSDT,GRASSUSDT,RVNUSDT,ENJUSDT,JTOUSDT,STGUSDT,ENAUSDT", height=100)
        full_universe = st.checkbox("Full archive universe", value=False)
        max_symbols = st.number_input("Max symbols", min_value=0, max_value=2000, value=0, step=10)
        min_turnover = st.number_input("Min turnover USDT", min_value=0, value=1_000_000, step=250_000)
        weak_threshold = st.slider("Weak threshold", 0, 15, 9)
        pump_threshold = st.slider("Pump threshold", 0, 15, 9)
        tp_weak = st.number_input("TP weak underlying", value=0.06, min_value=0.001, max_value=1.0, step=0.01, format="%.3f")
        sl_weak = st.number_input("SL weak underlying", value=0.07, min_value=0.001, max_value=1.0, step=0.01, format="%.3f")
        tp_pump = st.number_input("TP pump underlying", value=0.08, min_value=0.001, max_value=1.0, step=0.01, format="%.3f")
        sl_pump = st.number_input("SL pump underlying", value=0.07, min_value=0.001, max_value=1.0, step=0.01, format="%.3f")
        max_hold_min = st.number_input("Max hold minutes", min_value=15, max_value=1440, value=720, step=15)
        if job_mode == "TP/SL optimizer":
            tp_grid_raw = st.text_input("TP grid", "0.04,0.06,0.08")
            sl_grid_raw = st.text_input("SL grid", "0.05,0.07")
        run = st.button("Start job", type="primary")

    if run:
        symbols = [s.strip().upper() for s in symbols_raw.replace("\n", ",").split(",") if s.strip()]
        payload = {
            "start": start,
            "end": end,
            "symbols": symbols,
            "full_universe": full_universe,
            "include_majors": False,
            "max_symbols": int(max_symbols),
            "min_turnover": float(min_turnover),
            "weak_threshold": int(weak_threshold),
            "pump_threshold": int(pump_threshold),
            "tp_weak": float(tp_weak),
            "sl_weak": float(sl_weak),
            "tp_pump": float(tp_pump),
            "sl_pump": float(sl_pump),
            "max_hold_min": float(max_hold_min),
        }
        try:
            path = "/jobs/scan"
            if job_mode == "Causal signal scan":
                path = "/jobs/scan-causal"
            if job_mode == "TP/SL optimizer":
                payload["tp_grid"] = parse_float_grid(tp_grid_raw)
                payload["sl_grid"] = parse_float_grid(sl_grid_raw)
                path = "/jobs/optimize-tp-sl"
            resp = api_post(path, payload, api_url).json()
            st.session_state["selected_job_id"] = resp["job_id"]
            st.success(f"Job queued: {resp['job_id']}")
        except Exception as exc:
            st.error(f"Failed to start job: {exc}")

    render_jobs_table(api_url, auto_refresh=auto_refresh, show_results=False)
```

- [ ] **Step 4: Extract jobs table helper**

Create a helper before `render_scanner_jobs_page`:

```python
def render_jobs_table(api_url: str, *, auto_refresh: bool, show_results: bool) -> str | None:
    selected_job = None
    try:
        jobs = api_get("/jobs", api_url).json()
        if jobs:
            jobs_df = pd.DataFrame(jobs)
            if "created_at" in jobs_df.columns:
                jobs_df = jobs_df.sort_values("created_at", ascending=False, na_position="last")
            display_columns = [
                col
                for col in [
                    "job_id",
                    "job_type",
                    "status",
                    "message",
                    "metrics_rows",
                    "trades_rows",
                    "signals_rows",
                    "evaluations_rows",
                    "grid_rows",
                    "grid_trades_rows",
                    "created_at",
                    "updated_at",
                ]
                if col in jobs_df.columns
            ]
            st.header("Jobs")
            st.dataframe(jobs_df[display_columns], use_container_width=True, hide_index=True)
            job_ids = jobs_df["job_id"].tolist()
            selected_from_state = st.session_state.get("selected_job_id")
            default_index = job_ids.index(selected_from_state) if selected_from_state in job_ids else 0
            selected_job = st.selectbox("Open job", job_ids, index=default_index)
            st.session_state["selected_job_id"] = selected_job
        else:
            st.info("No jobs yet. Start a scan from Scanner Jobs.")
    except Exception as exc:
        st.warning(f"Backend is not reachable yet: {exc}")

    if show_results and selected_job:
        render_selected_job_results(api_url, selected_job, auto_refresh=auto_refresh)
    return selected_job
```

- [ ] **Step 5: Extract selected job results helper**

Move the old `if selected_job:` result-rendering block into a function with this signature:

```python
def render_selected_job_results(api_url: str, selected_job: str, *, auto_refresh: bool) -> None:
    """Render metadata, status, downloads, tables and charts for one selected job."""
```

The body is a mechanical move of the current selected-job result code. The moved code starts with `try: meta = api_get(f"/jobs/{selected_job}", api_url).json()` and ends with the final `st.info("No candidate trades in this job.")` branch. Do not change branch behavior in this task; only replace top-level variable reads with the function arguments.

- [ ] **Step 6: Remove old top-level sidebar/jobs path**

Delete the old top-level `with st.sidebar:` scan settings block and old top-level `st.header("Jobs")` block after the router. The only `st.header("Jobs")` should now be inside `render_jobs_table`.

- [ ] **Step 7: Run tests**

Run:

```powershell
..\..\.venv\Scripts\pytest.exe tests/test_streamlit_demo_execution_helpers.py tests/test_backend_api.py tests/test_ui_summary.py tests/test_table_totals.py -q
```

Expected: all pass.

- [ ] **Step 8: Commit**

Run:

```powershell
git add ui/streamlit_app.py tests/test_streamlit_demo_execution_helpers.py
git commit -m "refactor: move scanner jobs into secondary page"
```

---

## Task 5: Move Reports And Execution History Into Secondary Pages

**Files:**
- Modify: `ui/streamlit_app.py`
- Modify: `tests/test_streamlit_demo_execution_helpers.py`

- [ ] **Step 1: Add source tests for reports/history separation**

Add:

```python
def test_reports_page_owns_job_result_details() -> None:
    reports_source = _function_source("render_reports_page")
    monitor_source = _function_source("render_monitor_page")

    assert "render_jobs_table" in reports_source
    assert "show_results=True" in reports_source
    assert "render_selected_job_results" not in monitor_source


def test_execution_history_page_owns_journal_table() -> None:
    history_source = _function_source("render_execution_history_page")
    monitor_source = _function_source("render_monitor_page")

    assert "/execution/demo/journal?limit=100" in history_source
    assert "Execution History" in history_source
    assert "/execution/demo/journal?limit=25" not in monitor_source
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```powershell
..\..\.venv\Scripts\pytest.exe tests/test_streamlit_demo_execution_helpers.py::test_reports_page_owns_job_result_details tests/test_streamlit_demo_execution_helpers.py::test_execution_history_page_owns_journal_table -q
```

Expected: fails because reports/history still use stubs or Monitor journal loading.

- [ ] **Step 3: Implement Reports page**

Replace `render_reports_page` with:

```python
def render_reports_page(api_url: str, auto_refresh: bool) -> None:
    st.header("Reports")
    st.caption("Backtest summaries, optimizer results and historical result charts.")
    render_jobs_table(api_url, auto_refresh=auto_refresh, show_results=True)
```

- [ ] **Step 4: Implement Execution History page**

Replace `render_execution_history_page` with:

```python
def render_execution_history_page(api_url: str, execution_token: str) -> None:
    st.header("Execution History")
    if not execution_token:
        st.info("Reconnect with an execution token to view the local execution journal.")
        return
    journal_payload, journal_error = api_json_or_error("/execution/demo/journal?limit=100", api_url, token=execution_token)
    if journal_error:
        st.warning(f"Execution history unavailable: {journal_error}")
        return
    journal_frame = _frame_from_rows(_journal_rows(journal_payload))
    if journal_frame.empty:
        st.info("No execution history rows.")
        return
    history_columns = [
        column
        for column in [
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
        if column in journal_frame.columns
    ]
    st.dataframe(journal_frame[history_columns], use_container_width=True, hide_index=True)
```

- [ ] **Step 5: Stop Monitor from loading journal**

In `render_bot_monitor`, remove:

```python
journal_payload = None
journal_error = None
journal_payload, journal_error = api_json_or_error("/execution/demo/journal?limit=25", api_url, token=execution_token)
journal_rows = _journal_rows(journal_payload)
journal_frame = _frame_from_rows(journal_rows)
```

Also remove the Monitor section that starts with `st.subheader("Execution History")` and renders `journal_frame`. The Monitor must not render raw journal rows.

- [ ] **Step 6: Run tests**

Run:

```powershell
..\..\.venv\Scripts\pytest.exe tests/test_streamlit_demo_execution_helpers.py -q
```

Expected: all pass.

- [ ] **Step 7: Commit**

Run:

```powershell
git add ui/streamlit_app.py tests/test_streamlit_demo_execution_helpers.py
git commit -m "refactor: move reports and history into menu pages"
```

---

## Task 6: Simplify Monitor Page To Only Live Overview

**Files:**
- Modify: `ui/streamlit_app.py`
- Modify: `tests/test_streamlit_demo_execution_helpers.py`

- [ ] **Step 1: Add source test for clean Monitor**

Add:

```python
def test_monitor_page_shows_only_clean_live_overview() -> None:
    bot_monitor_source = _function_source("render_bot_monitor")

    assert "build_executive_overview_html" in bot_monitor_source
    assert "build_visual_panels_html" in bot_monitor_source
    assert "_render_monitor_visual_charts" in bot_monitor_source
    assert "st.dataframe(positions_frame" not in bot_monitor_source
    assert "st.dataframe(orders_frame" not in bot_monitor_source
    assert "Execution History" not in bot_monitor_source
    assert "Controlled demo test short" not in bot_monitor_source
```

- [ ] **Step 2: Run test to verify RED**

Run:

```powershell
..\..\.venv\Scripts\pytest.exe tests/test_streamlit_demo_execution_helpers.py::test_monitor_page_shows_only_clean_live_overview -q
```

Expected: fails because Monitor still renders detail dataframes and demo test form.

- [ ] **Step 3: Remove detail tables from Monitor**

In `render_bot_monitor`, keep:

```python
positions_frame = _frame_from_rows(positions_rows)
_render_variant_a_visual_overview(
    health_error=health_error,
    status_payload=status_payload,
    limits=limits,
    execution_token=execution_token,
    wallet_summary=wallet_summary,
    positions_rows=positions_rows,
    orders_rows=orders_rows,
    scanner_watchlist=scanner_watchlist,
)
_render_monitor_visual_charts(positions_frame, scanner_watchlist)
```

Remove from Monitor:

```python
main_left, main_right = st.columns(2)
st.dataframe(positions_frame, use_container_width=True, hide_index=True)
st.dataframe(scanner_watchlist, use_container_width=True, hide_index=True)
secondary_left, secondary_right = st.columns(2)
st.dataframe(orders_frame, use_container_width=True, hide_index=True)
with st.expander("Controlled demo test short", expanded=False):
    render_demo_test_short_form(api_url, execution_token, status_payload)
```

- [ ] **Step 4: Keep open orders in visual summary only**

Keep the existing `orders_rows = normalize_open_orders(orders_payload)` assignment because it is used for counts and TP/SL inference. Do not render the orders table in Monitor.

- [ ] **Step 5: Run tests**

Run:

```powershell
..\..\.venv\Scripts\pytest.exe tests/test_streamlit_demo_execution_helpers.py tests/test_bot_monitor_visual.py tests/test_bot_monitor.py -q
```

Expected: all pass.

- [ ] **Step 6: Commit**

Run:

```powershell
git add ui/streamlit_app.py tests/test_streamlit_demo_execution_helpers.py
git commit -m "refactor: simplify monitor live overview"
```

---

## Task 7: Move Connection Controls And Demo Test Short Into Settings

**Files:**
- Modify: `ui/streamlit_app.py`
- Modify: `tests/test_streamlit_demo_execution_helpers.py`

- [ ] **Step 1: Add source test for Settings**

Add:

```python
def test_settings_page_owns_connection_and_demo_controls() -> None:
    settings_source = _function_source("render_settings_page")
    monitor_source = _function_source("render_monitor_page")

    assert "Backend API URL" in settings_source
    assert "Execution API token" in settings_source
    assert "render_demo_test_short_form" in settings_source
    assert "Backend API URL" not in monitor_source
    assert "Execution API token" not in monitor_source
    assert "render_demo_test_short_form" not in monitor_source
```

- [ ] **Step 2: Run test to verify RED**

Run:

```powershell
..\..\.venv\Scripts\pytest.exe tests/test_streamlit_demo_execution_helpers.py::test_settings_page_owns_connection_and_demo_controls -q
```

Expected: fails because Settings does not own those controls yet.

- [ ] **Step 3: Implement Settings page**

Replace `render_settings_page` with:

```python
def render_settings_page(api_url: str, execution_token: str) -> None:
    st.header("Settings")
    st.caption("Connection settings are session-local and are not written to disk.")

    new_api_url = st.text_input("Backend API URL", api_url).rstrip("/")
    new_token = st.text_input("Execution API token", value="", type="password")
    if st.button("Reconnect", type="primary"):
        token_to_use = new_token or execution_token
        ok, messages = validate_connection(new_api_url, token_to_use)
        for message in messages:
            if "failed" in message.lower() or "unavailable" in message.lower() or "required" in message.lower():
                st.error(message)
            else:
                st.info(message)
        if ok:
            mark_connected(st.session_state, api_url=new_api_url, execution_token=token_to_use)
            st.success("Connection updated.")
            st.rerun()

    status_payload, status_error = api_json_or_error("/execution/demo/status", api_url)
    if status_error:
        st.warning(f"Execution status unavailable: {status_error}")
    else:
        st.json(
            {
                "mode": status_payload.get("mode"),
                "enabled": status_payload.get("enabled"),
                "configured": status_payload.get("configured"),
                "limits": status_payload.get("limits"),
                "api_token_configured": status_payload.get("api_token_configured"),
            }
        )

    with st.expander("Controlled demo test short", expanded=False):
        render_demo_test_short_form(api_url, execution_token, status_payload or {})
```

- [ ] **Step 4: Update demo test short missing-token message**

In `render_demo_test_short_form`, replace:

```python
st.error("Enter the execution API token in the sidebar before placing a demo test short.")
```

with:

```python
st.error("Connect with an execution API token before placing a demo test short.")
```

- [ ] **Step 5: Run tests**

Run:

```powershell
..\..\.venv\Scripts\pytest.exe tests/test_streamlit_demo_execution_helpers.py -q
```

Expected: all pass.

- [ ] **Step 6: Commit**

Run:

```powershell
git add ui/streamlit_app.py tests/test_streamlit_demo_execution_helpers.py
git commit -m "feat: move connection controls to settings"
```

---

## Task 8: Verification And Runtime Smoke

**Files:**
- Verify repository state.

- [ ] **Step 1: Run full tests**

Run:

```powershell
..\..\.venv\Scripts\pytest.exe -q
```

Expected: all tests pass.

- [ ] **Step 2: Run compile check**

Run:

```powershell
..\..\.venv\Scripts\python.exe -m py_compile ui/app_navigation.py ui/bot_monitor.py ui/bot_monitor_visual.py ui/streamlit_app.py backend/app/execution_routes.py bybit_weak_intraday/execution/journal.py
```

Expected: exit code `0`.

- [ ] **Step 3: Run whitespace check**

Run:

```powershell
git diff --check
```

Expected: no output.

- [ ] **Step 4: Runtime smoke**

If local feature backend/UI are still running on ports `8001` and `8502`, restart them so the new app shell loads. If those ports are occupied by this project, stop only those project processes after checking process command lines.

Start backend:

```powershell
..\..\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8001
```

Start Streamlit:

```powershell
$env:BWI_API_URL='http://127.0.0.1:8001'
..\..\.venv\Scripts\python.exe -m streamlit run ui\streamlit_app.py --server.address 127.0.0.1 --server.port 8502 --server.headless true --browser.gatherUsageStats false
```

Check:

```powershell
Invoke-RestMethod http://127.0.0.1:8001/health
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8502/_stcore/health
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8502
```

Expected:

```text
Backend health returns status ok.
Streamlit health returns ok.
UI returns HTTP 200.
```

- [ ] **Step 5: Manual UI checklist**

Open:

```text
http://127.0.0.1:8502
```

Verify:

```text
Initial view is Bybit Demo Connection.
After token connection, Monitor is the default page.
Monitor has no Jobs table.
Monitor has no scan settings.
Monitor has no token/backend inputs.
Monitor shows only the simplified Bot Monitor live overview.
Reports, Scanner Jobs, Execution History and Settings are accessible from the menu.
Settings contains reconnect and controlled demo test short.
No execution token is visible in errors or page text.
```

- [ ] **Step 6: Commit final docs only if needed**

If README or PR docs are updated with the new navigation note:

```powershell
git add README.md docs
git commit -m "docs: describe clean monitor navigation"
```

Do not create an empty commit.

- [ ] **Step 7: Push branch**

Run:

```powershell
git push
```

Expected: PR #11 updates with the clean monitor navigation work.

---

## Self-Review Checklist

- Spec coverage:
  - Start screen: Task 3.
  - Session-local API URL/token state: Tasks 1 and 3.
  - Clean Monitor only: Task 6.
  - Separate Reports menu: Task 5.
  - Separate Scanner Jobs menu: Task 4.
  - Separate Execution History menu: Task 5.
  - Settings owns token/API controls: Task 7.
  - Existing jobs/reports behavior retained: Tasks 4 and 5.
  - Verification and runtime check: Task 8.

- Placeholder scan:
  - This plan contains no `TBD`, `TODO`, `FIXME`, or unspecified file paths.

- Type consistency:
  - Session keys are defined in `ui/app_navigation.py` and imported into `ui/streamlit_app.py`.
  - Page labels match `NAV_PAGES`.
  - `render_jobs_table` returns `str | None`.
  - `render_selected_job_results` receives `api_url`, `selected_job`, and `auto_refresh`.
