from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import requests
from fastapi.testclient import TestClient

from backend.app import execution_routes
from backend.app import main
from bybit_weak_intraday.execution.bybit_demo import BybitDemoAPIError
from bybit_weak_intraday.execution.journal import append_journal_event, count_daily_test_orders, read_journal
from bybit_weak_intraday.execution.safety import DEMO_BASE_URL, ExecutionConfig

client = TestClient(main.app)
EXECUTION_TOKEN = "test-execution-token"


def _auth_headers(token: str = EXECUTION_TOKEN) -> dict[str, str]:
    return {"X-BWI-Execution-Token": token}


class FakeClient:
    def __init__(self):
        self.place_calls: list[dict] = []

    def instruments_info(self, symbol):
        return {
            "retCode": 0,
            "result": {
                "list": [
                    {
                        "symbol": symbol,
                        "lotSizeFilter": {"qtyStep": "1", "minOrderQty": "1"},
                        "priceFilter": {"tickSize": "0.0001"},
                    }
                ]
            },
        }

    def ticker(self, symbol):
        return {"retCode": 0, "result": {"list": [{"symbol": symbol, "lastPrice": "1.0000"}]}}

    def wallet_balance(self):
        return {"retCode": 0, "result": {"list": [{"accountType": "UNIFIED"}]}}

    def positions(self, symbol=None):
        return {"retCode": 0, "result": {"list": []}}

    def open_orders(self, symbol=None):
        return {"retCode": 0, "result": {"list": []}}

    def place_short_market_order(self, **kwargs):
        self.place_calls.append(kwargs)
        return {"retCode": 0, "retMsg": "OK", "result": {"orderId": "demo-order-1", **kwargs}}


def _patch_execution(
    monkeypatch,
    tmp_path: Path,
    *,
    enabled: bool = True,
    whitelist=("ENAUSDT",),
    fake_client=None,
    execution_mode: str = "demo",
    base_url: str = DEMO_BASE_URL,
    max_daily_test_orders: int = 3,
    execution_api_token: str = EXECUTION_TOKEN,
):
    config = ExecutionConfig(
        execution_mode=execution_mode,
        execution_enabled=enabled,
        api_key="key",
        api_secret="secret",
        base_url=base_url,
        symbol_whitelist=tuple(whitelist),
        max_demo_notional_usdt=25,
        max_open_positions=1,
        max_daily_test_orders=max_daily_test_orders,
    )
    fake_client = fake_client or FakeClient()
    client_factory_called = {"value": False, "count": 0}

    def client_factory(cfg):
        client_factory_called["value"] = True
        client_factory_called["count"] += 1
        return fake_client

    fake_client.client_factory_called = client_factory_called
    monkeypatch.setattr(execution_routes, "execution_config_from_settings", lambda: config)
    monkeypatch.setattr(execution_routes, "journal_path_from_settings", lambda: tmp_path / "execution_journal.csv")
    monkeypatch.setattr(execution_routes, "demo_client_from_config", client_factory)
    monkeypatch.setattr(execution_routes.settings, "execution_api_token", execution_api_token, raising=False)
    return fake_client


def test_execution_status_works_without_keys(monkeypatch, tmp_path):
    config = ExecutionConfig(
        execution_mode="disabled",
        execution_enabled=False,
        api_key="",
        api_secret="",
        base_url=DEMO_BASE_URL,
        symbol_whitelist=("ENAUSDT",),
    )
    monkeypatch.setattr(execution_routes, "execution_config_from_settings", lambda: config)
    monkeypatch.setattr(execution_routes, "journal_path_from_settings", lambda: tmp_path / "execution_journal.csv")
    monkeypatch.setattr(execution_routes.settings, "execution_api_token", "")

    response = client.get("/execution/demo/status")

    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "disabled"
    assert body["enabled"] is False
    assert body["configured"] is False
    assert body["whitelist"] == ["ENAUSDT"]
    assert "max_demo_notional_usdt" in body["limits"]
    assert "api_key" not in body
    assert "api_secret" not in body
    assert "execution_mode" not in body
    assert "execution_enabled" not in body
    assert body["api_token_configured"] is False


