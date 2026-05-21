from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN, ROUND_UP
from typing import Any


@dataclass(frozen=True)
class InstrumentRules:
    symbol: str
    qty_step: Decimal
    min_order_qty: Decimal
    tick_size: Decimal


def _first_result_item(response: dict[str, Any]) -> dict[str, Any]:
    items = ((response.get("result") or {}).get("list") or [])
    if not items:
        raise ValueError("instrument_not_found")
    return items[0]


def parse_linear_instrument_rules(response: dict[str, Any]) -> InstrumentRules:
    item = _first_result_item(response)
    lot = item.get("lotSizeFilter") or {}
    price = item.get("priceFilter") or {}
    return InstrumentRules(
        symbol=str(item["symbol"]).upper(),
        qty_step=Decimal(str(lot["qtyStep"])),
        min_order_qty=Decimal(str(lot["minOrderQty"])),
        tick_size=Decimal(str(price["tickSize"])),
    )


def floor_to_step(value: Decimal, step: Decimal) -> Decimal:
    return (value / step).to_integral_value(rounding=ROUND_DOWN) * step


def ceil_to_step(value: Decimal, step: Decimal) -> Decimal:
    return (value / step).to_integral_value(rounding=ROUND_UP) * step


def quantity_from_notional(notional_usdt: Decimal, reference_price: Decimal, rules: InstrumentRules) -> Decimal:
    if reference_price <= 0:
        raise ValueError("invalid_reference_price")
    qty = floor_to_step(notional_usdt / reference_price, rules.qty_step)
    if qty < rules.min_order_qty:
        raise ValueError("quantity_below_min_order_qty")
    return qty


def calculate_short_tpsl(
    reference_price: Decimal,
    take_profit_pct: Decimal,
    stop_loss_pct: Decimal,
    rules: InstrumentRules,
) -> tuple[Decimal, Decimal]:
    if reference_price <= 0:
        raise ValueError("invalid_reference_price")
    if take_profit_pct <= 0 or stop_loss_pct <= 0:
        raise ValueError("invalid_tpsl_pct")
    take_profit = floor_to_step(reference_price * (Decimal("1") - take_profit_pct), rules.tick_size)
    stop_loss = ceil_to_step(reference_price * (Decimal("1") + stop_loss_pct), rules.tick_size)
    if take_profit >= reference_price:
        raise ValueError("short_take_profit_not_below_reference")
    if stop_loss <= reference_price:
        raise ValueError("short_stop_loss_not_above_reference")
    return take_profit, stop_loss


def _decimal_to_str(value: Decimal) -> str:
    return format(value, "f")


def build_short_market_order_payload(
    *,
    symbol: str,
    qty: Decimal,
    take_profit: Decimal,
    stop_loss: Decimal,
    order_link_id: str,
) -> dict[str, Any]:
    return {
        "category": "linear",
        "symbol": symbol.strip().upper(),
        "side": "Sell",
        "orderType": "Market",
        "qty": _decimal_to_str(qty),
        "timeInForce": "IOC",
        "positionIdx": 0,
        "reduceOnly": False,
        "takeProfit": _decimal_to_str(take_profit),
        "stopLoss": _decimal_to_str(stop_loss),
        "orderLinkId": order_link_id,
    }
