from __future__ import annotations

import pandas as pd
import pytest

from bybit_weak_intraday.causal import CausalSignal
import bybit_weak_intraday.causal_scanner as scanner
from bybit_weak_intraday.causal_scanner import (
    evaluate_causal_signal,
    evaluations_to_frame,
    run_archive_causal_scan_outputs,
    signals_to_frame,
)
from bybit_weak_intraday.core import StrategyConfig


def _signal(**overrides) -> CausalSignal:
    values = {
        "date": "2026-03-18",
        "symbol": "TESTUSDT",
        "mode": "weak",
        "signal_time_utc": "2026-03-18T00:05:00+00:00",
        "signal_price": 100.0,
        "score": 9,
        "weak_score": 9,
        "pump_score": 3,
        "turnover_so_far_usdt": 1_500_000,
        "prev_turnover_usdt": 2_000_000,
        "turnover_ratio_so_far": 0.75,
        "runup_so_far_pct": 6.0,
        "peak_time_utc": "2026-03-18T00:00:00+00:00",
        "vwap_at_signal": 101.0,
        "sell_share_peak_to_signal_pct": 54.0,
    }
    values.update(overrides)
    return CausalSignal(**values)


def test_signals_to_frame_preserves_causal_fields():
    signals = [
        CausalSignal(
            date="2026-03-18",
            symbol="TESTUSDT",
            mode="weak",
            signal_time_utc="2026-03-18T10:00:00+00:00",
            signal_price=1.23,
            score=9,
            weak_score=9,
            pump_score=3,
            turnover_so_far_usdt=1_500_000,
            prev_turnover_usdt=2_000_000,
            turnover_ratio_so_far=0.75,
            runup_so_far_pct=6.0,
            peak_time_utc="2026-03-18T09:30:00+00:00",
            vwap_at_signal=1.25,
            sell_share_peak_to_signal_pct=54.0,
        )
    ]

    frame = signals_to_frame(signals)

    assert list(frame.columns) == [
        "date",
        "symbol",
        "mode",
        "signal_time_utc",
        "signal_price",
        "score",
        "weak_score",
        "pump_score",
        "turnover_so_far_usdt",
        "prev_turnover_usdt",
        "turnover_ratio_so_far",
        "runup_so_far_pct",
        "peak_time_utc",
        "vwap_at_signal",
        "sell_share_peak_to_signal_pct",
    ]
    assert frame.loc[0, "symbol"] == "TESTUSDT"
    assert frame.loc[0, "score"] == 9


def test_signals_to_frame_empty_has_stable_columns():
    frame = signals_to_frame([])

    assert frame.empty
    assert "signal_time_utc" in frame.columns


def test_evaluate_causal_signal_uses_only_ticks_after_signal():
    ticks = pd.DataFrame(
        {
            "timestamp": [1773792000, 1773792300, 1773792600, 1773792900],
            "side": ["Sell", "Sell", "Sell", "Sell"],
            "size": [1, 1, 1, 1],
            "price": [80.0, 100.0, 99.0, 94.0],
        }
    )

    row = evaluate_causal_signal(_signal(), ticks, StrategyConfig(tp_weak=0.06, sl_weak=0.07))

    assert row["entry_time_utc"] == "2026-03-18T00:05:00+00:00"
    assert row["entry_price"] == 100.0
    assert row["tp_pct"] == 6.0
    assert row["sl_pct"] == 7.000000000000001
    assert row["outcome"] == "tp"
    assert row["exit_price"] == 94.0
    assert row["pnl_underlying_pct"] == pytest.approx(6.0)
    assert row["minutes_to_exit"] == pytest.approx(10.0)
    assert row["mfe_after_entry_pct"] == pytest.approx(6.0)
    assert row["mae_after_entry_pct"] == pytest.approx(0.0)


def test_evaluate_causal_signal_uses_pump_tp_sl():
    ticks = pd.DataFrame(
        {
            "timestamp": [1773792300, 1773792600],
            "side": ["Sell", "Sell"],
            "size": [1, 1],
            "price": [100.0, 92.0],
        }
    )

    row = evaluate_causal_signal(
        _signal(mode="pump"),
        ticks,
        StrategyConfig(tp_weak=0.06, sl_weak=0.07, tp_pump=0.08, sl_pump=0.05),
    )

    assert row["tp_pct"] == 8.0
    assert row["sl_pct"] == 5.0
    assert row["outcome"] == "tp"
    assert row["pnl_underlying_pct"] == pytest.approx(8.0)


def test_evaluations_to_frame_empty_has_stable_columns():
    frame = evaluations_to_frame([])

    assert frame.empty
    assert "pnl_underlying_pct" in frame.columns


