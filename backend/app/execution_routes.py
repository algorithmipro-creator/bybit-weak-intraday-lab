from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from bybit_weak_intraday.execution.bybit_demo import BybitDemoAPIError, BybitDemoClient
from bybit_weak_intraday.execution.journal import append_journal_event, count_daily_test_orders, read_journal
from bybit_weak_intraday.execution.orders import (
    calculate_short_tpsl,
    parse_linear_instrument_rules,
    quantity_from_notional,
)
from bybit_weak_intraday.execution.safety import (
    ExecutionConfig,
    parse_symbol_whitelist,
    validate_position_limit,
    validate_static_demo_order_request,
)

from .settings import settings

router = APIRouter(prefix="/execution/demo", tags=["execution-demo"])


class TestShortRequest(BaseModel):
    symbol: str = Field(..., min_length=3, max_length=30)
    notional_usdt: float = Field(..., gt=0)
    take_profit_pct: float = Field(..., gt=0, le=1)
    stop_loss_pct: float = Field(..., gt=0, le=1)


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
    }


@router.get("/wallet")
def demo_wallet() -> dict:
    config = execution_config_from_settings()
    if not config.api_key or not config.api_secret:
        raise HTTPException(status_code=400, detail={"reason": "missing_demo_api_keys"})
    return demo_client_from_config(config).wallet_balance()


@router.get("/positions")
def demo_positions(symbol: str | None = None) -> dict:
    config = execution_config_from_settings()
    if not config.api_key or not config.api_secret:
        raise HTTPException(status_code=400, detail={"reason": "missing_demo_api_keys"})
    return demo_client_from_config(config).positions(symbol=symbol)


@router.get("/open-orders")
def demo_open_orders(symbol: str | None = None) -> dict:
    config = execution_config_from_settings()
    if not config.api_key or not config.api_secret:
        raise HTTPException(status_code=400, detail={"reason": "missing_demo_api_keys"})
    return demo_client_from_config(config).open_orders(symbol=symbol)


@router.post("/place-test-short")
def place_test_short(req: TestShortRequest) -> dict:
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
            detail={
                "status": "error",
                "reason": "bybit_api_error",
                "bybit_ret_code": exc.ret_code,
                "bybit_ret_msg": exc.ret_msg,
            },
        ) from exc
    except ValueError as exc:
        reason = str(exc)
        _append_event(event, status="error", reason=reason)
        raise HTTPException(status_code=400, detail={"status": "error", "reason": reason}) from exc

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
