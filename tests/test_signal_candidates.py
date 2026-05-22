from __future__ import annotations

import pandas as pd

from bybit_weak_intraday.signals.candidates import build_scanner_watchlist, select_latest_scanner_job


def test_select_latest_scanner_job_selects_latest_done_scan_or_causal() -> None:
    jobs = [
        {"job_id": "old", "job_type": "scan", "status": "done", "updated_at": "2026-05-22T10:00:00+00:00"},
        {"job_id": "new", "job_type": "causal_scan", "status": "done", "updated_at": "2026-05-22T11:00:00+00:00"},
        {"job_id": "running", "job_type": "scan", "status": "running", "updated_at": "2026-05-22T12:00:00+00:00"},
    ]

    assert select_latest_scanner_job(jobs)["job_id"] == "new"


def test_build_scanner_watchlist_from_causal_signals() -> None:
    signals = pd.DataFrame(
        [
            {
                "date": "2026-03-18",
                "symbol": "ENAUSDT",
                "mode": "weak",
                "score": 10,
                "signal_time_utc": "2026-03-18T10:00:00+00:00",
                "signal_price": 0.1,
                "turnover_so_far_usdt": 2_000_000,
            }
        ]
    )
    evaluations = pd.DataFrame(
        [{"date": "2026-03-18", "symbol": "ENAUSDT", "signal_time_utc": "2026-03-18T10:00:00+00:00", "outcome": "tp"}]
    )

    watchlist = build_scanner_watchlist("causal_scan", signals=signals, evaluations=evaluations)

    assert list(watchlist.columns) == [
        "symbol",
        "mode",
        "score",
        "time_utc",
        "price",
        "turnover_usdt",
        "status",
        "outcome",
        "pnl_underlying_pct",
    ]
    assert watchlist.loc[0, "status"] == "waiting"
    assert watchlist.loc[0, "outcome"] == "tp"


def test_build_scanner_watchlist_from_regular_scan() -> None:
    trades = pd.DataFrame(
        [
            {
                "symbol": "JTOUSDT",
                "mode": "pump",
                "candidate_score": 9,
                "entry_time_utc": "2026-03-18T11:00:00+00:00",
                "entry_price": 1.23,
                "turnover_usdt": 3_000_000,
            }
        ]
    )

    watchlist = build_scanner_watchlist("scan", trades=trades)

    assert watchlist.loc[0, "symbol"] == "JTOUSDT"
    assert watchlist.loc[0, "score"] == 9
    assert watchlist.loc[0, "status"] == "candidate"
