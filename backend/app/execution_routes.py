from __future__ import annotations

import secrets
import threading
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from uuid import uuid4

import requests
from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

from bybit_weak_intraday.execution.bybit_demo import BybitDemoAPIError, BybitDemoClient
from bybit_weak_intraday.execution.journal import (
    append_journal_event,
    count_daily_test_orders,
    read_journal,
    read_journal_tail,
)
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


def demo_short_event_from_request(req: TestShortRequest, *, config: ExecutionConfig, event_id: str | None = None) -> dict:
    resolved_event_id = event_id or uuid4().hex
    symbol = req.symbol.strip().upper()
    return {
        "created_at_utc": _utc_now_iso(),
        "event_id": resolved_event_id,
        "order_link_id": f"bwi-demo-{resolved_event_id[:18]}",
        "mode": config.execution_mode,
        "symbol": symbol,
        "side": "Sell",
        "category": "linear",
        "requested_notional_usdt": req.notional_usdt,
    }


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


def _redact_journal_rows(rows: list[dict], secrets_to_redact: set[str]) -> list[dict]:
    if not secrets_to_redact:
        return rows
    redacted_rows = []
    for row in rows:
        redacted_row = {}
        for key, value in row.items():
            if isinstance(value, str):
                redacted_value = value
                for secret in secrets_to_redact:
                    redacted_value = redacted_value.replace(secret, "[redacted]")
                redacted_row[key] = redacted_value
            else:
                redacted_row[key] = value
        redacted_rows.append(redacted_row)
    return redacted_rows


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


@router.get("/journal")
def demo_journal(
    limit: int = Query(default=50),
    x_bwi_execution_token: str | None = Header(default=None, alias="X-BWI-Execution-Token"),
) -> dict:
    _require_execution_api_token(x_bwi_execution_token)
    config = execution_config_from_settings()
    _require_demo_read_config(config)
    clamped_limit = max(1, min(int(limit), 500))
    journal = read_journal_tail(journal_path_from_settings(), clamped_limit)
    rows = [] if journal.empty else journal.fillna("").to_dict(orient="records")
    secrets_to_redact = {
        secret
        for secret in (config.api_key.strip(), config.api_secret.strip(), settings.execution_api_token.strip())
        if secret
    }
    rows = _redact_journal_rows(rows, secrets_to_redact)
    return {"rows": rows, "limit": clamped_limit, "count": len(rows)}


def submit_demo_short_order(req: TestShortRequest, *, config: ExecutionConfig, event: dict) -> dict:
    symbol = req.symbol.strip().upper()
    order_link_id = event["order_link_id"]
    journal_path = journal_path_from_settings()
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


@router.post("/place-test-short")
def place_test_short(
    req: TestShortRequest,
    x_bwi_execution_token: str | None = Header(default=None, alias="X-BWI-Execution-Token"),
) -> dict:
    _require_execution_api_token(x_bwi_execution_token)
    config = execution_config_from_settings()
    event = demo_short_event_from_request(req, config=config)
    return submit_demo_short_order(req, config=config, event=event)
