from __future__ import annotations

import secrets
import threading
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from uuid import uuid4

import requests
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from bybit_weak_intraday.execution.bybit_demo import BybitDemoAPIError, BybitDemoClient
from bybit_weak_intraday.execution.journal import append_journal_event, count_daily_test_orders, read_journal
from bybit_weak_intraday.execution.orders import (
    calculate_short_tpsl,
    parse_linear_instrument_rules,
    quantity_from_notional,
)
from bybit_weak_intraday.execution.safety import (
    DEMO_BASE_URL,
    ExecutionConfig,
    parse_symbol_whitelist,
    validate_position_limit,
    validate_static_demo_order_request,
)

from .settings import settings

router = APIRouter(prefix="/execution/demo", tags=["execution-demo"])
_ORDER_LOCK = threading.Lock()


class TestShortRequest(BaseModel):
    symbol: str = Field(..., min_length=3, max_length=30)
    notional_usdt: float = Field(..., gt=0)
    take_profit_pct: float
    stop_loss_pct: float


def execution_config_from_settings() -> ExecutionConfig:
    return ExecutionConfig(
        execution_mode=settings.execution_mode,
        execution_enabled=settings.execution_enabled,
        api_key=settings.bybit_demo_api_key,
        api_secret=settings.bybit_demo_api_secret,
        base_url=settings.bybit_demo_base_url,
        symbol_whitelist=parse_symbol_whitelist(settings.execution_symbol_whitelist),
        max_demo_notional_usdt=float(settings.max_demo_notional_usdt),
        max_open_positions=int(settings.max_open_positions),
        max_daily_test_orders=int(settings.max_daily_test_orders),
    )


def journal_path_from_settings() -> Path:
    return Path(settings.execution_journal_path)


def demo_client_from_config(config: ExecutionConfig) -> BybitDemoClient:
    return BybitDemoClient(api_key=config.api_key, api_secret=config.api_secret, base_url=config.base_url)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _append_event(event: dict, **updates) -> None:
    event.update(updates)
    append_journal_event(journal_path_from_settings(), event)


def _reject(reason: str, *, event: dict, status_code: int = 400) -> None:
    _append_event(event, status="rejected", reason=reason)
    raise HTTPException(status_code=status_code, detail={"status": "rejected", "reason": reason})


def _require_execution_api_token(header_token: str | None) -> None:
    configured_token = settings.execution_api_token.strip()
    if not configured_token:
        raise HTTPException(status_code=403, detail={"reason": "execution_api_token_not_configured"})
    if header_token is None or not secrets.compare_digest(header_token, configured_token):
        raise HTTPException(status_code=403, detail={"reason": "invalid_execution_api_token"})


def _require_demo_read_config(config: ExecutionConfig) -> None:
    if config.execution_mode != "demo":
        raise HTTPException(status_code=400, detail={"reason": "execution_mode_not_demo"})
    if config.base_url != DEMO_BASE_URL:
        raise HTTPException(status_code=400, detail={"reason": "non_demo_base_url"})
    if not config.api_key.strip() or not config.api_secret.strip():
        raise HTTPException(status_code=400, detail={"reason": "missing_demo_api_keys"})


def _bybit_error_detail(exc: BybitDemoAPIError) -> dict:
    return {
        "status": "error",
        "reason": "bybit_api_error",
        "ret_code": exc.ret_code,
        "ret_msg": exc.ret_msg,
        "method": exc.method,
        "path": exc.path,
    }


def _read_only_bybit_error(exc: BybitDemoAPIError) -> HTTPException:
    return HTTPException(status_code=502, detail=_bybit_error_detail(exc))


def _transport_error_detail() -> dict:
    return {"status": "error", "reason": "bybit_transport_error"}


def _result_list(response: dict) -> list[dict]:
    return ((response.get("result") or {}).get("list") or [])


def _open_positions_count(response: dict) -> int:
    count = 0
    for row in _result_list(response):
        size = Decimal(str(row.get("size") or "0"))
        if size != 0:
            count += 1
    return count


def _last_price(response: dict) -> Decimal:
    items = _result_list(response)
    if not items:
        raise ValueError("ticker_not_found")
    return Decimal(str(items[0]["lastPrice"]))


def _decimal_to_str(value: Decimal) -> str:
    return format(value, "f")


@router.get("/status")
def execution_status() -> dict:
    config = execution_config_from_settings()
    journal = read_journal(journal_path_from_settings())
    return {
        "mode": config.execution_mode,
        "enabled": config.execution_enabled,
        "configured": bool(config.api_key and config.api_secret),
        "base_url": config.base_url,
        "whitelist": list(config.symbol_whitelist),
        "limits": {
            "max_demo_notional_usdt": config.max_demo_notional_usdt,
            "max_open_positions": config.max_open_positions,
            "max_daily_test_orders": config.max_daily_test_orders,
        },
        "journal_rows": int(len(journal)),
        "api_token_configured": bool(settings.execution_api_token.strip()),
    }


@router.get("/wallet")
def demo_wallet(x_bwi_execution_token: str | None = Header(default=None, alias="X-BWI-Execution-Token")) -> dict:
    _require_execution_api_token(x_bwi_execution_token)
    config = execution_config_from_settings()
    _require_demo_read_config(config)
    try:
        return demo_client_from_config(config).wallet_balance()
    except BybitDemoAPIError as exc:
        raise _read_only_bybit_error(exc) from exc
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=_transport_error_detail()) from exc


