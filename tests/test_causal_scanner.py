from __future__ import annotations

from bybit_weak_intraday.causal import CausalSignal
from bybit_weak_intraday.causal_scanner import signals_to_frame


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
