from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import requests
from fastapi.testclient import TestClient

from backend.app import main, signal_routes
from bybit_weak_intraday.execution.bybit_demo import BybitDemoAPIError
from bybit_weak_intraday.signals.journal import append_decision_event, read_decision_journal

client = TestClient(main.app)
TOKEN = "signal-token"


def _headers(token: str = TOKEN) -> dict[str, str]:
    return {"X-BWI-Execution-Token": token}


def _patch_signal_settings(monkeypatch, tmp_path, **overrides):
    monkeypatch.setattr(signal_routes.settings, "execution_api_token", TOKEN)
    monkeypatch.setattr(signal_routes.settings, "signal_decision_journal_path", tmp_path / "signal_decisions.csv")
    monkeypatch.setattr(signal_routes.settings, "signal_min_score", 9.0)
    monkeypatch.setattr(signal_routes.settings, "signal_auto_entry_enabled", False)
    monkeypatch.setattr(signal_routes.settings, "signal_default_notional_usdt", 25.0)
    monkeypatch.setattr(signal_routes.settings, "signal_take_profit_pct", 0.06)
    monkeypatch.setattr(signal_routes.settings, "signal_stop_loss_pct", 0.07)
    monkeypatch.setattr(signal_routes.settings, "signal_cooldown_minutes", 60)
    monkeypatch.setattr(signal_routes.settings, "telegram_enabled", False)
    monkeypatch.setattr(signal_routes.settings, "telegram_bot_token", "")
    monkeypatch.setattr(signal_routes.settings, "telegram_chat_id", "")
    for key, value in overrides.items():
        monkeypatch.setattr(signal_routes.settings, key, value)


def _execution_config(*, enabled: bool = True, whitelist=("ENAUSDT", "JTOUSDT")):
    return signal_routes.ExecutionConfig(
        execution_mode="demo",
        execution_enabled=enabled,
        api_key="key",
        api_secret="secret",
        base_url=signal_routes.DEMO_BASE_URL,
        symbol_whitelist=tuple(whitelist),
        max_demo_notional_usdt=25.0,
        max_open_positions=3,
        max_daily_test_orders=3,
    )


def _candidate(symbol: str = "ENAUSDT", score: float = 9.0) -> dict:
    return {
        "symbol": symbol,
        "mode": "causal",
        "score": score,
        "time_utc": "2026-05-22T10:00:00+00:00",
        "price": 1.0,
    }


def test_telegram_status_redacts_config(monkeypatch, tmp_path):
    _patch_signal_settings(
        monkeypatch,
        tmp_path,
        telegram_enabled=True,
        telegram_bot_token="secret-token",
        telegram_chat_id="123456",
    )

    response = client.get("/signals/telegram/status")

    assert response.status_code == 200
    body = response.json()
    assert body == {"enabled": True, "bot_token_configured": True, "chat_id_configured": True}
    assert "secret-token" not in str(body)
    assert "123456" not in str(body)


def test_telegram_test_requires_execution_token(monkeypatch, tmp_path):
    _patch_signal_settings(monkeypatch, tmp_path)

    response = client.post("/signals/telegram/test")

    assert response.status_code == 403
    assert response.json()["detail"]["reason"] == "invalid_execution_api_token"


def test_evaluate_latest_requires_execution_token(monkeypatch, tmp_path):
    _patch_signal_settings(monkeypatch, tmp_path)

    response = client.post("/signals/evaluate-latest", json={"notify": False})

    assert response.status_code == 403
    assert response.json()["detail"]["reason"] == "invalid_execution_api_token"


def test_evaluate_latest_writes_decision(monkeypatch, tmp_path):
    _patch_signal_settings(monkeypatch, tmp_path)
    monkeypatch.setattr(
        signal_routes,
        "load_latest_candidates",
        lambda max_candidates=20: ({"job_id": "job-1", "job_type": "causal_scan"}, pd.DataFrame([_candidate()])),
    )
    monkeypatch.setattr(signal_routes, "execution_config_from_settings", lambda: _execution_config())
    monkeypatch.setattr(signal_routes, "current_open_positions_count", lambda config: 0)
    monkeypatch.setattr(signal_routes, "count_daily_test_orders", lambda path, date: 0)

    response = client.post("/signals/evaluate-latest", headers=_headers(), json={"notify": False})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "evaluated"
    assert body["count"] == 1
    assert body["decisions"][0]["status"] == "qualified"
    journal = read_decision_journal(tmp_path / "signal_decisions.csv")
    assert len(journal) == 1
    assert journal.loc[0, "symbol"] == "ENAUSDT"
    assert journal.loc[0, "status"] == "qualified"
    assert journal.loc[0, "telegram_status"] == "disabled"


