from __future__ import annotations

import hashlib
import hmac
import json
import time
from decimal import Decimal
from typing import Any, Callable
from urllib.parse import urlencode

import requests

from bybit_weak_intraday.execution.orders import build_short_market_order_payload
from bybit_weak_intraday.execution.safety import DEMO_BASE_URL


def sign_v5_payload(*, api_secret: str, timestamp_ms: str, api_key: str, recv_window: str, payload: str) -> str:
    raw = f"{timestamp_ms}{api_key}{recv_window}{payload}"
    return hmac.new(api_secret.encode("utf-8"), raw.encode("utf-8"), hashlib.sha256).hexdigest()


def _compact_json(body: dict[str, Any]) -> str:
    return json.dumps(body, separators=(",", ":"), ensure_ascii=False)


class BybitDemoClient:
    def __init__(
        self,
        *,
        api_key: str,
        api_secret: str,
        base_url: str = DEMO_BASE_URL,
        recv_window: str = "5000",
        session: requests.Session | None = None,
        timeout: int = 30,
        timestamp_ms: Callable[[], str] | None = None,
    ) -> None:
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = base_url.rstrip("/")
        self.recv_window = recv_window
        self.session = session or requests.Session()
        self.timeout = timeout
        self.timestamp_ms = timestamp_ms or (lambda: str(int(time.time() * 1000)))

    def _headers(self, payload: str) -> dict[str, str]:
        timestamp = self.timestamp_ms()
        return {
            "X-BAPI-API-KEY": self.api_key,
            "X-BAPI-TIMESTAMP": timestamp,
            "X-BAPI-RECV-WINDOW": self.recv_window,
            "X-BAPI-SIGN": sign_v5_payload(
                api_secret=self.api_secret,
                timestamp_ms=timestamp,
                api_key=self.api_key,
                recv_window=self.recv_window,
                payload=payload,
            ),
            "Content-Type": "application/json",
        }

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        method = method.upper()
        params = params or {}
        if method == "GET":
            payload = urlencode(params)
            request_body = None
            request_data = None
        else:
            request_body = body or {}
            payload = _compact_json(request_body)
            request_data = payload
        response = self.session.request(
            method,
            f"{self.base_url}{path}",
            params=params if method == "GET" else None,
            json=None,
            data=request_data,
            headers=self._headers(payload),
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def instruments_info(self, symbol: str) -> dict[str, Any]:
        return self._request("GET", "/v5/market/instruments-info", params={"category": "linear", "symbol": symbol.upper()})

    def ticker(self, symbol: str) -> dict[str, Any]:
        return self._request("GET", "/v5/market/tickers", params={"category": "linear", "symbol": symbol.upper()})

    def wallet_balance(self, coin: str = "USDT") -> dict[str, Any]:
        return self._request("GET", "/v5/account/wallet-balance", params={"accountType": "UNIFIED", "coin": coin.upper()})

    def positions(self, symbol: str | None = None) -> dict[str, Any]:
        params = {"category": "linear"}
        if symbol:
            params["symbol"] = symbol.upper()
        else:
            params["settleCoin"] = "USDT"
        return self._request("GET", "/v5/position/list", params=params)

    def open_orders(self, symbol: str | None = None) -> dict[str, Any]:
        params = {"category": "linear", "openOnly": 0}
        if symbol:
            params["symbol"] = symbol.upper()
        else:
            params["settleCoin"] = "USDT"
        return self._request("GET", "/v5/order/realtime", params=params)

    def place_short_market_order(
        self,
        *,
        symbol: str,
        qty: str,
        take_profit: str,
        stop_loss: str,
        order_link_id: str,
    ) -> dict[str, Any]:
        body = build_short_market_order_payload(
            symbol=symbol,
            qty=Decimal(qty),
            take_profit=Decimal(take_profit),
            stop_loss=Decimal(stop_loss),
            order_link_id=order_link_id,
        )
        return self._request("POST", "/v5/order/create", body=body)
