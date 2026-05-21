from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from backend.app import execution_routes
from backend.app import main
from bybit_weak_intraday.execution.safety import DEMO_BASE_URL, ExecutionConfig

client = TestClient(main.app)


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


def _patch_execution(monkeypatch, tmp_path: Path, *, enabled: bool = True, whitelist=("ENAUSDT",), fake_client=None):
    config = ExecutionConfig(
        execution_mode="demo",
        execution_enabled=enabled,
        api_key="key",
        api_secret="secret",
        base_url=DEMO_BASE_URL,
        symbol_whitelist=tuple(whitelist),
        max_demo_notional_usdt=25,
        max_open_positions=1,
        max_daily_test_orders=3,
    )
    fake_client = fake_client or FakeClient()
    monkeypatch.setattr(execution_routes, "execution_config_from_settings", lambda: config)
    monkeypatch.setattr(execution_routes, "journal_path_from_settings", lambda: tmp_path / "execution_journal.csv")
    monkeypatch.setattr(execution_routes, "demo_client_from_config", lambda cfg: fake_client)
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

    response = client.get("/execution/demo/status")

    assert response.status_code == 200
    body = response.json()
    assert body["execution_mode"] == "disabled"
    assert body["configured"] is False
    assert "api_secret" not in body


def test_place_test_short_rejects_when_disabled(monkeypatch, tmp_path):
    fake_client = _patch_execution(monkeypatch, tmp_path, enabled=False)

    response = client.post(
        "/execution/demo/place-test-short",
        json={"symbol": "ENAUSDT", "notional_usdt": 10, "take_profit_pct": 0.06, "stop_loss_pct": 0.07},
    )

    assert response.status_code == 400
    assert response.json()["detail"]["reason"] == "execution_disabled"
    assert fake_client.place_calls == []
    assert (tmp_path / "execution_journal.csv").exists()


def test_place_test_short_rejects_unknown_symbol(monkeypatch, tmp_path):
    fake_client = _patch_execution(monkeypatch, tmp_path, whitelist=("JTOUSDT",))

    response = client.post(
        "/execution/demo/place-test-short",
        json={"symbol": "ENAUSDT", "notional_usdt": 10, "take_profit_pct": 0.06, "stop_loss_pct": 0.07},
    )

    assert response.status_code == 400
    assert response.json()["detail"]["reason"] == "symbol_not_whitelisted"
    assert fake_client.place_calls == []


def test_place_test_short_uses_mock_client_and_writes_journal(monkeypatch, tmp_path):
    fake_client = _patch_execution(monkeypatch, tmp_path)

    response = client.post(
        "/execution/demo/place-test-short",
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
    assert (tmp_path / "execution_journal.csv").exists()
