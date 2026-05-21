from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pandas as pd

WALLET_SUMMARY_FIELDS = {
    "equity": "totalEquity",
    "wallet_balance": "totalWalletBalance",
    "available_balance": "totalAvailableBalance",
    "margin_used": "totalInitialMargin",
    "unrealized_pnl": "totalPerpUPL",
}

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


def safe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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


def select_latest_scanner_job(jobs: list[dict]) -> dict | None:
    done_jobs = [job for job in jobs if job.get("status") == "done"]
    causal = [job for job in done_jobs if job.get("job_type") == "causal_scan"]
    regular = [job for job in done_jobs if job.get("job_type") in (None, "", "scan")]
    if causal:
        return max(causal, key=_job_updated_at)
    if regular:
        return max(regular, key=_job_updated_at)
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
    return datetime.fromtimestamp(millis / 1000, tz=timezone.utc).isoformat()


def _job_updated_at(job: dict) -> datetime:
    value = job.get("updated_at")
    if not value:
        return datetime.min.replace(tzinfo=timezone.utc)
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)


def _frame(value: Any) -> pd.DataFrame:
    if value is None:
        return pd.DataFrame()
    if isinstance(value, pd.DataFrame):
        return value.copy()
    return pd.DataFrame(value)


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
    return out[WATCHLIST_COLUMNS]


def _causal_evaluation_merge_keys(signals: pd.DataFrame, evaluations: pd.DataFrame) -> list[str]:
    signal_keys = ["date", "symbol", "signal_time_utc"]
    if all(key in signals.columns and key in evaluations.columns for key in signal_keys):
        return signal_keys
    return ["symbol"]
