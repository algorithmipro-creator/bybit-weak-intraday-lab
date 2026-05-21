from __future__ import annotations

from decimal import Decimal

import pytest

from bybit_weak_intraday.execution.orders import (
    build_short_market_order_payload,
    calculate_short_tpsl,
    floor_to_step,
    parse_linear_instrument_rules,
    quantity_from_notional,
)


INSTRUMENT_RESPONSE = {
    "result": {
        "list": [
            {
                "symbol": "ENAUSDT",
                "lotSizeFilter": {"qtyStep": "1", "minOrderQty": "1"},
                "priceFilter": {"tickSize": "0.0001"},
            }
        ]
    }
}


def test_parse_linear_instrument_rules_extracts_steps() -> None:
    rules = parse_linear_instrument_rules(INSTRUMENT_RESPONSE)

    assert rules.symbol == "ENAUSDT"
    assert rules.qty_step == Decimal("1")
    assert rules.min_order_qty == Decimal("1")
    assert rules.tick_size == Decimal("0.0001")


def test_floor_to_step_rounds_down() -> None:
    assert floor_to_step(Decimal("12.987"), Decimal("0.1")) == Decimal("12.9")


def test_quantity_from_notional_uses_reference_price_and_min_qty() -> None:
    rules = parse_linear_instrument_rules(INSTRUMENT_RESPONSE)

    assert quantity_from_notional(Decimal("10"), Decimal("0.7432"), rules) == Decimal("13")


def test_quantity_from_notional_supports_fractional_qty_step() -> None:
    response = {
        "result": {
            "list": [
                {
                    "symbol": "ENAUSDT",
                    "lotSizeFilter": {"qtyStep": "0.001", "minOrderQty": "0.001"},
                    "priceFilter": {"tickSize": "0.0001"},
                }
            ]
        }
    }
    rules = parse_linear_instrument_rules(response)

    assert quantity_from_notional(Decimal("1"), Decimal("2"), rules) == Decimal("0.5")


def test_quantity_from_notional_rejects_too_small_notional() -> None:
    rules = parse_linear_instrument_rules(INSTRUMENT_RESPONSE)

    with pytest.raises(ValueError, match="quantity_below_min_order_qty"):
        quantity_from_notional(Decimal("0.01"), Decimal("0.7432"), rules)


def test_quantity_from_notional_rejects_non_finite_notional() -> None:
    rules = parse_linear_instrument_rules(INSTRUMENT_RESPONSE)

    with pytest.raises(ValueError, match="invalid_notional"):
        quantity_from_notional(Decimal("Infinity"), Decimal("0.7432"), rules)


def test_quantity_from_notional_rejects_zero_reference_price() -> None:
    rules = parse_linear_instrument_rules(INSTRUMENT_RESPONSE)

    with pytest.raises(ValueError, match="invalid_reference_price"):
        quantity_from_notional(Decimal("10"), Decimal("0"), rules)


def test_calculate_short_tpsl_places_tp_below_and_sl_above_reference() -> None:
    rules = parse_linear_instrument_rules(INSTRUMENT_RESPONSE)

    tp, sl = calculate_short_tpsl(Decimal("1.0000"), Decimal("0.06"), Decimal("0.07"), rules)

    assert tp == Decimal("0.9400")
    assert sl == Decimal("1.0700")


def test_calculate_short_tpsl_rejects_take_profit_pct_at_or_above_one() -> None:
    rules = parse_linear_instrument_rules(INSTRUMENT_RESPONSE)

    with pytest.raises(ValueError, match="invalid_tpsl_pct"):
        calculate_short_tpsl(Decimal("1.0000"), Decimal("1"), Decimal("0.07"), rules)


def test_calculate_short_tpsl_rejects_non_finite_stop_loss_pct() -> None:
    rules = parse_linear_instrument_rules(INSTRUMENT_RESPONSE)

    with pytest.raises(ValueError, match="invalid_tpsl_pct"):
        calculate_short_tpsl(Decimal("1.0000"), Decimal("0.06"), Decimal("NaN"), rules)


def test_build_short_market_order_payload_uses_linear_sell() -> None:
    payload = build_short_market_order_payload(
        symbol="ENAUSDT",
        qty=Decimal("13"),
        take_profit=Decimal("0.9400"),
        stop_loss=Decimal("1.0700"),
        order_link_id="bwi-demo-1",
    )

    assert payload["category"] == "linear"
    assert payload["symbol"] == "ENAUSDT"
    assert payload["side"] == "Sell"
    assert payload["orderType"] == "Market"
    assert payload["qty"] == "13"
    assert payload["takeProfit"] == "0.9400"
    assert payload["stopLoss"] == "1.0700"
    assert payload["positionIdx"] == 0
    assert payload["orderLinkId"] == "bwi-demo-1"


def test_build_short_market_order_payload_rejects_non_finite_values() -> None:
    with pytest.raises(ValueError, match="invalid_order_payload"):
        build_short_market_order_payload(
            symbol="ENAUSDT",
            qty=Decimal("NaN"),
            take_profit=Decimal("0.9400"),
            stop_loss=Decimal("1.0700"),
            order_link_id="bwi-demo-1",
        )


def test_parse_linear_instrument_rules_rejects_invalid_steps() -> None:
    response = {
        "result": {
            "list": [
                {
                    "symbol": "ENAUSDT",
                    "lotSizeFilter": {"qtyStep": "0", "minOrderQty": "1"},
                    "priceFilter": {"tickSize": "0.0001"},
                }
            ]
        }
    }

    with pytest.raises(ValueError, match="invalid_instrument_rules"):
        parse_linear_instrument_rules(response)
