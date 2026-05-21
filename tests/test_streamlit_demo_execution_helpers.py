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
