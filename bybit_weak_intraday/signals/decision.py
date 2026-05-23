from __future__ import annotations

import math
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class DecisionConfig:
    min_score: float
    symbol_whitelist: set[str]
    execution_mode: str
    execution_enabled: bool
    demo_keys_configured: bool
    auto_entry_enabled: bool
    notional_usdt: float
    max_notional_usdt: float
    open_positions_count: int
    max_open_positions: int
    daily_order_count: int
    max_daily_orders: int
    cooldown_active: bool
    take_profit_pct: float
    stop_loss_pct: float


def evaluate_signal_candidate(
    candidate: Mapping[str, Any],
    config: DecisionConfig,
    *,
    job_id: str,
    job_type: str,
    require_auto_entry: bool = False,
) -> dict[str, Any]:
    score = _score(candidate.get("score"))
    symbol = _normalize_symbol(candidate.get("symbol"))
    price = _price(candidate.get("price"))
    status, reason = _decision_status(config, score, symbol, price, require_auto_entry)

    return {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "decision_id": str(uuid.uuid4()),
        "job_id": job_id,
        "job_type": job_type,
        "symbol": symbol,
        "mode": candidate.get("mode"),
        "score": score,
        "side": "Sell",
        "notional_usdt": config.notional_usdt,
        "take_profit_pct": config.take_profit_pct,
        "stop_loss_pct": config.stop_loss_pct,
        "candidate_price": price,
        "candidate_time_utc": candidate.get("time_utc"),
        "status": status,
        "reason": reason,
    }


def _decision_status(
    config: DecisionConfig,
    score: float,
    symbol: str,
    price: float | None,
    require_auto_entry: bool,
) -> tuple[str, str]:
    if score < config.min_score:
        return "rejected", "score_below_threshold"
    if symbol not in _normalized_whitelist(config.symbol_whitelist):
        return "rejected", "symbol_not_whitelisted"
    if price is None:
        return "rejected", "candidate_missing_price"
    if str(config.execution_mode).strip().lower() != "demo":
        return "rejected", "execution_mode_not_demo"
    if not config.execution_enabled:
        return "rejected", "execution_disabled"
    if not config.demo_keys_configured:
        return "rejected", "missing_demo_keys"
    notional_usdt = _finite_float(config.notional_usdt)
    max_notional_usdt = _finite_float(config.max_notional_usdt)
    take_profit_pct = _finite_float(config.take_profit_pct)
    stop_loss_pct = _finite_float(config.stop_loss_pct)
    if notional_usdt is None or notional_usdt <= 0:
        return "rejected", "invalid_notional"
    if max_notional_usdt is None or max_notional_usdt <= 0:
        return "rejected", "invalid_notional_limit"
    if take_profit_pct is None or stop_loss_pct is None or take_profit_pct <= 0 or stop_loss_pct <= 0:
        return "rejected", "missing_take_profit_or_stop_loss"
    if take_profit_pct >= 1 or stop_loss_pct >= 1:
        return "rejected", "invalid_take_profit_or_stop_loss_pct"
    if notional_usdt > max_notional_usdt:
        return "rejected", "notional_limit_exceeded"
    if config.open_positions_count >= config.max_open_positions:
        return "rejected", "max_open_positions_reached"
    if config.daily_order_count >= config.max_daily_orders:
        return "rejected", "daily_limit_reached"
    if config.cooldown_active:
        return "rejected", "cooldown_active"
    if require_auto_entry and not config.auto_entry_enabled:
        return "rejected", "auto_entry_disabled"
    return "qualified", "qualified"


def _score(value: Any) -> float:
    parsed = _finite_float(value)
    return parsed if parsed is not None else 0.0


def _price(value: Any) -> float | None:
    parsed = _finite_float(value)
    return parsed if parsed is not None and parsed > 0 else None


def _finite_float(value: Any) -> float | None:
    if _is_missing(value):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _normalize_symbol(value: Any) -> str:
    return "" if _is_missing(value) else str(value).strip().upper()


def _normalized_whitelist(symbols: set[str]) -> set[str]:
    return {_normalize_symbol(symbol) for symbol in symbols}


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    try:
        return bool(value != value)
    except (TypeError, ValueError):
        return True
