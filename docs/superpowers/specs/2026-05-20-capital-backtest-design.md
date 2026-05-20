# Capital Backtest Design

## Purpose

The current dashboard reports `pnl_underlying_pct`, which is the price move captured by each hypothetical short trade. That is useful for signal quality, but it is not account return. The next feature adds a simple account-level backtest layer on top of completed `trades.csv` results so the dashboard can answer: "What would this have done to an account under fixed assumptions?"

This remains research-only. It does not place orders, store exchange keys, or imply live readiness.

## Approaches Considered

### Recommended: Fixed-Fraction Account Backtest

Each signal uses a fixed percentage of current equity as margin allocation. Notional equals allocation multiplied by leverage. Trade PnL is derived from `pnl_underlying_pct`, fees are subtracted from entry and exit notional, and account equity updates when the trade closes.

This is the first implementation because it is easy to explain, deterministic, and directly connects existing scan output to account-level metrics.

### Alternative: Full Portfolio Simulator

Track overlapping positions, reserved margin, liquidation thresholds, funding payments by timestamp, and notional limits. This is closer to real trading, but too large for the next increment and needs more exchange-specific assumptions.

### Alternative: Summary-Only Estimator

Compute account return as `average trade pnl * position size * trade count`. This is quick but hides timing, drawdown, overlapping trades, and per-trade fee effects. It is useful as a mental model, not as dashboard output.

## Selected MVP

Add a fixed-fraction capital model that runs client-side in the Streamlit dashboard first, using completed scan job `trades.csv` files. This avoids changing scan output format and keeps the first version focused on interpretation.

Default assumptions:

```text
initial_equity_usd = 10,000
position_size_pct = 10
leverage = 1
entry_fee_pct = 0.06
exit_fee_pct = 0.06
slippage_pct = 0
funding_pct = 0
```

All fee/slippage/funding settings are percentages of notional unless explicitly named otherwise.

## Calculation

For each completed trade, sorted by `exit_time_utc` with `entry_time_utc` as a fallback:

```text
margin_allocated = equity_before * position_size_pct / 100
notional = margin_allocated * leverage
gross_pnl_usd = notional * pnl_underlying_pct / 100
costs_usd = notional * (entry_fee_pct + exit_fee_pct + slippage_pct + funding_pct) / 100
net_pnl_usd = gross_pnl_usd - costs_usd
equity_after = equity_before + net_pnl_usd
account_return_pct = net_pnl_usd / equity_before * 100
```

Rows without numeric `pnl_underlying_pct` are excluded from account calculations and counted as skipped.

The MVP does not reserve margin during open positions. It treats each trade as sequential at close time. This is an intentional simplification and must be labeled as such in UI.

## Dashboard Changes

For completed archive scan jobs, add a new "Account Backtest" section near the result overview.

Controls:

```text
Initial equity USD
Position size %
Leverage
Entry fee %
Exit fee %
Slippage %
Funding %
```

Displayed metrics:

```text
Final equity
Total return %
Net PnL USD
Max drawdown %
Account win rate %
Skipped trades
```

Charts:

```text
Equity curve by exit time
Per-trade account PnL bar chart
```

Table:

```text
symbol
date
mode
outcome
entry_time_utc
exit_time_utc
pnl_underlying_pct
gross_pnl_usd
costs_usd
net_pnl_usd
equity_after
account_return_pct
```

## Components

Add a small pure helper module under `ui/` first:

```text
ui/account_backtest.py
```

Expected public functions:

```text
run_account_backtest(trades, settings) -> (summary, equity_curve)
```

The helper should be deterministic, pandas-based, and covered by unit tests. Streamlit should only render controls and charts, not contain calculation logic.

## Error Handling

If `trades.csv` is empty, show a neutral message and zeroed account metrics.

If all trades have missing PnL, show skipped-trades count and do not draw a misleading equity curve.

If settings are invalid, clamp or block in the UI:

```text
initial_equity_usd > 0
0 < position_size_pct <= 100
leverage > 0
fee/slippage/funding settings >= 0
```

## Testing

Add unit tests for:

```text
single winning trade after fees
compounded multi-trade sequence
max drawdown after a losing trade
missing PnL rows counted as skipped
empty trades frame returns stable zero-result summary
```

Run the full project test suite after implementation:

```text
python -m pytest -q
```

## Non-Goals

This feature will not add:

```text
live trading
paper order placement
exchange API keys
margin reservation for overlapping trades
liquidation modeling
dynamic funding from Bybit
order-book slippage
```

Those can be added later after the research dashboard clearly separates underlying signal performance from account-level assumptions.
