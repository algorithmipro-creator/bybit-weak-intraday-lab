from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

ACCOUNT_CURVE_COLUMNS = [
    "date",
    "symbol",
    "mode",
    "outcome",
    "entry_time_utc",
    "exit_time_utc",
    "pnl_underlying_pct",
    "equity_before_usd",
    "margin_allocated_usd",
    "notional_usd",
    "gross_pnl_usd",
    "costs_usd",
    "net_pnl_usd",
    "equity_after_usd",
    "account_return_pct",
    "drawdown_pct",
]


@dataclass(frozen=True)
class AccountBacktestSettings:
    initial_equity_usd: float = 10_000.0
    position_size_pct: float = 10.0
    leverage: float = 1.0
    entry_fee_pct: float = 0.06
    exit_fee_pct: float = 0.06
    slippage_pct: float = 0.0
    funding_pct: float = 0.0


def validate_account_backtest_settings(settings: AccountBacktestSettings) -> None:
    if settings.initial_equity_usd <= 0:
        raise ValueError("initial_equity_usd must be positive")
    if not 0 < settings.position_size_pct <= 100:
        raise ValueError("position_size_pct must be between 0 and 100")
    if settings.leverage <= 0:
        raise ValueError("leverage must be positive")
    for name in ("entry_fee_pct", "exit_fee_pct", "slippage_pct", "funding_pct"):
        if getattr(settings, name) < 0:
            raise ValueError(f"{name} must be non-negative")


def _empty_summary(settings: AccountBacktestSettings, skipped_trades: int = 0) -> dict[str, float]:
    return {
        "trades": 0,
        "skipped_trades": int(skipped_trades),
        "initial_equity_usd": float(settings.initial_equity_usd),
        "final_equity_usd": float(settings.initial_equity_usd),
        "net_pnl_usd": 0.0,
        "total_return_pct": 0.0,
        "max_drawdown_pct": 0.0,
        "win_rate_pct": 0.0,
        "gross_pnl_usd": 0.0,
        "costs_usd": 0.0,
    }


def _get(row: pd.Series, key: str) -> Any:
    return row[key] if key in row.index else None


def _datetime_series(df: pd.DataFrame, column: str) -> pd.Series:
    if column not in df.columns:
        return pd.Series(pd.NaT, index=df.index)
    return pd.to_datetime(df[column], errors="coerce", utc=True)


def _sorted_valid_trades(trades: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    if trades.empty or "pnl_underlying_pct" not in trades.columns:
        return pd.DataFrame(), int(len(trades))

    work = trades.copy()
    work["pnl_underlying_pct"] = pd.to_numeric(work["pnl_underlying_pct"], errors="coerce")
    skipped = int(work["pnl_underlying_pct"].isna().sum())
    work = work.dropna(subset=["pnl_underlying_pct"]).copy()
    if work.empty:
        return work, skipped

    exit_ts = _datetime_series(work, "exit_time_utc")
    entry_ts = _datetime_series(work, "entry_time_utc")
    work["_sort_time"] = exit_ts.fillna(entry_ts)
    work["_sort_pos"] = range(len(work))
    return work.sort_values(["_sort_time", "_sort_pos"], na_position="last").drop(columns=["_sort_time", "_sort_pos"]), skipped


def run_account_backtest(trades: pd.DataFrame, settings: AccountBacktestSettings) -> tuple[dict[str, float], pd.DataFrame]:
    validate_account_backtest_settings(settings)
    valid, skipped = _sorted_valid_trades(trades)
    if valid.empty:
        return _empty_summary(settings, skipped), pd.DataFrame(columns=ACCOUNT_CURVE_COLUMNS)

    equity = float(settings.initial_equity_usd)
    peak_equity = equity
    rows: list[dict[str, Any]] = []
    cost_rate = settings.entry_fee_pct + settings.exit_fee_pct + settings.slippage_pct + settings.funding_pct

    for _, row in valid.iterrows():
        equity_before = equity
        margin_allocated = equity_before * settings.position_size_pct / 100
        notional = margin_allocated * settings.leverage
        pnl_underlying_pct = float(row["pnl_underlying_pct"])
        gross_pnl = notional * pnl_underlying_pct / 100
        costs = notional * cost_rate / 100
        net_pnl = gross_pnl - costs
        equity = equity_before + net_pnl
        peak_equity = max(peak_equity, equity)
        drawdown = 0.0 if peak_equity == 0 else max(0.0, (peak_equity - equity) / peak_equity * 100)
        account_return_pct = net_pnl / equity_before * 100

        rows.append(
            {
                "date": _get(row, "date"),
                "symbol": _get(row, "symbol"),
                "mode": _get(row, "mode"),
                "outcome": _get(row, "outcome"),
                "entry_time_utc": _get(row, "entry_time_utc"),
                "exit_time_utc": _get(row, "exit_time_utc"),
                "pnl_underlying_pct": pnl_underlying_pct,
                "equity_before_usd": float(equity_before),
                "margin_allocated_usd": float(margin_allocated),
                "notional_usd": float(notional),
                "gross_pnl_usd": float(gross_pnl),
                "costs_usd": float(costs),
                "net_pnl_usd": float(net_pnl),
                "equity_after_usd": float(equity),
                "account_return_pct": float(account_return_pct),
                "drawdown_pct": float(drawdown),
            }
        )

    curve = pd.DataFrame(rows, columns=ACCOUNT_CURVE_COLUMNS)
    wins = int((curve["net_pnl_usd"] > 0).sum())
    count = int(len(curve))
    final_equity = float(curve["equity_after_usd"].iloc[-1])
    summary = {
        "trades": count,
        "skipped_trades": int(skipped),
        "initial_equity_usd": float(settings.initial_equity_usd),
        "final_equity_usd": final_equity,
        "net_pnl_usd": final_equity - float(settings.initial_equity_usd),
        "total_return_pct": (final_equity / float(settings.initial_equity_usd) - 1) * 100,
        "max_drawdown_pct": float(curve["drawdown_pct"].max()),
        "win_rate_pct": float(wins / count * 100) if count else 0.0,
        "gross_pnl_usd": float(curve["gross_pnl_usd"].sum()),
        "costs_usd": float(curve["costs_usd"].sum()),
    }
    return summary, curve