def test_execution_status_reports_token_configured_without_exposing_token(monkeypatch, tmp_path):
    _patch_execution(monkeypatch, tmp_path, execution_api_token=EXECUTION_TOKEN)

    response = client.get("/execution/demo/status")

    assert response.status_code == 200
    body = response.json()
    assert body["api_token_configured"] is True
    assert "execution_api_token" not in body
    assert EXECUTION_TOKEN not in str(body)


def test_journal_rejects_missing_token_before_reading_journal(monkeypatch, tmp_path):
    fake_client = _patch_execution(monkeypatch, tmp_path)

    response = client.get("/execution/demo/journal")

    assert response.status_code == 403
    assert response.json()["detail"]["reason"] == "invalid_execution_api_token"
    assert fake_client.client_factory_called["value"] is False


def test_journal_rejects_invalid_token_before_reading_journal(monkeypatch, tmp_path):
    fake_client = _patch_execution(monkeypatch, tmp_path)

    response = client.get("/execution/demo/journal", headers=_auth_headers("wrong-token"))

    assert response.status_code == 403
    assert response.json()["detail"]["reason"] == "invalid_execution_api_token"
    assert fake_client.client_factory_called["value"] is False


def test_journal_returns_recent_rows_newest_first(monkeypatch, tmp_path):
    _patch_execution(monkeypatch, tmp_path)
    journal_path = tmp_path / "execution_journal.csv"
    append_journal_event(
        journal_path,
        {
            "created_at_utc": "2026-05-21T10:00:00+00:00",
            "event_id": "event-1",
            "order_link_id": "bwi-demo-1",
            "mode": "demo",
            "symbol": "ENAUSDT",
            "side": "Sell",
            "status": "accepted",
            "reason": "order_submission_started",
        },
    )
    append_journal_event(
        journal_path,
        {
            "created_at_utc": "2026-05-21T10:01:00+00:00",
            "event_id": "event-2",
            "order_link_id": "bwi-demo-2",
            "mode": "demo",
            "symbol": "JTOUSDT",
            "side": "Sell",
            "status": "sent",
            "reason": "allowed",
        },
    )
    append_journal_event(
        journal_path,
        {
            "created_at_utc": "2026-05-21T10:02:00+00:00",
            "event_id": "event-3",
            "order_link_id": "bwi-demo-3",
            "mode": "demo",
            "symbol": "ENAUSDT",
            "side": "Sell",
            "status": "rejected",
            "reason": "open_position_limit_reached",
        },
    )

    response = client.get("/execution/demo/journal?limit=2", headers=_auth_headers())

    assert response.status_code == 200
    body = response.json()
    assert body["limit"] == 2
    assert body["count"] == 2
    assert [row["event_id"] for row in body["rows"]] == ["event-3", "event-2"]
    assert body["rows"][0]["reason"] == "open_position_limit_reached"


def test_journal_clamps_limit_and_does_not_expose_secrets(monkeypatch, tmp_path):
    _patch_execution(monkeypatch, tmp_path, execution_api_token=EXECUTION_TOKEN)
    journal_path = tmp_path / "execution_journal.csv"
    append_journal_event(
        journal_path,
        {
            "created_at_utc": "2026-05-21T10:00:00+00:00",
            "event_id": "event-1",
            "order_link_id": "bwi-demo-1",
            "mode": "demo",
            "symbol": "ENAUSDT",
            "side": "Sell",
            "status": "sent",
            "reason": "allowed",
            "bybit_ret_msg": "OK",
        },
    )

    too_large = client.get("/execution/demo/journal?limit=9999", headers=_auth_headers())
    too_small = client.get("/execution/demo/journal?limit=0", headers=_auth_headers())

    assert too_large.status_code == 200
    assert too_large.json()["limit"] == 500
    assert too_large.json()["count"] == 1
    assert too_small.status_code == 200
    assert too_small.json()["limit"] == 1
    assert EXECUTION_TOKEN not in str(too_large.json())
    assert "secret" not in str(too_large.json())


