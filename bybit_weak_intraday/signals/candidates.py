from __future__ import annotations

import math
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

import pandas as pd

WATCHLIST_COLUMNS = [
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
WATCHLIST_NUMERIC_COLUMNS = ["score", "price", "turnover_usdt", "pnl_underlying_pct"]


def select_latest_scanner_job(jobs: list[dict] | None) -> dict | None:
    if not isinstance(jobs, (list, tuple)):
        return None
    scanner_jobs = [
        job
        for job in jobs
        if isinstance(job, dict)
        and job.get("status") == "done"
        and job.get("job_type") in ("causal_scan", "scan", "", None)
    ]
    if scanner_jobs:
        return max(scanner_jobs, key=_job_updated_at)
    return None


def build_scanner_watchlist(
    job_type: str,
    *,
    signals: Any = None,
    evaluations: Any = None,
    trades: Any = None,
    max_rows: int = 20,
) -> pd.DataFrame:
    if job_type == "causal_scan":
        watchlist = _causal_watchlist(signals, evaluations)
    else:
        watchlist = _regular_watchlist(trades)
    return watchlist.head(max_rows).reset_index(drop=True)


def _job_updated_at(job: dict) -> datetime:
    value = job.get("updated_at")
    if not value:
        return datetime.min.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _frame(value: Any) -> pd.DataFrame:
    if value is None:
        return pd.DataFrame()
    if isinstance(value, pd.DataFrame):
        return value.copy()
    if isinstance(value, (list, tuple)) and not all(isinstance(row, Mapping) for row in value):
        return pd.DataFrame()
    try:
        return pd.DataFrame(value)
    except (TypeError, ValueError):
        return pd.DataFrame()


def _causal_watchlist(signals: Any, evaluations: Any) -> pd.DataFrame:
    df = _frame(signals)
    if df.empty:
        return pd.DataFrame(columns=WATCHLIST_COLUMNS)

    evals = _frame(evaluations)
    if not evals.empty and "symbol" in df.columns and "symbol" in evals.columns:
        keys = _causal_evaluation_merge_keys(df, evals)
        keep = keys + [column for column in ["outcome", "pnl_underlying_pct"] if column in evals.columns]
        df = df.merge(evals[keep].drop_duplicates(keys, keep="last"), on=keys, how="left")

    df = df.rename(
        columns={
            "signal_time_utc": "time_utc",
            "signal_price": "price",
            "turnover_so_far_usdt": "turnover_usdt",
        }
    )
    df["status"] = "waiting"

    return _with_watchlist_columns(df)


def _regular_watchlist(trades: Any) -> pd.DataFrame:
    df = _frame(trades)
    if df.empty:
        return pd.DataFrame(columns=WATCHLIST_COLUMNS)
    df = df.rename(
        columns={
            "candidate_score": "score",
            "entry_time_utc": "time_utc",
            "entry_price": "price",
        }
    )
    df["status"] = "candidate"
    return _with_watchlist_columns(df)


def _with_watchlist_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for column in WATCHLIST_COLUMNS:
        if column not in out.columns:
            out[column] = pd.NA
    for column in WATCHLIST_NUMERIC_COLUMNS:
        out[column] = out[column].map(_watchlist_number)
    return out[WATCHLIST_COLUMNS]


def _causal_evaluation_merge_keys(signals: pd.DataFrame, evaluations: pd.DataFrame) -> list[str]:
    signal_keys = ["date", "symbol", "signal_time_utc"]
    if all(key in signals.columns and key in evaluations.columns for key in signal_keys):
        return signal_keys
    return ["symbol"]


def _watchlist_number(value: Any) -> float | Any:
    parsed = _safe_float(value)
    return parsed if parsed is not None else pd.NA


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, str) and value == "":
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None
