from __future__ import annotations

import json

from bybit_weak_intraday.execution.bybit_demo import BybitDemoClient, sign_v5_payload
from bybit_weak_intraday.execution.safety import DEMO_BASE_URL


class FakeResponse:
    def __init__(self, payload: dict):
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self.payload


class FakeSession:
    def __init__(self):
        self.calls: list[dict] = []

    def request(self, method, url, *, params=None, json=None, headers=None, timeout=None):
        self.calls.append(
            {
                "method": method,
                "url": url,
                "params": params,
                "json": json,
                "headers": headers,
                "timeout": timeout,
            }
        )
        return FakeResponse({"retCode": 0, "retMsg": "OK", "result": {"list": []}})


def test_sign_v5_payload_is_stable_for_known_input() -> None:
    signature = sign_v5_payload(
        api_secret="secret",
        timestamp_ms="1700000000000",
        api_key="key",
        recv_window="5000",
        payload='{"category":"linear","symbol":"ENAUSDT"}',
    )

    assert signature == "cfb791c426ed91fc50bf2b87a369064f48f388e7a43aae49aff43942ce900baa"


def test_wallet_balance_uses_demo_base_url_and_auth_headers() -> None:
    session = FakeSession()
    client = BybitDemoClient(api_key="key", api_secret="secret", session=session, timestamp_ms=lambda: "1700000000000")

    client.wallet_balance()

    call = session.calls[0]
    assert call["method"] == "GET"
    assert call["url"] == f"{DEMO_BASE_URL}/v5/account/wallet-balance"
    assert call["params"] == {"accountType": "UNIFIED", "coin": "USDT"}
    assert call["headers"]["X-BAPI-API-KEY"] == "key"
    assert call["headers"]["X-BAPI-TIMESTAMP"] == "1700000000000"
    assert "X-BAPI-SIGN" in call["headers"]


def test_place_short_market_order_posts_expected_body() -> None:
    session = FakeSession()
    client = BybitDemoClient(api_key="key", api_secret="secret", session=session, timestamp_ms=lambda: "1700000000000")

    client.place_short_market_order(
        symbol="ENAUSDT",
        qty="13",
        take_profit="0.94",
        stop_loss="1.07",
        order_link_id="bwi-demo-1",
    )

    call = session.calls[0]
    assert call["method"] == "POST"
    assert call["url"] == f"{DEMO_BASE_URL}/v5/order/create"
    assert call["json"]["category"] == "linear"
    assert call["json"]["side"] == "Sell"
    assert call["json"]["orderType"] == "Market"
    assert call["json"]["qty"] == "13"
    assert call["json"]["takeProfit"] == "0.94"
    assert call["json"]["stopLoss"] == "1.07"
    json.dumps(call["json"], separators=(",", ":"))
