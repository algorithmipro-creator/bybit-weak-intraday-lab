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
    assert NAV_PAGES == ("Monitor", "Reports", "Scanner Jobs", "Signal Decisions", "Execution History", "Settings")


def test_ensure_navigation_state_sets_defaults_without_overwriting_existing_values() -> None:
    state = {
        "bwi_api_url": "http://custom:8000",
        "bwi_execution_token": "secret",
        "bwi_connected": True,
        "bwi_selected_page": "Reports",
    }

    ensure_navigation_state(state, default_api_url="http://default:8000")

    assert state["bwi_api_url"] == "http://custom:8000"
    assert state["bwi_execution_token"] == "secret"
    assert state["bwi_connected"] is True
    assert state["bwi_selected_page"] == "Reports"


def test_ensure_navigation_state_sets_missing_defaults() -> None:
    state = {}

    ensure_navigation_state(state, default_api_url="http://default:8000/")

    assert state["bwi_api_url"] == "http://default:8000"
    assert state["bwi_execution_token"] == ""
    assert state["bwi_connected"] is False
    assert state["bwi_selected_page"] == "Monitor"


def test_ensure_navigation_state_normalizes_invalid_existing_selected_page() -> None:
    state = {"bwi_selected_page": "Unknown"}

    ensure_navigation_state(state, default_api_url="http://default:8000")

    assert state["bwi_selected_page"] == "Monitor"


def test_mark_connected_stores_session_local_connection_values() -> None:
    state = {}
    ensure_navigation_state(state, default_api_url="http://default:8000")

    mark_connected(state, api_url="http://api:8000/", execution_token="  token  ")

    assert is_connected(state) is True
    assert state["bwi_api_url"] == "http://api:8000"
    assert state["bwi_execution_token"] == "token"
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


def test_connection_values_normalizes_and_trims_stored_values() -> None:
    state = {
        "bwi_api_url": "http://api:8000/",
        "bwi_execution_token": "  token  ",
        "bwi_selected_page": "bad-page",
    }

    assert connection_values(state) == {
        "api_url": "http://api:8000",
        "execution_token": "token",
        "selected_page": "Monitor",
    }
