from __future__ import annotations

import json

import pytest

from bybit_weak_intraday.execution.bybit_demo import BybitDemoAPIError, BybitDemoClient, sign_v5_payload
from bybit_weak_intraday.execution.safety import DEMO_BASE_URL


class FakeResponse:
    def __init__(self, payload: dict):
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self.payload


class FakeSession:
    def __init__(self, payload: dict | None = None):
        self.calls: list[dict] = []
        self.payload = payload or {"retCode": 0, "retMsg": "OK", "result": {"list": []}}

    def request(self, method, url, *, params=None, json=None, data=None, headers=None, timeout=None):
        self.calls.append(
            {
                "method": method,
                "url": url,
                "params": params,
                "json": json,
                "data": data,
                "headers": headers,
                "timeout": timeout,
            }
        )
        return FakeResponse(self.payload)


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
    assert call["headers"]["X-BAPI-SIGN"] == sign_v5_payload(
        api_secret="secret",
        timestamp_ms="1700000000000",
        api_key="key",
        recv_window="5000",
        payload="accountType=UNIFIED&coin=USDT",
    )


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
    assert call["json"] is None
    assert call["data"] == (
        '{"category":"linear","symbol":"ENAUSDT","side":"Sell","orderType":"Market","qty":"13",'
        '"timeInForce":"IOC","positionIdx":0,"reduceOnly":false,"takeProfit":"0.94",'
        '"stopLoss":"1.07","orderLinkId":"bwi-demo-1"}'
    )
    assert call["headers"]["X-BAPI-SIGN"] == sign_v5_payload(
        api_secret="secret",
        timestamp_ms="1700000000000",
        api_key="key",
        recv_window="5000",
        payload=call["data"],
    )
    body = json.loads(call["data"])
    assert body["category"] == "linear"
    assert body["side"] == "Sell"
    assert body["orderType"] == "Market"
    assert body["qty"] == "13"
    assert body["takeProfit"] == "0.94"
    assert body["stopLoss"] == "1.07"


def test_positions_defaults_to_usdt_settle_coin_without_symbol() -> None:
    session = FakeSession()
    client = BybitDemoClient(api_key="key", api_secret="secret", session=session, timestamp_ms=lambda: "1700000000000")

    client.positions()

    assert session.calls[0]["params"] == {"category": "linear", "settleCoin": "USDT"}


def test_open_orders_defaults_to_usdt_settle_coin_without_symbol() -> None:
    session = FakeSession()
    client = BybitDemoClient(api_key="key", api_secret="secret", session=session, timestamp_ms=lambda: "1700000000000")

    client.open_orders()

    assert session.calls[0]["params"] == {"category": "linear", "openOnly": 0, "settleCoin": "USDT"}


def test_nonzero_ret_code_raises_without_secrets() -> None:
    session = FakeSession({"retCode": 10004, "retMsg": "Error sign", "result": {}})
    client = BybitDemoClient(
        api_key="key",
        api_secret="secret",
        session=session,
        timestamp_ms=lambda: "1700000000000",
    )

    with pytest.raises(BybitDemoAPIError) as exc_info:
        client.wallet_balance()

    error = exc_info.value
    message = str(error)
    assert error.ret_code == 10004
    assert error.ret_msg == "Error sign"
    assert "10004" in message
    assert "Error sign" in message
    assert "key" not in message
    assert "secret" not in message
    assert "X-BAPI-SIGN" not in message


def test_open_orders_signature_includes_integer_query_param() -> None:
    session = FakeSession()
    client = BybitDemoClient(api_key="key", api_secret="secret", session=session, timestamp_ms=lambda: "1700000000000")

    client.open_orders()

    call = session.calls[0]
    assert call["params"] == {"category": "linear", "openOnly": 0, "settleCoin": "USDT"}
    assert call["headers"]["X-BAPI-SIGN"] == sign_v5_payload(
        api_secret="secret",
        timestamp_ms="1700000000000",
        api_key="key",
        recv_window="5000",
        payload="category=linear&openOnly=0&settleCoin=USDT",
    )
