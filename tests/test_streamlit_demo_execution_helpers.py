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
    assert "render_execution_history_page" in source
    assert "render_settings_page" in source


def test_monitor_page_does_not_render_jobs_or_connection_inputs() -> None:
    monitor_source = _function_source("render_monitor_page")

    assert "render_bot_monitor(api_url, execution_token)" in monitor_source
    assert "api_json_or_error" not in monitor_source
    assert "Start Scan Job" not in monitor_source
    assert "Start Job" not in monitor_source
    assert "Scanner Jobs" not in monitor_source
    assert "Backend API URL" not in monitor_source
    assert "Execution token" not in monitor_source
    assert "Bot Monitor" in monitor_source
    assert "Open Positions" in monitor_source
    assert "Scanner Watchlist" in monitor_source


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


def test_connection_screen_owns_connection_inputs() -> None:
    connection_source = _function_source("render_connection_screen")

    assert "Backend API URL" in connection_source
    assert "Execution token" in connection_source
    assert "Connect" in connection_source


def test_secondary_menu_contains_clean_monitor_sections() -> None:
    menu_source = _function_source("render_app_menu")

    assert "NAV_PAGES" in menu_source
    assert "Monitor" in menu_source
    assert "Reports" in menu_source
    assert "Scanner Jobs" in menu_source
    assert "Execution History" in menu_source
    assert "Settings" in menu_source


def test_bot_monitor_uses_variant_a_visual_overview_before_tables() -> None:
    source = Path("ui/streamlit_app.py").read_text(encoding="utf-8")

    assert "build_executive_overview_html" in source
    assert "build_visual_panels_html" in source
    assert source.index("build_executive_overview_html") < source.index("st.dataframe(positions_frame")


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