def test_evaluate_latest_journals_bybit_position_error(monkeypatch, tmp_path):
    _patch_signal_settings(monkeypatch, tmp_path)
    monkeypatch.setattr(
        signal_routes,
        "load_latest_candidates",
        lambda max_candidates=20: ({"job_id": "job-1", "job_type": "causal_scan"}, pd.DataFrame([_candidate()])),
    )
    monkeypatch.setattr(signal_routes, "execution_config_from_settings", lambda: _execution_config())
    monkeypatch.setattr(signal_routes, "count_daily_test_orders", lambda path, date: 0)

    def fail_positions(config):
        raise BybitDemoAPIError(
            ret_code=10001,
            ret_msg="bad",
            method="GET",
            path="/v5/position/list",
            response={},
        )

    monkeypatch.setattr(signal_routes, "current_open_positions_count", fail_positions)

    response = client.post("/signals/evaluate-latest", headers=_headers(), json={"notify": False})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "evaluated"
    assert body["decisions"][0]["status"] == "error"
    assert body["decisions"][0]["reason"] == "bybit_api_error"
    journal = read_decision_journal(tmp_path / "signal_decisions.csv")
    assert journal.loc[0, "status"] == "error"
    assert journal.loc[0, "reason"] == "bybit_api_error"
    assert journal.loc[0, "execution_status"] == "error"


def test_decisions_returns_journal_rows(monkeypatch, tmp_path):
    _patch_signal_settings(monkeypatch, tmp_path)
    append_decision_event(
        tmp_path / "signal_decisions.csv",
        {
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "decision_id": "decision-1",
            "symbol": "ENAUSDT",
            "status": "qualified",
            "reason": "qualified",
        },
    )

    response = client.get("/signals/decisions?limit=10")

    assert response.status_code == 200
    body = response.json()
    assert body["limit"] == 10
    assert body["count"] == 1
    assert body["rows"][0]["decision_id"] == "decision-1"
    assert body["rows"][0]["symbol"] == "ENAUSDT"


def test_demo_auto_entry_rejects_when_disabled(monkeypatch, tmp_path):
    _patch_signal_settings(monkeypatch, tmp_path, signal_auto_entry_enabled=False)

    response = client.post("/signals/demo-auto-entry", headers=_headers(), json={"notify": False})

    assert response.status_code == 400
    assert response.json()["detail"]["reason"] == "auto_entry_disabled"


