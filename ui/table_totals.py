from __future__ import annotations

from typing import Any

import pandas as pd

TRADE_TOTAL_COLUMNS = [
    "total_trades",
    "tp_count",
    "sl_count",
    "time_stop_count",
    "eod_count",
    "no_data_count",
    "sum_pnl_underlying_pct",
    "avg_pnl_underlying_pct",
    "sum_mfe_after_entry_pct",
    "avg_mfe_after_entry_pct",
    "sum_mae_after_entry_pct",
    "avg_mae_after_entry_pct",
]

ACCOUNT_TOTAL_COLUMNS = [
    "total_trades",
    "total_net_pnl_usd",
    "total_costs_usd",
    "final_equity_usd",
    "total_return_pct",
    "avg_account_return_pct",
]


def _base_rows(df: pd.DataFrame) -> pd.DataFrame:
    if "row_type" not in df.columns:
        return df.copy()
    mask = df["row_type"].astype(str).str.upper() != "TOTAL"
    return df.loc[mask].copy()


def _numeric(df: pd.DataFrame, column: str) -> pd.Series:
    if column not in df.columns:
        return pd.Series(dtype="float64")
    return pd.to_numeric(df[column], errors="coerce")


def _sum_or_na(df: pd.DataFrame, column: str) -> float | Any:
    values = _numeric(df, column).dropna()
    if values.empty:
        return pd.NA
    return float(values.sum())


def _mean_or_na(df: pd.DataFrame, column: str) -> float | Any:
    values = _numeric(df, column).dropna()
    if values.empty:
        return pd.NA
    return float(values.mean())


def _last_or_na(df: pd.DataFrame, column: str) -> float | Any:
    values = _numeric(df, column).dropna()
    if values.empty:
        return pd.NA
    return float(values.iloc[-1])


def _count_outcome(df: pd.DataFrame, outcome: str) -> int:
    if "outcome" not in df.columns:
        return 0
    outcomes = df["outcome"].astype(str).str.lower()
    return int((outcomes == outcome).sum())


def _total_return_pct(df: pd.DataFrame, initial_equity_usd: float | None) -> float | Any:
    final_equity = _last_or_na(df, "equity_after_usd")
    if pd.isna(final_equity):
        return pd.NA
    if initial_equity_usd is None:
        initial_equity = _last_or_na(df.head(1), "equity_before_usd")
    else:
        initial_equity = float(initial_equity_usd)
    if pd.isna(initial_equity) or initial_equity == 0:
        return pd.NA
    return (float(final_equity) / float(initial_equity) - 1.0) * 100.0


def _ordered_columns(columns: list[str], summary_columns: list[str]) -> list[str]:
    existing = list(columns)
    front = ["row_type"]
    if "symbol" in existing:
        front.append("symbol")
    front.extend(summary_columns)
    return [col for col in front if col in existing] + [col for col in existing if col not in front]


def _append_total_row(df: pd.DataFrame, total_values: dict[str, Any], summary_columns: list[str]) -> pd.DataFrame:
    base = _base_rows(df)
    if base.empty:
        return df.copy()

    out = base.copy()
    if "row_type" not in out.columns:
        out.insert(0, "row_type", "")
    else:
        out["row_type"] = out["row_type"].fillna("")

    for column in summary_columns:
        if column not in out.columns:
            out[column] = pd.NA

    total_row = {column: pd.NA for column in out.columns}
    total_row.update(total_values)
    result = pd.concat([out, pd.DataFrame([total_row])], ignore_index=True)
    return result[_ordered_columns(list(result.columns), summary_columns)]


def append_trade_total_row(df: pd.DataFrame) -> pd.DataFrame:
    """Return a display copy with one aggregate row appended at the bottom."""
    base = _base_rows(df)
    if base.empty:
        return df.copy()

    total_values = {
        "row_type": "TOTAL",
        "symbol": "TOTAL",
        "total_trades": int(len(base)),
        "tp_count": _count_outcome(base, "tp"),
        "sl_count": _count_outcome(base, "sl"),
        "time_stop_count": _count_outcome(base, "time_stop"),
        "eod_count": _count_outcome(base, "eod"),
        "no_data_count": _count_outcome(base, "no_data"),
        "sum_pnl_underlying_pct": _sum_or_na(base, "pnl_underlying_pct"),
        "avg_pnl_underlying_pct": _mean_or_na(base, "pnl_underlying_pct"),
        "sum_mfe_after_entry_pct": _sum_or_na(base, "mfe_after_entry_pct"),
        "avg_mfe_after_entry_pct": _mean_or_na(base, "mfe_after_entry_pct"),
        "sum_mae_after_entry_pct": _sum_or_na(base, "mae_after_entry_pct"),
        "avg_mae_after_entry_pct": _mean_or_na(base, "mae_after_entry_pct"),
    }
    return _append_total_row(base, total_values, TRADE_TOTAL_COLUMNS)


def append_account_total_row(df: pd.DataFrame, initial_equity_usd: float | None = None) -> pd.DataFrame:
    """Return a display copy with account-level totals appended at the bottom."""
    base = _base_rows(df)
    if base.empty:
        return df.copy()

    total_net_pnl = _sum_or_na(base, "net_pnl_usd")
    total_costs = _sum_or_na(base, "costs_usd")
    final_equity = _last_or_na(base, "equity_after_usd")
    total_values = {
        "row_type": "TOTAL",
        "symbol": "TOTAL",
        "total_trades": int(len(base)),
        "total_net_pnl_usd": total_net_pnl,
        "total_costs_usd": total_costs,
        "final_equity_usd": final_equity,
        "total_return_pct": _total_return_pct(base, initial_equity_usd),
        "avg_account_return_pct": _mean_or_na(base, "account_return_pct"),
        "net_pnl_usd": total_net_pnl,
        "costs_usd": total_costs,
        "equity_after_usd": final_equity,
    }
    return _append_total_row(base, total_values, ACCOUNT_TOTAL_COLUMNS)