def test_wallet_rejects_when_token_not_configured_before_client_construction(monkeypatch, tmp_path):
    fake_client = _patch_execution(monkeypatch, tmp_path, execution_api_token="")

    response = client.get("/execution/demo/wallet", headers=_auth_headers())

    assert response.status_code == 403
    assert response.json()["detail"]["reason"] == "execution_api_token_not_configured"
    assert fake_client.client_factory_called["value"] is False


def test_place_test_short_rejects_when_token_not_configured_before_client_construction(monkeypatch, tmp_path):
    fake_client = _patch_execution(monkeypatch, tmp_path, execution_api_token="")

    response = client.post(
        "/execution/demo/place-test-short",
        headers=_auth_headers(),
        json={"symbol": "ENAUSDT", "notional_usdt": 10, "take_profit_pct": 0.06, "stop_loss_pct": 0.07},
    )

    assert response.status_code == 403
    assert response.json()["detail"]["reason"] == "execution_api_token_not_configured"
    assert fake_client.client_factory_called["value"] is False


def test_wallet_rejects_invalid_token_before_client_construction(monkeypatch, tmp_path):
    fake_client = _patch_execution(monkeypatch, tmp_path)

    response = client.get("/execution/demo/wallet", headers=_auth_headers("wrong-token"))

    assert response.status_code == 403
    assert response.json()["detail"]["reason"] == "invalid_execution_api_token"
    assert fake_client.client_factory_called["value"] is False


def test_wallet_rejects_missing_token_before_client_construction(monkeypatch, tmp_path):
    fake_client = _patch_execution(monkeypatch, tmp_path)

    response = client.get("/execution/demo/wallet")

    assert response.status_code == 403
    assert response.json()["detail"]["reason"] == "invalid_execution_api_token"
    assert fake_client.client_factory_called["value"] is False


def test_place_test_short_rejects_missing_token_before_client_construction(monkeypatch, tmp_path):
    fake_client = _patch_execution(monkeypatch, tmp_path)

    response = client.post(
        "/execution/demo/place-test-short",
        json={"symbol": "ENAUSDT", "notional_usdt": 10, "take_profit_pct": 0.06, "stop_loss_pct": 0.07},
    )

    assert response.status_code == 403
    assert response.json()["detail"]["reason"] == "invalid_execution_api_token"
    assert fake_client.client_factory_called["value"] is False


def test_place_test_short_rejects_invalid_token_before_client_construction(monkeypatch, tmp_path):
    fake_client = _patch_execution(monkeypatch, tmp_path)

    response = client.post(
        "/execution/demo/place-test-short",
        headers=_auth_headers("wrong-token"),
        json={"symbol": "ENAUSDT", "notional_usdt": 10, "take_profit_pct": 0.06, "stop_loss_pct": 0.07},
    )

    assert response.status_code == 403
    assert response.json()["detail"]["reason"] == "invalid_execution_api_token"
    assert fake_client.client_factory_called["value"] is False


def test_place_test_short_rejects_when_disabled(monkeypatch, tmp_path):
    fake_client = _patch_execution(monkeypatch, tmp_path, enabled=False)

    response = client.post(
        "/execution/demo/place-test-short",
        headers=_auth_headers(),
        json={"symbol": "ENAUSDT", "notional_usdt": 10, "take_profit_pct": 0.06, "stop_loss_pct": 0.07},
    )

    assert response.status_code == 400
    assert response.json()["detail"]["reason"] == "execution_disabled"
    assert fake_client.client_factory_called["value"] is False
    assert fake_client.place_calls == []
    journal = read_journal(tmp_path / "execution_journal.csv")
    assert journal.loc[0, "status"] == "rejected"
    assert journal.loc[0, "reason"] == "execution_disabled"


