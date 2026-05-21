from __future__ import annotations

from bybit_weak_intraday.execution.safety import (
    DEMO_BASE_URL,
    ExecutionConfig,
    SafetyDecision,
    parse_symbol_whitelist,
    validate_position_limit,
    validate_static_demo_order_request,
)


def _config(**overrides) -> ExecutionConfig:
    values = {
        "execution_mode": "demo",
        "execution_enabled": True,
        "api_key": "key",
        "api_secret": "secret",
        "base_url": DEMO_BASE_URL,
        "symbol_whitelist": ("ENAUSDT", "JTOUSDT"),
        "max_demo_notional_usdt": 25.0,
        "max_open_positions": 1,
        "max_daily_test_orders": 3,
    }
    values.update(overrides)
    return ExecutionConfig(**values)


def test_parse_symbol_whitelist_normalizes_symbols() -> None:
    assert parse_symbol_whitelist(" enausdt, JTOUSDT ,,") == ("ENAUSDT", "JTOUSDT")


def test_execution_package_import_star_exposes_safety_module() -> None:
    namespace: dict[str, object] = {}

    exec("from bybit_weak_intraday.execution import *", namespace)

    assert namespace["safety"].SafetyDecision is SafetyDecision


def test_static_gate_blocks_disabled_mode() -> None:
    decision = validate_static_demo_order_request(
        _config(execution_mode="disabled"),
        symbol="ENAUSDT",
        notional_usdt=10,
        take_profit_pct=0.06,
        stop_loss_pct=0.07,
        daily_test_order_count=0,
    )

    assert not decision.allowed
    assert decision.reason == "execution_mode_not_demo"


def test_static_gate_blocks_when_execution_flag_is_false() -> None:
    decision = validate_static_demo_order_request(
        _config(execution_enabled=False),
        symbol="ENAUSDT",
        notional_usdt=10,
        take_profit_pct=0.06,
        stop_loss_pct=0.07,
        daily_test_order_count=0,
    )

    assert not decision.allowed
    assert decision.reason == "execution_disabled"


def test_static_gate_blocks_mainnet_base_url() -> None:
    decision = validate_static_demo_order_request(
        _config(base_url="https://api.bybit.com"),
        symbol="ENAUSDT",
        notional_usdt=10,
        take_profit_pct=0.06,
        stop_loss_pct=0.07,
        daily_test_order_count=0,
    )

    assert not decision.allowed
    assert decision.reason == "non_demo_base_url"


def test_static_gate_blocks_trailing_slash_demo_base_url() -> None:
    decision = validate_static_demo_order_request(
        _config(base_url="https://api-demo.bybit.com/"),
        symbol="ENAUSDT",
        notional_usdt=10,
        take_profit_pct=0.06,
        stop_loss_pct=0.07,
        daily_test_order_count=0,
    )

    assert not decision.allowed
    assert decision.reason == "non_demo_base_url"


def test_static_gate_blocks_missing_keys() -> None:
    decision = validate_static_demo_order_request(
        _config(api_key="", api_secret=""),
        symbol="ENAUSDT",
        notional_usdt=10,
        take_profit_pct=0.06,
        stop_loss_pct=0.07,
        daily_test_order_count=0,
    )

    assert not decision.allowed
    assert decision.reason == "missing_demo_api_keys"


def test_static_gate_blocks_whitespace_keys() -> None:
    decision = validate_static_demo_order_request(
        _config(api_key=" ", api_secret="\t"),
        symbol="ENAUSDT",
        notional_usdt=10,
        take_profit_pct=0.06,
        stop_loss_pct=0.07,
        daily_test_order_count=0,
    )

    assert not decision.allowed
    assert decision.reason == "missing_demo_api_keys"


def test_static_gate_blocks_non_whitelisted_symbol() -> None:
    decision = validate_static_demo_order_request(
        _config(),
        symbol="BTCUSDT",
        notional_usdt=10,
        take_profit_pct=0.06,
        stop_loss_pct=0.07,
        daily_test_order_count=0,
    )

    assert not decision.allowed
    assert decision.reason == "symbol_not_whitelisted"


def test_static_gate_blocks_oversized_notional() -> None:
    decision = validate_static_demo_order_request(
        _config(max_demo_notional_usdt=25),
        symbol="ENAUSDT",
        notional_usdt=26,
        take_profit_pct=0.06,
        stop_loss_pct=0.07,
        daily_test_order_count=0,
    )

    assert not decision.allowed
    assert decision.reason == "notional_limit_exceeded"


def test_static_gate_blocks_non_finite_notional_limit() -> None:
    decision = validate_static_demo_order_request(
        _config(max_demo_notional_usdt=float("inf")),
        symbol="ENAUSDT",
        notional_usdt=10,
        take_profit_pct=0.06,
        stop_loss_pct=0.07,
        daily_test_order_count=0,
    )

    assert not decision.allowed
    assert decision.reason == "invalid_notional_limit"


