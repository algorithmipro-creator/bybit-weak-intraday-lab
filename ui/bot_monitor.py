from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

from bybit_weak_intraday.signals.candidates import build_scanner_watchlist, select_latest_scanner_job

WALLET_SUMMARY_FIELDS = {
    "equity": "totalEquity",
    "wallet_balance": "totalWalletBalance",
    "available_balance": "totalAvailableBalance",
    "margin_used": "totalInitialMargin",
    "unrealized_pnl": "totalPerpUPL",
}

def safe_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, str) and value == "":
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def result_rows(payload: dict | None) -> list[dict]:
    if not isinstance(payload, dict):
        return []
    result = payload.get("result")
    if not isinstance(result, dict):
        return []
    rows = result.get("list")
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def summarize_wallet(payload: dict | None) -> dict[str, float | None]:
    rows = result_rows(payload)
    account = rows[0] if rows else {}
    return {name: safe_float(account.get(source)) for name, source in WALLET_SUMMARY_FIELDS.items()}


def normalize_positions(payload: dict | None, orders_payload: dict | None = None) -> list[dict]:
    protections = _protections_by_symbol(orders_payload)
    normalized = []
    for row in result_rows(payload):
        position_value = safe_float(row.get("positionValue"))
        unrealized_pnl = safe_float(row.get("unrealisedPnl"))
        pnl_pct = None
        if unrealized_pnl is not None and position_value not in (None, 0):
            pnl_pct = unrealized_pnl / position_value

        symbol = row.get("symbol")
        protection = protections.get(symbol, {})
        normalized.append(
            {
                "symbol": symbol,
                "side": row.get("side"),
                "size": safe_float(row.get("size")),
                "entry_price": safe_float(row.get("avgPrice")),
                "mark_price": safe_float(row.get("markPrice")),
                "unrealized_pnl": unrealized_pnl,
                "pnl_pct": pnl_pct,
                "position_value": position_value,
                "leverage": safe_float(row.get("leverage")),
                "margin": safe_float(row.get("positionIM")),
                "liq_price": safe_float(row.get("liqPrice")),
                "take_profit": protection.get("take_profit"),
                "stop_loss": protection.get("stop_loss"),
            }
        )
    return normalized


def normalize_open_orders(payload: dict | None) -> list[dict]:
    return [
        {
            "symbol": row.get("symbol"),
            "side": row.get("side"),
            "order_type": row.get("orderType"),
            "qty": safe_float(row.get("qty")),
            "price": safe_float(row.get("price")),
            "trigger_price": safe_float(row.get("triggerPrice")),
            "stop_order_type": row.get("stopOrderType"),
            "status": row.get("orderStatus"),
            "created_time": _epoch_millis_to_iso(row.get("createdTime")),
        }
        for row in result_rows(payload)
    ]


def _protections_by_symbol(orders_payload: dict | None) -> dict[str, dict[str, float | None]]:
    protections: dict[str, dict[str, float | None]] = {}
    for row in result_rows(orders_payload):
        symbol = row.get("symbol")
        if not symbol:
            continue
        stop_type = str(row.get("stopOrderType") or "").lower()
        if stop_type == "takeprofit":
            protections.setdefault(symbol, {})["take_profit"] = safe_float(row.get("triggerPrice"))
        elif stop_type == "stoploss":
            protections.setdefault(symbol, {})["stop_loss"] = safe_float(row.get("triggerPrice"))
    return protections


def _epoch_millis_to_iso(value: Any) -> str | None:
    millis = safe_float(value)
    if millis is None:
        return None
    try:
        return datetime.fromtimestamp(millis / 1000, tz=timezone.utc).isoformat()
    except (ValueError, OverflowError, OSError):
        return None