def test_place_test_short_rejects_unknown_symbol(monkeypatch, tmp_path):
    fake_client = _patch_execution(monkeypatch, tmp_path, whitelist=("JTOUSDT",))

    response = client.post(
        "/execution/demo/place-test-short",
        headers=_auth_headers(),
        json={"symbol": "ENAUSDT", "notional_usdt": 10, "take_profit_pct": 0.06, "stop_loss_pct": 0.07},
    )

    assert response.status_code == 400
    assert response.json()["detail"]["reason"] == "symbol_not_whitelisted"
    assert fake_client.place_calls == []


def test_place_test_short_rejects_take_profit_pct_one_before_client_construction(monkeypatch, tmp_path):
    fake_client = _patch_execution(monkeypatch, tmp_path)

    response = client.post(
        "/execution/demo/place-test-short",
        headers=_auth_headers(),
        json={"symbol": "ENAUSDT", "notional_usdt": 10, "take_profit_pct": 1, "stop_loss_pct": 0.07},
    )

    assert response.status_code == 400
    assert response.json()["detail"]["reason"] == "invalid_take_profit_or_stop_loss_pct"
    assert fake_client.client_factory_called["value"] is False
    assert fake_client.place_calls == []
    journal = read_journal(tmp_path / "execution_journal.csv")
    assert journal.loc[0, "status"] == "rejected"
    assert journal.loc[0, "reason"] == "invalid_take_profit_or_stop_loss_pct"


def test_place_test_short_rejects_take_profit_pct_above_one_with_journal(monkeypatch, tmp_path):
    fake_client = _patch_execution(monkeypatch, tmp_path)

    response = client.post(
        "/execution/demo/place-test-short",
        headers=_auth_headers(),
        json={"symbol": "ENAUSDT", "notional_usdt": 10, "take_profit_pct": 1.2, "stop_loss_pct": 0.07},
    )

    assert response.status_code == 400
    assert response.json()["detail"]["reason"] == "invalid_take_profit_or_stop_loss_pct"
    assert fake_client.client_factory_called["value"] is False
    assert fake_client.place_calls == []
    journal = read_journal(tmp_path / "execution_journal.csv")
    assert journal.loc[0, "status"] == "rejected"
    assert journal.loc[0, "reason"] == "invalid_take_profit_or_stop_loss_pct"


def test_place_test_short_rejects_take_profit_pct_zero_with_journal(monkeypatch, tmp_path):
    fake_client = _patch_execution(monkeypatch, tmp_path)

    response = client.post(
        "/execution/demo/place-test-short",
        headers=_auth_headers(),
        json={"symbol": "ENAUSDT", "notional_usdt": 10, "take_profit_pct": 0, "stop_loss_pct": 0.07},
    )

    assert response.status_code == 400
    assert response.json()["detail"]["reason"] == "missing_take_profit_or_stop_loss"
    assert fake_client.client_factory_called["value"] is False
    assert fake_client.place_calls == []
    journal = read_journal(tmp_path / "execution_journal.csv")
    assert journal.loc[0, "status"] == "rejected"
    assert journal.loc[0, "reason"] == "missing_take_profit_or_stop_loss"


def test_place_test_short_rejects_stop_loss_pct_one_before_client_construction(monkeypatch, tmp_path):
    fake_client = _patch_execution(monkeypatch, tmp_path)

    response = client.post(
        "/execution/demo/place-test-short",
        headers=_auth_headers(),
        json={"symbol": "ENAUSDT", "notional_usdt": 10, "take_profit_pct": 0.06, "stop_loss_pct": 1},
    )

    assert response.status_code == 400
    assert response.json()["detail"]["reason"] == "invalid_take_profit_or_stop_loss_pct"
    assert fake_client.client_factory_called["value"] is False
    assert fake_client.place_calls == []


