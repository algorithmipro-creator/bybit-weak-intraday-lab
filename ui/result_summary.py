from __future__ import annotations

import pandas as pd


def _mean_or_zero(df: pd.DataFrame, column: str) -> float:
    if df.empty or column not in df.columns:
        return 0.0
    value = df[column].mean()
    return 0.0 if pd.isna(value) else float(value)


def _median_or_zero(df: pd.DataFrame, column: str) -> float:
    if df.empty or column not in df.columns:
        return 0.0
    value = df[column].median()
    return 0.0 if pd.isna(value) else float(value)


def trade_result_summary(trades: pd.DataFrame) -> dict[str, float]:
    if trades.empty:
        return {
            "trades": 0,
            "tp_rate_pct": 0.0,
            "sl_rate_pct": 0.0,
            "avg_pnl_pct": 0.0,
            "median_pnl_pct": 0.0,
            "avg_mfe_pct": 0.0,
            "avg_mae_pct": 0.0,
        }

    outcomes = trades["outcome"].astype(str) if "outcome" in trades.columns else pd.Series(dtype=str)
    count = int(len(trades))
    return {
        "trades": count,
        "tp_rate_pct": float((outcomes == "tp").sum() / count * 100),
        "sl_rate_pct": float((outcomes == "sl").sum() / count * 100),
        "avg_pnl_pct": _mean_or_zero(trades, "pnl_underlying_pct"),
        "median_pnl_pct": _median_or_zero(trades, "pnl_underlying_pct"),
        "avg_mfe_pct": _mean_or_zero(trades, "mfe_after_entry_pct"),
        "avg_mae_pct": _mean_or_zero(trades, "mae_after_entry_pct"),
    }


def best_grid_result(grid: pd.DataFrame) -> dict[str, float] | None:
    if grid.empty:
        return None
    usable = grid.copy()
    if "trades" in usable.columns:
        usable = usable[usable["trades"].fillna(0) > 0]
    if "avg_underlying_pnl" in usable.columns:
        usable = usable[usable["avg_underlying_pnl"].notna()]
    if usable.empty:
        return None
    ranked = usable.sort_values(["avg_underlying_pnl", "tp_rate", "trades"], ascending=[False, False, False])
    return ranked.iloc[0].to_dict()