def test_static_gate_blocks_non_positive_notional_limit() -> None:
    decision = validate_static_demo_order_request(
        _config(max_demo_notional_usdt=0),
        symbol="ENAUSDT",
        notional_usdt=10,
        take_profit_pct=0.06,
        stop_loss_pct=0.07,
        daily_test_order_count=0,
    )

    assert not decision.allowed
    assert decision.reason == "invalid_notional_limit"


def test_static_gate_blocks_invalid_notional() -> None:
    decision = validate_static_demo_order_request(
        _config(),
        symbol="ENAUSDT",
        notional_usdt=0,
        take_profit_pct=0.06,
        stop_loss_pct=0.07,
        daily_test_order_count=0,
    )

    assert not decision.allowed
    assert decision.reason == "invalid_notional"


def test_static_gate_blocks_non_finite_notional() -> None:
    decision = validate_static_demo_order_request(
        _config(),
        symbol="ENAUSDT",
        notional_usdt=float("nan"),
        take_profit_pct=0.06,
        stop_loss_pct=0.07,
        daily_test_order_count=0,
    )

    assert not decision.allowed
    assert decision.reason == "invalid_notional"


def test_static_gate_blocks_infinite_notional() -> None:
    decision = validate_static_demo_order_request(
        _config(),
        symbol="ENAUSDT",
        notional_usdt=float("inf"),
        take_profit_pct=0.06,
        stop_loss_pct=0.07,
        daily_test_order_count=0,
    )

    assert not decision.allowed
    assert decision.reason == "invalid_notional"


def test_static_gate_blocks_missing_tp_sl() -> None:
    decision = validate_static_demo_order_request(
        _config(),
        symbol="ENAUSDT",
        notional_usdt=10,
        take_profit_pct=0,
        stop_loss_pct=0.07,
        daily_test_order_count=0,
    )

    assert not decision.allowed
    assert decision.reason == "missing_take_profit_or_stop_loss"


def test_static_gate_blocks_non_finite_take_profit() -> None:
    decision = validate_static_demo_order_request(
        _config(),
        symbol="ENAUSDT",
        notional_usdt=10,
        take_profit_pct=float("nan"),
        stop_loss_pct=0.07,
        daily_test_order_count=0,
    )

    assert not decision.allowed
    assert decision.reason == "missing_take_profit_or_stop_loss"


def test_static_gate_blocks_non_finite_stop_loss() -> None:
    decision = validate_static_demo_order_request(
        _config(),
        symbol="ENAUSDT",
        notional_usdt=10,
        take_profit_pct=0.06,
        stop_loss_pct=float("nan"),
        daily_test_order_count=0,
    )

    assert not decision.allowed
    assert decision.reason == "missing_take_profit_or_stop_loss"


def test_static_gate_blocks_take_profit_pct_at_or_above_one() -> None:
    decision = validate_static_demo_order_request(
        _config(),
        symbol="ENAUSDT",
        notional_usdt=10,
        take_profit_pct=1,
        stop_loss_pct=0.07,
        daily_test_order_count=0,
    )

    assert not decision.allowed
    assert decision.reason == "invalid_take_profit_or_stop_loss_pct"


def test_static_gate_blocks_stop_loss_pct_at_or_above_one() -> None:
    decision = validate_static_demo_order_request(
        _config(),
        symbol="ENAUSDT",
        notional_usdt=10,
        take_profit_pct=0.06,
        stop_loss_pct=1,
        daily_test_order_count=0,
    )

    assert not decision.allowed
    assert decision.reason == "invalid_take_profit_or_stop_loss_pct"


def test_static_gate_blocks_daily_order_limit() -> None:
    decision = validate_static_demo_order_request(
        _config(max_daily_test_orders=3),
        symbol="ENAUSDT",
        notional_usdt=10,
        take_profit_pct=0.06,
        stop_loss_pct=0.07,
        daily_test_order_count=3,
    )

    assert not decision.allowed
    assert decision.reason == "daily_test_order_limit_reached"


def test_static_gate_allows_valid_request() -> None:
    decision = validate_static_demo_order_request(
        _config(),
        symbol="enausdt",
        notional_usdt=10,
        take_profit_pct=0.06,
        stop_loss_pct=0.07,
        daily_test_order_count=0,
    )

    assert decision.allowed
    assert decision.reason == "allowed"


def test_position_gate_blocks_open_position_limit() -> None:
    decision = validate_position_limit(_config(max_open_positions=1), open_positions_count=1)

    assert not decision.allowed
    assert decision.reason == "open_position_limit_reached"


def test_position_gate_allows_below_open_position_limit() -> None:
    decision = validate_position_limit(_config(max_open_positions=1), open_positions_count=0)

    assert decision.allowed
    assert decision.reason == "allowed"
