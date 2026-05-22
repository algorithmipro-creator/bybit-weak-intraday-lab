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