def test_place_test_short_rejects_stop_loss_pct_above_one_with_journal(monkeypatch, tmp_path):
    fake_client = _patch_execution(monkeypatch, tmp_path)

    response = client.post(
        "/execution/demo/place-test-short",
        headers=_auth_headers(),
        json={"symbol": "ENAUSDT", "notional_usdt": 10, "take_profit_pct": 0.06, "stop_loss_pct": 1.2},
    )

    assert response.status_code == 400
    assert response.json()["detail"]["reason"] == "invalid_take_profit_or_stop_loss_pct"
    assert fake_client.client_factory_called["value"] is False
    assert fake_client.place_calls == []
    journal = read_journal(tmp_path / "execution_journal.csv")
    assert journal.loc[0, "status"] == "rejected"
    assert journal.loc[0, "reason"] == "invalid_take_profit_or_stop_loss_pct"


def test_wallet_rejects_non_demo_base_url_without_constructing_client(monkeypatch, tmp_path):
    fake_client = _patch_execution(monkeypatch, tmp_path, base_url="https://api.bybit.com")

    response = client.get("/execution/demo/wallet", headers=_auth_headers())

    assert response.status_code == 400
    assert response.json()["detail"]["reason"] == "non_demo_base_url"
    assert fake_client.client_factory_called["value"] is False


def test_wallet_bybit_api_error_returns_sanitized_detail(monkeypatch, tmp_path):
    class ErrorClient(FakeClient):
        def wallet_balance(self):
            raise BybitDemoAPIError(
                ret_code=10004,
                ret_msg="Error sign",
                method="GET",
                path="/v5/account/wallet-balance",
                response={"retCode": 10004, "retMsg": "Error sign"},
            )

    _patch_execution(monkeypatch, tmp_path, fake_client=ErrorClient())

    response = client.get("/execution/demo/wallet", headers=_auth_headers())

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert detail["reason"] == "bybit_api_error"
    assert detail["ret_code"] == 10004
    assert detail["ret_msg"] == "Error sign"
    assert detail["method"] == "GET"
    assert detail["path"] == "/v5/account/wallet-balance"
    assert "key" not in str(detail)
    assert "secret" not in str(detail)


def test_wallet_transport_error_returns_sanitized_detail(monkeypatch, tmp_path):
    class TransportErrorClient(FakeClient):
        def wallet_balance(self):
            raise requests.RequestException("network down with secret should not leak")

    _patch_execution(monkeypatch, tmp_path, fake_client=TransportErrorClient())

    response = client.get("/execution/demo/wallet", headers=_auth_headers())

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert detail["reason"] == "bybit_transport_error"
    assert "secret" not in str(detail)


