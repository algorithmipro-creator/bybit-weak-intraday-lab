from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

import pytest


def _load_streamlit_helpers(*names: str) -> dict:
    source = Path("ui/streamlit_app.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    selected = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in set(names)
    ]
    module = ast.Module(body=selected, type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = {"requests": None}
    exec(compile(module, "ui/streamlit_app.py", "exec"), namespace)
    return namespace


def _function_source(function_name: str) -> str:
    source = Path("ui/streamlit_app.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == function_name:
            return ast.get_source_segment(source, node) or ""
    raise AssertionError(f"Function {function_name} not found")


def test_streamlit_app_defines_clean_navigation_pages() -> None:
    source = Path("ui/streamlit_app.py").read_text(encoding="utf-8")

    assert "render_connection_screen" in source
    assert "render_app_menu" in source
    assert "render_monitor_page" in source
    assert "render_reports_page" in source
    assert "render_scanner_jobs_page" in source
    assert "render_signal_decisions_page" in source
    assert "render_execution_history_page" in source
    assert "render_settings_page" in source


def test_app_shell_uses_compact_header_and_constrained_width() -> None:
    source = Path("ui/streamlit_app.py").read_text(encoding="utf-8")
    shell_source = _function_source("render_app_shell_chrome")

    assert 'st.title("Bybit Weak Intraday Lab")' not in source
    assert "bwi-app-title" in shell_source
    assert "bwi-app-subtitle" in shell_source
    assert ".block-container" in shell_source
    assert "max-width: 1360px" in shell_source
    assert "padding-top: 1.1rem" in shell_source
    assert "unsafe_allow_html=True" in shell_source


def test_monitor_page_does_not_render_jobs_or_connection_inputs() -> None:
    monitor_source = _function_source("render_monitor_page")
    bot_monitor_source = _function_source("render_bot_monitor")

    assert "render_bot_monitor(api_url, execution_token)" in monitor_source
    assert "st.caption" not in monitor_source
    assert 'st.header("Bot Monitor")' not in bot_monitor_source
    assert "api_json_or_error" not in monitor_source
    assert "Start Scan Job" not in monitor_source
    assert "Start Job" not in monitor_source
    assert "Scanner Jobs" not in monitor_source
    assert "Backend API URL" not in monitor_source
    assert "Execution token" not in monitor_source


def test_scanner_jobs_page_owns_scan_controls_and_jobs_table() -> None:
    scanner_source = _function_source("render_scanner_jobs_page")
    monitor_source = _function_source("render_monitor_page")

    assert "Start job" in scanner_source
    assert 'st.header("Jobs")' in scanner_source or "render_jobs_table" in scanner_source
    assert "Job type" in scanner_source
    assert "show_results=True" in scanner_source
    assert "Start job" not in monitor_source
    assert 'st.header("Jobs")' not in monitor_source


def test_selected_job_results_render_completed_job_outputs() -> None:
    results_source = _function_source("render_selected_job_results")

    assert "/trades.csv" in results_source
    assert "/grid.csv" in results_source
    assert "/signals.csv" in results_source
    assert "render_account_backtest" in results_source


def test_scanner_jobs_page_owns_auto_refresh_toggle() -> None:
    scanner_source = _function_source("render_scanner_jobs_page")

    assert "Auto-refresh active jobs" in scanner_source
    assert "st.checkbox" in scanner_source
    assert "auto_refresh=active_jobs_auto_refresh" in scanner_source


def test_scanner_jobs_page_renders_active_job_lifecycle_above_history() -> None:
    scanner_source = _function_source("render_scanner_jobs_page")
    active_source = _function_source("render_active_job_overview")
    candidates_source = _function_source("render_latest_job_candidates")

    assert "render_active_job_overview" in scanner_source
    assert "render_jobs_table(api_url, auto_refresh=False, show_results=True, jobs=jobs)" in scanner_source
    assert "if active_jobs_auto_refresh and active_meta" in scanner_source
    assert "Active Job" in active_source
    assert "Status" in active_source
    assert "Type" in active_source
    assert "Metrics rows" in active_source
    assert "Signals" in active_source
    assert "Trades" in active_source
    assert "Updated" in active_source
    assert "render_latest_job_candidates(api_url, meta)" in active_source
    assert "Latest candidates" in candidates_source
    assert "build_scanner_watchlist" in candidates_source


def test_active_job_overview_renders_progress_cache_stats_and_warnings() -> None:
    active_source = _function_source("render_active_job_overview")
    progress_source = _function_source("render_job_progress")

    assert "render_job_progress(meta)" in active_source
    assert "st.progress" in progress_source
    assert "symbol-days" in progress_source
    assert "Now scanning" in progress_source
    assert "Cache" in progress_source
    assert "cache_hits" in progress_source
    assert "downloads" in progress_source
    assert "missing_files" in progress_source
    assert "warnings" in progress_source


def test_reports_page_owns_job_result_details() -> None:
    reports_source = _function_source("render_reports_page")
    monitor_source = _function_source("render_monitor_page")
    bot_monitor_source = _function_source("render_bot_monitor")

    assert "render_jobs_table" in reports_source
    assert "show_results=True" in reports_source
    assert "auto_refresh=False" in reports_source
    assert "Auto-refresh active jobs" not in reports_source
    assert "render_selected_job_results" not in monitor_source
    assert "render_selected_job_results" not in bot_monitor_source


def test_execution_history_page_owns_journal_table() -> None:
    history_source = _function_source("render_execution_history_page")
    monitor_source = _function_source("render_bot_monitor")

    assert "/execution/demo/journal?limit=100" in history_source
    assert "Execution History" in history_source
    assert "/execution/demo/journal?limit=25" not in monitor_source


def test_execution_token_messages_do_not_reference_sidebar() -> None:
    monitor_source = _function_source("render_bot_monitor")
    form_source = _function_source("render_demo_test_short_form")

    assert "sidebar" not in monitor_source
    assert "sidebar" not in form_source


def test_monitor_page_shows_only_clean_live_overview() -> None:
    bot_monitor_source = _function_source("render_bot_monitor")

    assert "_render_variant_a_visual_overview" in bot_monitor_source
    assert "_render_monitor_visual_charts" in bot_monitor_source
    assert "st.dataframe(positions_frame" not in bot_monitor_source
    assert "st.dataframe(orders_frame" not in bot_monitor_source
    assert "st.dataframe(scanner_watchlist" not in bot_monitor_source
    assert "Execution History" not in bot_monitor_source
    assert "Controlled demo test short" not in bot_monitor_source
    assert "render_demo_test_short_form" not in bot_monitor_source
    assert "render_selected_job_results" not in bot_monitor_source


def test_connection_screen_owns_connection_inputs() -> None:
    connection_source = _function_source("render_connection_screen")

    assert "Backend API URL" in connection_source
    assert "Execution token" in connection_source
    assert "Connect" in connection_source


def test_settings_page_owns_connection_and_demo_controls() -> None:
    settings_source = _function_source("render_settings_page")
    monitor_source = _function_source("render_monitor_page")
    bot_monitor_source = _function_source("render_bot_monitor")

    assert "Backend API URL" in settings_source
    assert "Execution token" in settings_source
    assert "render_demo_test_short_form" in settings_source
    assert "Reconnect" in settings_source
    assert "Backend API URL" not in monitor_source
    assert "Execution token" not in monitor_source
    assert "Reconnect" not in monitor_source
    assert "render_demo_test_short_form" not in monitor_source
    assert "Backend API URL" not in bot_monitor_source
    assert "Execution token" not in bot_monitor_source
    assert "Execution API token" not in bot_monitor_source
    assert "API token" not in bot_monitor_source
    assert "Reconnect" not in bot_monitor_source
    assert "render_demo_test_short_form" not in bot_monitor_source


def test_settings_reconnect_feedback_uses_session_flash_before_rerun() -> None:
    settings_source = _function_source("render_settings_page")

    assert "settings_reconnect_flash" in settings_source
    assert "st.session_state.pop" in settings_source
    assert "st.session_state[\"settings_reconnect_flash\"]" in settings_source
    assert "st.success(message)" not in settings_source
    assert "st.rerun()" in settings_source


def test_secondary_menu_contains_clean_monitor_sections() -> None:
    menu_source = _function_source("render_app_menu")

    assert "NAV_PAGES" in menu_source
    assert "Monitor" in menu_source
    assert "Reports" in menu_source
    assert "Scanner Jobs" in menu_source
    assert "Signal Decisions" in menu_source
    assert "Execution History" in menu_source
    assert "Settings" in menu_source


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


def test_bot_monitor_uses_visual_overview_and_charts() -> None:
    source = _function_source("render_bot_monitor")

    assert "_render_variant_a_visual_overview" in source
    assert "_render_monitor_visual_charts" in source


def test_variant_a_visual_overview_uses_visual_builders() -> None:
    source = _function_source("_render_variant_a_visual_overview")

    assert "build_executive_overview_html" in source
    assert "build_visual_panels_html" in source


def test_monitor_charts_do_not_force_dark_backgrounds() -> None:
    source = _function_source("_style_monitor_figure")

    assert "#101418" not in source
    assert "paper_bgcolor" not in source
    assert "plot_bgcolor" not in source


class FakeResponse:
    def __init__(self, payload=None):
        self.payload = payload or {}

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self.payload


def test_api_get_passes_execution_token_header_only_when_provided() -> None:
    helpers = _load_streamlit_helpers("api_get")
    calls = []

    def fake_get(url, *, timeout, headers=None):
        calls.append({"url": url, "timeout": timeout, "headers": headers})
        return FakeResponse()

    helpers["requests"] = SimpleNamespace(get=fake_get)

    helpers["api_get"]("/jobs", "http://api")
    helpers["api_get"]("/execution/demo/wallet", "http://api", token="secret-token")

    assert calls == [
        {"url": "http://api/jobs", "timeout": 30, "headers": None},
        {
            "url": "http://api/execution/demo/wallet",
            "timeout": 30,
            "headers": {"X-BWI-Execution-Token": "secret-token"},
        },
    ]


def test_api_post_passes_execution_token_header_only_when_provided() -> None:
    helpers = _load_streamlit_helpers("api_post")
    calls = []

    def fake_post(url, *, json, timeout, headers=None):
        calls.append({"url": url, "json": json, "timeout": timeout, "headers": headers})
        return FakeResponse()

    helpers["requests"] = SimpleNamespace(post=fake_post)

    helpers["api_post"]("/jobs/scan", {"symbols": ["ENAUSDT"]}, "http://api")
    helpers["api_post"](
        "/execution/demo/place-test-short",
        {"symbol": "ENAUSDT"},
        "http://api",
        token="secret-token",
    )

    assert calls == [
        {
            "url": "http://api/jobs/scan",
            "json": {"symbols": ["ENAUSDT"]},
            "timeout": 30,
            "headers": None,
        },
        {
            "url": "http://api/execution/demo/place-test-short",
            "json": {"symbol": "ENAUSDT"},
            "timeout": 30,
            "headers": {"X-BWI-Execution-Token": "secret-token"},
        },
    ]


def test_api_json_or_error_redacts_token_from_errors() -> None:
    helpers = _load_streamlit_helpers("_safe_error", "api_json_or_error")

    def fake_api_get(path, api_url, token=None):
        raise RuntimeError(f"bad token {token}")

    helpers["api_get"] = fake_api_get

    payload, error = helpers["api_json_or_error"](
        "/execution/demo/wallet",
        "http://api",
        token="secret-token",
    )

    assert payload is None
    assert error == "bad token [redacted]"


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        (None, []),
        ({}, []),
        ({"result": {"list": [{"symbol": "ENAUSDT"}]}}, [{"symbol": "ENAUSDT"}]),
        ({"result": {"list": None}}, []),
    ],
)
def test_result_list_extracts_bybit_result_list(payload, expected) -> None:
    helpers = _load_streamlit_helpers("_result_list")

    assert helpers["_result_list"](payload) == expected


def test_journal_rows_extracts_top_level_rows() -> None:
    helpers = _load_streamlit_helpers("_journal_rows")
    journal_rows = helpers.get("_journal_rows")

    assert journal_rows is not None
    assert journal_rows(
        {
            "rows": [
                {
                    "symbol": "ENAUSDT",
                    "side": "Sell",
                    "qty": "1",
                }
            ],
            "limit": 25,
            "count": 1,
        }
    ) == [
        {
            "symbol": "ENAUSDT",
            "side": "Sell",
            "qty": "1",
        }
    ]


@pytest.mark.parametrize(
    "payload",
    [
        {"rows": "not-a-list"},
        {"rows": {"symbol": "ENAUSDT"}},
        {"rows": ["bad", 1, None]},
    ],
)
def test_journal_rows_returns_empty_list_for_malformed_rows(payload) -> None:
    helpers = _load_streamlit_helpers("_journal_rows")

    assert helpers["_journal_rows"](payload) == []


def test_journal_rows_keeps_only_dict_rows() -> None:
    helpers = _load_streamlit_helpers("_journal_rows")

    assert helpers["_journal_rows"]({"rows": [{"symbol": "ENAUSDT"}, "bad", 1, None]}) == [{"symbol": "ENAUSDT"}]