@router.get("/positions")
def demo_positions(
    symbol: str | None = None,
    x_bwi_execution_token: str | None = Header(default=None, alias="X-BWI-Execution-Token"),
) -> dict:
    _require_execution_api_token(x_bwi_execution_token)
    config = execution_config_from_settings()
    _require_demo_read_config(config)
    try:
        return demo_client_from_config(config).positions(symbol=symbol)
    except BybitDemoAPIError as exc:
        raise _read_only_bybit_error(exc) from exc
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=_transport_error_detail()) from exc


@router.get("/open-orders")
def demo_open_orders(
    symbol: str | None = None,
    x_bwi_execution_token: str | None = Header(default=None, alias="X-BWI-Execution-Token"),
) -> dict:
    _require_execution_api_token(x_bwi_execution_token)
    config = execution_config_from_settings()
    _require_demo_read_config(config)
    try:
        return demo_client_from_config(config).open_orders(symbol=symbol)
    except BybitDemoAPIError as exc:
        raise _read_only_bybit_error(exc) from exc
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=_transport_error_detail()) from exc


@router.post("/place-test-short")
def place_test_short(
    req: TestShortRequest,
    x_bwi_execution_token: str | None = Header(default=None, alias="X-BWI-Execution-Token"),
) -> dict:
    _require_execution_api_token(x_bwi_execution_token)
    config = execution_config_from_settings()
    symbol = req.symbol.strip().upper()
    event_id = uuid4().hex
    order_link_id = f"bwi-demo-{event_id[:18]}"
    journal_path = journal_path_from_settings()
    event = {
        "created_at_utc": _utc_now_iso(),
        "event_id": event_id,
        "order_link_id": order_link_id,
        "mode": config.execution_mode,
        "symbol": symbol,
        "side": "Sell",
        "category": "linear",
        "requested_notional_usdt": req.notional_usdt,
    }
    decision = validate_static_demo_order_request(
        config,
        symbol=symbol,
        notional_usdt=float(req.notional_usdt),
        take_profit_pct=float(req.take_profit_pct),
        stop_loss_pct=float(req.stop_loss_pct),
        daily_test_order_count=0,
    )
    if not decision.allowed:
        _reject(decision.reason, event=event)

    with _ORDER_LOCK:
        daily_count = count_daily_test_orders(journal_path, datetime.now(timezone.utc).date())
        decision = validate_static_demo_order_request(
            config,
            symbol=symbol,
            notional_usdt=float(req.notional_usdt),
            take_profit_pct=float(req.take_profit_pct),
            stop_loss_pct=float(req.stop_loss_pct),
            daily_test_order_count=daily_count,
        )
        if not decision.allowed:
            _reject(decision.reason, event=event)

        client = demo_client_from_config(config)
        try:
            positions = client.positions()
            position_decision = validate_position_limit(config, open_positions_count=_open_positions_count(positions))
            if not position_decision.allowed:
                _reject(position_decision.reason, event=event)

            instrument_response = client.instruments_info(symbol)
            ticker_response = client.ticker(symbol)
            rules = parse_linear_instrument_rules(instrument_response)
            reference_price = _last_price(ticker_response)
            qty = quantity_from_notional(Decimal(str(req.notional_usdt)), reference_price, rules)
            take_profit, stop_loss = calculate_short_tpsl(
                reference_price,
                Decimal(str(req.take_profit_pct)),
                Decimal(str(req.stop_loss_pct)),
                rules,
            )
            _append_event(
                event,
                qty=_decimal_to_str(qty),
                take_profit=_decimal_to_str(take_profit),
                stop_loss=_decimal_to_str(stop_loss),
                status="accepted",
                reason="order_submission_started",
            )
            response = client.place_short_market_order(
                symbol=symbol,
                qty=_decimal_to_str(qty),
                take_profit=_decimal_to_str(take_profit),
                stop_loss=_decimal_to_str(stop_loss),
                order_link_id=order_link_id,
            )
        except BybitDemoAPIError as exc:
            _append_event(
                event,
                status="error",
                reason="bybit_api_error",
                bybit_ret_code=exc.ret_code,
                bybit_ret_msg=exc.ret_msg,
            )
            raise HTTPException(
                status_code=502,
                detail=_bybit_error_detail(exc),
            ) from exc
        except (ValueError, KeyError, TypeError, InvalidOperation) as exc:
            _append_event(event, status="error", reason="order_preparation_error", bybit_ret_msg=str(exc))
            raise HTTPException(status_code=400, detail={"status": "error", "reason": "order_preparation_error"}) from exc
        except requests.RequestException as exc:
            _append_event(event, status="error", reason="bybit_transport_error", bybit_ret_msg="request_failed")
            raise HTTPException(status_code=502, detail=_transport_error_detail()) from exc

        _append_event(
            event,
            qty=_decimal_to_str(qty),
            take_profit=_decimal_to_str(take_profit),
            stop_loss=_decimal_to_str(stop_loss),
            status="sent",
            reason="allowed",
            bybit_ret_code=response.get("retCode", ""),
            bybit_ret_msg=response.get("retMsg", ""),
        )
    return {
        "status": "sent",
        "symbol": symbol,
        "qty": _decimal_to_str(qty),
        "take_profit": _decimal_to_str(take_profit),
        "stop_loss": _decimal_to_str(stop_loss),
        "order_link_id": order_link_id,
        "bybit_response": response,
    }