def test_demo_auto_entry_dry_run_writes_decision_without_order(monkeypatch, tmp_path):
    _patch_signal_settings(monkeypatch, tmp_path, signal_auto_entry_enabled=False)
    monkeypatch.setattr(
        signal_routes,
        "load_latest_candidates",
        lambda max_candidates=20: ({"job_id": "job-1", "job_type": "causal_scan"}, pd.DataFrame([_candidate()])),
    )
    monkeypatch.setattr(signal_routes, "execution_config_from_settings", lambda: _execution_config())
    monkeypatch.setattr(signal_routes, "count_daily_test_orders", lambda path, date: 0)

    def fail_positions(config):
        raise AssertionError("dry_run should not read Bybit positions")

    def fail_submit(*args, **kwargs):
        raise AssertionError("submit_demo_short_order should not be called")

    monkeypatch.setattr(signal_routes, "current_open_positions_count", fail_positions)
    monkeypatch.setattr(signal_routes, "submit_demo_short_order", fail_submit)

    response = client.post(
        "/signals/demo-auto-entry",
        headers=_headers(),
        json={"dry_run": True, "notify": False},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "evaluated"
    assert body["decisions"][0]["status"] == "skipped"
    assert body["decisions"][0]["reason"] == "dry_run"
    journal = read_decision_journal(tmp_path / "signal_decisions.csv")
    assert list(journal["status"]) == ["skipped"]
    assert list(journal["reason"]) == ["dry_run"]


def test_demo_auto_entry_journals_transport_preflight_error_without_order(monkeypatch, tmp_path):
    _patch_signal_settings(monkeypatch, tmp_path, signal_auto_entry_enabled=True)
    monkeypatch.setattr(
        signal_routes,
        "load_latest_candidates",
        lambda max_candidates=20: ({"job_id": "job-1", "job_type": "causal_scan"}, pd.DataFrame([_candidate()])),
    )
    monkeypatch.setattr(signal_routes, "execution_config_from_settings", lambda: _execution_config())
    monkeypatch.setattr(signal_routes, "count_daily_test_orders", lambda path, date: 0)

    def fail_positions(config):
        raise requests.RequestException("network secret")

    def fail_submit(*args, **kwargs):
        raise AssertionError("submit_demo_short_order should not be called")

    monkeypatch.setattr(signal_routes, "current_open_positions_count", fail_positions)
    monkeypatch.setattr(signal_routes, "submit_demo_short_order", fail_submit)

    response = client.post("/signals/demo-auto-entry", headers=_headers(), json={"notify": False})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "evaluated"
    assert body["decisions"][0]["status"] == "error"
    assert body["decisions"][0]["reason"] == "bybit_transport_error"
    journal = read_decision_journal(tmp_path / "signal_decisions.csv")
    assert journal.loc[0, "status"] == "error"
    assert journal.loc[0, "reason"] == "bybit_transport_error"


def test_demo_auto_entry_sends_at_most_one_order(monkeypatch, tmp_path):
    _patch_signal_settings(monkeypatch, tmp_path, signal_auto_entry_enabled=True)
    candidates = pd.DataFrame([_candidate("ENAUSDT"), _candidate("JTOUSDT")])
    monkeypatch.setattr(
        signal_routes,
        "load_latest_candidates",
        lambda max_candidates=20: ({"job_id": "job-1", "job_type": "causal_scan"}, candidates),
    )
    monkeypatch.setattr(signal_routes, "execution_config_from_settings", lambda: _execution_config())
    monkeypatch.setattr(signal_routes, "current_open_positions_count", lambda config: 0)
    monkeypatch.setattr(signal_routes, "count_daily_test_orders", lambda path, date: 0)
    calls = []

    def fake_submit(req, *, config, event):
        calls.append({"req": req, "config": config, "event": event})
        return {"status": "sent", "order_link_id": event["order_link_id"]}

    monkeypatch.setattr(signal_routes, "submit_demo_short_order", fake_submit)

    response = client.post(
        "/signals/demo-auto-entry",
        headers=_headers(),
        json={"notify": False},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "entered"
    assert len(calls) == 1
    statuses = [decision["status"] for decision in body["decisions"]]
    reasons = [decision["reason"] for decision in body["decisions"]]
    assert statuses == ["entered", "skipped"]
    assert reasons == ["order_sent", "already_entered_this_run"]
    journal = read_decision_journal(tmp_path / "signal_decisions.csv")
    assert list(journal["status"]) == ["entered", "skipped"]
    assert list(journal["reason"]) == ["order_sent", "already_entered_this_run"]


def test_evaluate_latest_does_not_create_entry_cooldown(monkeypatch, tmp_path):
    _patch_signal_settings(monkeypatch, tmp_path, signal_auto_entry_enabled=True)
    monkeypatch.setattr(
        signal_routes,
        "load_latest_candidates",
        lambda max_candidates=20: ({"job_id": "job-1", "job_type": "causal_scan"}, pd.DataFrame([_candidate()])),
    )
    monkeypatch.setattr(signal_routes, "execution_config_from_settings", lambda: _execution_config())
    monkeypatch.setattr(signal_routes, "current_open_positions_count", lambda config: 0)
    monkeypatch.setattr(signal_routes, "count_daily_test_orders", lambda path, date: 0)
    calls = []

    def fake_submit(req, *, config, event):
        calls.append({"req": req, "config": config, "event": event})
        return {"status": "sent", "order_link_id": event["order_link_id"]}

    monkeypatch.setattr(signal_routes, "submit_demo_short_order", fake_submit)

    evaluated = client.post("/signals/evaluate-latest", headers=_headers(), json={"notify": False})
    entered = client.post("/signals/demo-auto-entry", headers=_headers(), json={"notify": False})

    assert evaluated.status_code == 200
    assert evaluated.json()["decisions"][0]["status"] == "qualified"
    assert entered.status_code == 200
    body = entered.json()
    assert body["status"] == "entered"
    assert body["decisions"][0]["status"] == "entered"
    assert body["decisions"][0]["reason"] != "cooldown_active"
    assert len(calls) == 1
