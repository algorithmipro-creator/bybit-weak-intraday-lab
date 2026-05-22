from __future__ import annotations

import math

import pandas as pd

from bybit_weak_intraday.signals.decision import DecisionConfig, evaluate_signal_candidate


def _candidate(**overrides):
    row = {
        "symbol": "ENAUSDT",
        "mode": "weak",
        "score": 10,
        "price": 0.1,
        "time_utc": "2026-03-18T10:00:00+00:00",
    }
    row.update(overrides)
    return row


def _config(**overrides):
    values = {
        "min_score": 9,
        "symbol_whitelist": {"ENAUSDT", "JTOUSDT"},
        "execution_mode": "demo",
        "execution_enabled": True,
        "demo_keys_configured": True,
        "auto_entry_enabled": True,
        "notional_usdt": 25.0,
        "max_notional_usdt": 25.0,
        "open_positions_count": 0,
        "max_open_positions": 1,
        "daily_order_count": 0,
        "max_daily_orders": 3,
        "cooldown_active": False,
        "take_profit_pct": 0.06,
        "stop_loss_pct": 0.07,
    }
    values.update(overrides)
    return DecisionConfig(**values)


def test_evaluate_signal_candidate_qualifies_valid_candidate() -> None:
    decision = evaluate_signal_candidate(_candidate(), _config(), job_id="job-1", job_type="causal_scan")

    assert decision["status"] == "qualified"
    assert decision["reason"] == "qualified"
    assert decision["symbol"] == "ENAUSDT"
    assert decision["side"] == "Sell"
    assert decision["job_id"] == "job-1"
    assert decision["notional_usdt"] == 25.0


def test_evaluate_signal_candidate_rejects_score_below_threshold() -> None:
    decision = evaluate_signal_candidate(_candidate(score=8), _config(), job_id="job-1", job_type="scan")

    assert decision["status"] == "rejected"
    assert decision["reason"] == "score_below_threshold"


def test_evaluate_signal_candidate_rejects_symbol_not_whitelisted() -> None:
    decision = evaluate_signal_candidate(_candidate(symbol="BADUSDT"), _config(), job_id="job-1", job_type="scan")

    assert decision["status"] == "rejected"
    assert decision["reason"] == "symbol_not_whitelisted"


def test_evaluate_signal_candidate_rejects_disabled_execution_before_entry() -> None:
    decision = evaluate_signal_candidate(_candidate(), _config(execution_enabled=False), job_id="job-1", job_type="scan")

    assert decision["status"] == "rejected"
    assert decision["reason"] == "execution_disabled"


def test_evaluate_signal_candidate_rejects_auto_entry_disabled_when_order_requested() -> None:
    decision = evaluate_signal_candidate(
        _candidate(),
        _config(auto_entry_enabled=False),
        job_id="job-1",
        job_type="scan",
        require_auto_entry=True,
    )

    assert decision["status"] == "rejected"
    assert decision["reason"] == "auto_entry_disabled"


def test_evaluate_signal_candidate_rejects_missing_price() -> None:
    decision = evaluate_signal_candidate(_candidate(price=None), _config(), job_id="job-1", job_type="scan")

    assert decision["status"] == "rejected"
    assert decision["reason"] == "candidate_missing_price"


def test_evaluate_signal_candidate_rejects_pandas_na_symbol_without_crashing() -> None:
    decision = evaluate_signal_candidate(_candidate(symbol=pd.NA), _config(), job_id="job-1", job_type="scan")

    assert decision["status"] == "rejected"
    assert decision["reason"] == "symbol_not_whitelisted"
    assert decision["symbol"] == ""


def test_evaluate_signal_candidate_rejects_non_positive_price_as_missing() -> None:
    zero = evaluate_signal_candidate(_candidate(price=0), _config(), job_id="job-1", job_type="scan")
    negative = evaluate_signal_candidate(_candidate(price=-0.1), _config(), job_id="job-1", job_type="scan")

    assert zero["reason"] == "candidate_missing_price"
    assert negative["reason"] == "candidate_missing_price"


def test_evaluate_signal_candidate_rejects_invalid_notional_values() -> None:
    zero = evaluate_signal_candidate(_candidate(), _config(notional_usdt=0), job_id="job-1", job_type="scan")
    non_finite = evaluate_signal_candidate(_candidate(), _config(notional_usdt=math.nan), job_id="job-1", job_type="scan")

    assert zero["reason"] == "invalid_notional"
    assert non_finite["reason"] == "invalid_notional"


def test_evaluate_signal_candidate_rejects_invalid_notional_limit() -> None:
    decision = evaluate_signal_candidate(_candidate(), _config(max_notional_usdt=0), job_id="job-1", job_type="scan")

    assert decision["reason"] == "invalid_notional_limit"


def test_evaluate_signal_candidate_rejects_invalid_take_profit_or_stop_loss() -> None:
    missing = evaluate_signal_candidate(_candidate(), _config(take_profit_pct=0), job_id="job-1", job_type="scan")
    too_large = evaluate_signal_candidate(_candidate(), _config(stop_loss_pct=1), job_id="job-1", job_type="scan")

    assert missing["reason"] == "missing_take_profit_or_stop_loss"
    assert too_large["reason"] == "invalid_take_profit_or_stop_loss_pct"