def test_run_archive_causal_scan_outputs_returns_signals_and_evaluations(monkeypatch, tmp_path):
    cur_ticks = pd.DataFrame(
        {
            "timestamp": [1773792300, 1773792600],
            "side": ["Sell", "Sell"],
            "size": [1, 1],
            "price": [100.0, 94.0],
        }
    )
    prev_ticks = pd.DataFrame(
        {
            "timestamp": [1773705600, 1773705900],
            "side": ["Sell", "Sell"],
            "size": [1, 1],
            "price": [100.0, 90.0],
        }
    )

    def fake_download(_sess, symbol, day, _cache, sleep=0.15):
        return scanner.ArchiveDownloadResult(path=f"{symbol}-{day}", status="cache_hit")

    def fake_load(path):
        return cur_ticks if "2026-03-18" in str(path) else prev_ticks

    def fake_find(symbol, day, _cur_ticks, _prev_ticks, _cfg):
        return [_signal(symbol=symbol, date=day)]

    monkeypatch.setattr(scanner, "download_archive_file_result", fake_download)
    monkeypatch.setattr(scanner, "load_archive_ticks", fake_load)
    monkeypatch.setattr(scanner, "find_causal_signals", fake_find)

    signals, evaluations = run_archive_causal_scan_outputs(
        start="2026-03-18",
        end="2026-03-18",
        symbols=["testusdt"],
        cache_dir=tmp_path,
        cfg=StrategyConfig(tp_weak=0.06, sl_weak=0.07),
    )

    assert len(signals) == 1
    assert len(evaluations) == 1
    assert signals.loc[0, "symbol"] == "TESTUSDT"
    assert evaluations.loc[0, "outcome"] == "tp"
    assert evaluations.loc[0, "pnl_underlying_pct"] == pytest.approx(6.0)


def test_run_archive_causal_scan_outputs_emits_progress_for_missing_archive(monkeypatch, tmp_path):
    events: list[dict] = []

    def fake_download(_sess, symbol, day, _cache, sleep=0.15):
        if str(day) == "2026-03-17":
            return scanner.ArchiveDownloadResult(path=None, status="missing")
        return scanner.ArchiveDownloadResult(path=tmp_path / f"{symbol}-{day}.csv.gz", status="cache_hit")

    monkeypatch.setattr(scanner, "download_archive_file_result", fake_download)
    monkeypatch.setattr(scanner, "load_archive_ticks", lambda path: pd.DataFrame())
    monkeypatch.setattr(scanner, "find_causal_signals", lambda *args, **kwargs: [])

    signals, evaluations = run_archive_causal_scan_outputs(
        start="2026-03-18",
        end="2026-03-18",
        symbols=["testusdt"],
        cache_dir=tmp_path,
        progress_callback=events.append,
    )

    assert signals.empty
    assert evaluations.empty
    assert events[-1]["processed"] == 1
    assert events[-1]["total"] == 1
    assert events[-1]["current_symbol"] == "TESTUSDT"
    assert events[-1]["missing_files"] == 1
    assert events[-1]["warnings"] == [
        {"symbol": "TESTUSDT", "date": "2026-03-18", "message": "archive file missing"}
    ]


def test_run_archive_causal_scan_outputs_callback_failure_does_not_mutate_successful_scan(
    monkeypatch,
    tmp_path,
):
    events: list[dict] = []
    callback_calls = 0
    cur_ticks = pd.DataFrame(
        {
            "timestamp": [1773792300, 1773792600],
            "side": ["Sell", "Sell"],
            "size": [1, 1],
            "price": [100.0, 94.0],
        }
    )
    prev_ticks = pd.DataFrame(
        {
            "timestamp": [1773705600, 1773705900],
            "side": ["Sell", "Sell"],
            "size": [1, 1],
            "price": [100.0, 90.0],
        }
    )

    def fake_download(_sess, symbol, day, _cache, sleep=0.15):
        return scanner.ArchiveDownloadResult(path=tmp_path / f"{symbol}-{day}.csv.gz", status="cache_hit")

    def fake_load(path):
        return cur_ticks if "2026-03-18" in str(path) else prev_ticks

    def fake_find(symbol, day, _cur_ticks, _prev_ticks, _cfg):
        return [_signal(symbol=symbol, date=day)]

    def failing_callback(event: dict) -> None:
        nonlocal callback_calls
        callback_calls += 1
        events.append(event)
        if callback_calls == 1:
            raise RuntimeError("job store unavailable")

    monkeypatch.setattr(scanner, "download_archive_file_result", fake_download)
    monkeypatch.setattr(scanner, "load_archive_ticks", fake_load)
    monkeypatch.setattr(scanner, "find_causal_signals", fake_find)

    signals, evaluations = run_archive_causal_scan_outputs(
        start="2026-03-18",
        end="2026-03-18",
        symbols=["testusdt"],
        cache_dir=tmp_path,
        cfg=StrategyConfig(tp_weak=0.06, sl_weak=0.07),
        progress_callback=failing_callback,
    )

    assert callback_calls == 1
    assert len(events) == 1
    assert events[0]["processed"] == 1
    assert events[0]["total"] == 1
    assert events[0]["errors"] == 0
    assert len(signals) == 1
    assert "error" not in signals.columns
    assert signals.loc[0, "symbol"] == "TESTUSDT"
    assert len(evaluations) == 1
    assert evaluations.loc[0, "outcome"] == "tp"