def test_place_test_short_uses_mock_client_and_writes_journal(monkeypatch, tmp_path):
    fake_client = _patch_execution(monkeypatch, tmp_path)

    response = client.post(
        "/execution/demo/place-test-short",
        headers=_auth_headers(),
        json={"symbol": "ENAUSDT", "notional_usdt": 10, "take_profit_pct": 0.06, "stop_loss_pct": 0.07},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "sent"
    assert body["symbol"] == "ENAUSDT"
    assert body["qty"] == "10"
    assert body["take_profit"] == "0.9400"
    assert body["stop_loss"] == "1.0700"
    assert fake_client.place_calls == [
        {
            "symbol": "ENAUSDT",
            "qty": "10",
            "take_profit": "0.9400",
            "stop_loss": "1.0700",
            "order_link_id": body["order_link_id"],
        }
    ]
    journal = read_journal(tmp_path / "execution_journal.csv")
    last_row = journal.iloc[-1]
    assert last_row["status"] == "sent"
    assert last_row["symbol"] == "ENAUSDT"
    assert str(last_row["qty"]) == "10"
    assert format(Decimal(str(last_row["take_profit"])), ".4f") == "0.9400"
    assert format(Decimal(str(last_row["stop_loss"])), ".4f") == "1.0700"
    assert str(last_row["bybit_ret_code"]) in {"0", "0.0"}


def test_place_test_short_journals_order_preparation_error(monkeypatch, tmp_path):
    class BrokenTickerClient(FakeClient):
        def ticker(self, symbol):
            return {"retCode": 0, "result": {"list": []}}

    _patch_execution(monkeypatch, tmp_path, fake_client=BrokenTickerClient())

    response = client.post(
        "/execution/demo/place-test-short",
        headers=_auth_headers(),
        json={"symbol": "ENAUSDT", "notional_usdt": 10, "take_profit_pct": 0.06, "stop_loss_pct": 0.07},
    )

    assert response.status_code == 400
    assert response.json()["detail"]["reason"] == "order_preparation_error"
    journal = read_journal(tmp_path / "execution_journal.csv")
    last_row = journal.iloc[-1]
    assert last_row["status"] == "error"
    assert last_row["reason"] == "order_preparation_error"


def test_place_test_short_daily_limit_blocks_second_request_before_order_placement(monkeypatch, tmp_path):
    fake_client = _patch_execution(monkeypatch, tmp_path, max_daily_test_orders=1)
    payload = {"symbol": "ENAUSDT", "notional_usdt": 10, "take_profit_pct": 0.06, "stop_loss_pct": 0.07}

    first = client.post("/execution/demo/place-test-short", headers=_auth_headers(), json=payload)
    second = client.post("/execution/demo/place-test-short", headers=_auth_headers(), json=payload)

    assert first.status_code == 200
    assert second.status_code == 400
    assert second.json()["detail"]["reason"] == "daily_test_order_limit_reached"
    assert fake_client.client_factory_called["count"] == 1
    assert len(fake_client.place_calls) == 1
    journal_path = tmp_path / "execution_journal.csv"
    journal = read_journal(journal_path)
    assert list(journal["status"]) == ["accepted", "sent", "rejected"]
    assert list(journal["reason"]) == ["order_submission_started", "allowed", "daily_test_order_limit_reached"]
    assert count_daily_test_orders(journal_path, datetime.now(timezone.utc).date()) == 1


def test_place_test_short_transport_error_consumes_daily_attempt_before_retry(monkeypatch, tmp_path):
    class TimeoutAfterPlaceClient(FakeClient):
        def place_short_market_order(self, **kwargs):
            self.place_calls.append(kwargs)
            raise requests.RequestException("timed out after Bybit may have accepted")

    fake_client = _patch_execution(
        monkeypatch,
        tmp_path,
        fake_client=TimeoutAfterPlaceClient(),
        max_daily_test_orders=1,
    )
    payload = {"symbol": "ENAUSDT", "notional_usdt": 10, "take_profit_pct": 0.06, "stop_loss_pct": 0.07}

    first = client.post("/execution/demo/place-test-short", headers=_auth_headers(), json=payload)
    second = client.post("/execution/demo/place-test-short", headers=_auth_headers(), json=payload)

    assert first.status_code == 502
    assert first.json()["detail"]["reason"] == "bybit_transport_error"
    assert second.status_code == 400
    assert second.json()["detail"]["reason"] == "daily_test_order_limit_reached"
    assert fake_client.client_factory_called["count"] == 1
    assert len(fake_client.place_calls) == 1
    journal_path = tmp_path / "execution_journal.csv"
    journal = read_journal(journal_path)
    assert list(journal["status"]) == ["accepted", "error", "rejected"]
    assert list(journal["reason"]) == [
        "order_submission_started",
        "bybit_transport_error",
        "daily_test_order_limit_reached",
    ]
    assert Decimal(str(journal.loc[0, "qty"])) == Decimal("10")
    assert format(Decimal(str(journal.loc[0, "take_profit"])), ".4f") == "0.9400"
    assert format(Decimal(str(journal.loc[0, "stop_loss"])), ".4f") == "1.0700"
    assert count_daily_test_orders(journal_path, datetime.now(timezone.utc).date()) == 1
