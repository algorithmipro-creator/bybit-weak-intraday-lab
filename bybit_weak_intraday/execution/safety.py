from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

DEMO_BASE_URL = "https://api-demo.bybit.com"


@dataclass(frozen=True)
class ExecutionConfig:
    execution_mode: str = "disabled"
    execution_enabled: bool = False
    api_key: str = ""
    api_secret: str = ""
    base_url: str = DEMO_BASE_URL
    symbol_whitelist: tuple[str, ...] = ()
    max_demo_notional_usdt: float = 25.0
    max_open_positions: int = 1
    max_daily_test_orders: int = 3


@dataclass(frozen=True)
class SafetyDecision:
    allowed: bool
    reason: str


def parse_symbol_whitelist(value: str | Sequence[str]) -> tuple[str, ...]:
    if isinstance(value, str):
        raw_symbols = value.split(",")
    else:
        raw_symbols = value
    symbols: list[str] = []
    for symbol in raw_symbols:
        normalized = str(symbol).strip().upper()
        if normalized:
            symbols.append(normalized)
    return tuple(dict.fromkeys(symbols))


def _blocked(reason: str) -> SafetyDecision:
    return SafetyDecision(allowed=False, reason=reason)


def validate_static_demo_order_request(
    config: ExecutionConfig,
    *,
    symbol: str,
    notional_usdt: float,
    take_profit_pct: float,
    stop_loss_pct: float,
    daily_test_order_count: int,
) -> SafetyDecision:
    normalized_symbol = symbol.strip().upper()
    if config.execution_mode != "demo":
        return _blocked("execution_mode_not_demo")
    if not config.execution_enabled:
        return _blocked("execution_disabled")
    if config.base_url != DEMO_BASE_URL:
        return _blocked("non_demo_base_url")
    if not config.api_key.strip() or not config.api_secret.strip():
        return _blocked("missing_demo_api_keys")
    if normalized_symbol not in config.symbol_whitelist:
        return _blocked("symbol_not_whitelisted")
    if not math.isfinite(float(notional_usdt)) or notional_usdt <= 0:
        return _blocked("invalid_notional")
    if (
        not math.isfinite(float(config.max_demo_notional_usdt))
        or config.max_demo_notional_usdt <= 0
    ):
        return _blocked("invalid_notional_limit")
    if notional_usdt > config.max_demo_notional_usdt:
        return _blocked("notional_limit_exceeded")
    if (
        not math.isfinite(float(take_profit_pct))
        or not math.isfinite(float(stop_loss_pct))
        or take_profit_pct <= 0
        or stop_loss_pct <= 0
    ):
        return _blocked("missing_take_profit_or_stop_loss")
    if daily_test_order_count >= config.max_daily_test_orders:
        return _blocked("daily_test_order_limit_reached")
    return SafetyDecision(allowed=True, reason="allowed")


def validate_position_limit(config: ExecutionConfig, *, open_positions_count: int) -> SafetyDecision:
    if open_positions_count >= config.max_open_positions:
        return _blocked("open_position_limit_reached")
    return SafetyDecision(allowed=True, reason="allowed")
