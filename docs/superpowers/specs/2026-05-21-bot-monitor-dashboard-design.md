# Bot Monitor Dashboard Design

## Goal

Build a clear first-screen monitoring interface for the Bybit Weak Intraday Lab. The user should be able to open Streamlit and immediately understand whether the demo connection works, what the account state is, what positions and orders are open, what PnL/risk is visible, and what coins the scanner is currently surfacing.

This is a monitoring and research UX increment. It does not add automatic signal execution, mainnet trading, position closing, or larger order controls.

## Chosen Direction

Use the selected `Executive Overview` layout.

The top of the Streamlit app becomes a `Bot Monitor` section with:

1. Connection and safety status.
2. Account summary metrics.
3. Open positions and scanner watchlist side by side.
4. Open orders and execution history below.
5. Existing `Jobs` section kept below as a technical archive.

The layout should be easy to show to another person without explaining raw Bybit payloads.

## In Scope

1. Add a readable `Bot Monitor` block near the top of `ui/streamlit_app.py`.
2. Normalize Bybit Demo wallet, positions, and open-orders payloads into user-facing tables.
3. Show connection status:
   - backend reachable;
   - execution mode;
   - execution enabled;
   - API keys configured;
   - execution token configured;
   - Bybit Demo base URL;
   - safety limits.
4. Show account metrics when the sidebar execution token is provided:
   - equity;
   - wallet balance;
   - available balance;
   - margin used;
   - unrealized PnL;
   - open positions count;
   - open orders count.
5. Show open positions with readable columns:
   - symbol;
   - side;
   - size;
   - average entry;
   - mark price;
   - unrealized PnL;
   - PnL percentage when it can be derived;
   - leverage;
   - position margin or initial margin;
   - liquidation price;
   - take profit;
   - stop loss.
6. Show open orders with readable columns:
   - symbol;
   - side;
   - order type;
   - quantity;
   - price;
   - trigger price;
   - take profit / stop loss hints when present;
   - order status;
   - created time.
7. Add a protected backend endpoint for recent execution journal rows:
   - `GET /execution/demo/journal`
   - same `X-BWI-Execution-Token` protection as wallet/positions/orders;
   - returns recent local journal rows only;
   - never returns API keys, secrets, or the execution token.
8. Show execution history from the local journal:
   - created time;
   - symbol;
   - side;
   - requested notional;
   - quantity;
   - TP;
   - SL;
   - status;
   - reason;
   - Bybit retCode/retMsg.
9. Show scanner watchlist from the latest finished scan job:
   - prefer latest `causal_scan`;
   - fall back to latest regular `scan`;
   - show symbol, mode, score, signal or entry time, turnover, price, and evaluation/outcome when available.
10. Keep existing scan/job controls working.

## Out Of Scope

1. Auto-entry from scanner signals.
2. Mainnet order placement.
3. Closing positions from the UI.
4. Cancelling orders from the UI.
5. Modifying leverage or margin mode.
6. New trading strategy logic.
7. A separate React frontend.

## Data Flow

The Streamlit app reads:

```text
GET /health
GET /execution/demo/status
GET /execution/demo/wallet
GET /execution/demo/positions
GET /execution/demo/open-orders
GET /execution/demo/journal
GET /jobs
GET /jobs/{job_id}/signals.csv
GET /jobs/{job_id}/evaluations.csv
GET /jobs/{job_id}/trades.csv
GET /jobs/{job_id}/metrics.csv
```

The wallet, positions, orders, and journal endpoints require the execution token except for `/execution/demo/status`. If the token is missing, the monitor still shows configuration status and explains that account data is locked.

## UI Structure

### Bot Monitor Header

Show compact status pills and metrics:

```text
Backend: OK/Error
Mode: demo/disabled
Execution: enabled/disabled
Keys: configured/missing
Token: configured/missing
Bybit URL: https://api-demo.bybit.com
```

### Account Summary

Show a single row of metrics:

```text
Equity
Wallet Balance
Available
Margin Used
Unrealized PnL
Open Positions
Open Orders
Scanner Signals
```

If a value is missing from Bybit, display `n/a` instead of failing the page.

### Main Overview

Left side: `Open Positions`.

Right side: `Scanner Watchlist`.

This is the main working area. It should answer two questions quickly:

```text
What is currently open?
What is the bot watching?
```

### Secondary Overview

Below the main area:

```text
Open Orders
Execution History
```

These sections are still visible, but less dominant than account status and positions.

### Existing Jobs

The old jobs table remains below the monitor. It keeps scan launching, result tables, charts, and CSV downloads intact.

## Normalization Rules

Parsing should be defensive because Bybit fields may be empty strings.

Numeric helpers should:

1. accept strings, numbers, empty strings, and missing values;
2. return `None` for unparseable values;
3. format money and percentages consistently;
4. avoid throwing inside Streamlit render paths.

Position PnL percentage:

```text
unrealized_pnl / position_value
```

Use this only when both values are available and position value is non-zero.

Margin used:

1. prefer account payload fields when available;
2. otherwise sum position margin or initial margin from open positions;
3. otherwise show `n/a`.

TP/SL:

1. show direct position fields if Bybit returns them;
2. if absent, infer visible TP/SL from open trigger orders by symbol when possible;
3. otherwise show `n/a`.

## Error Handling

The monitor should degrade section by section.

If backend is unavailable, show a clear backend error and keep the sidebar visible.

If status works but token is missing, show public status and lock account sections.

If wallet fails but positions work, show positions and mark wallet unavailable.

If one CSV result file is missing for the latest scanner job, show the available scanner data and a small warning.

No error message may include API keys, API secrets, or the execution token.

## Backend Change

Add one read-only execution endpoint:

```text
GET /execution/demo/journal?limit=50
```

Behavior:

1. require `X-BWI-Execution-Token`;
2. validate demo read config in the same way as wallet/positions/orders;
3. read `execution_journal_path`;
4. return the newest rows first;
5. clamp `limit` between 1 and 500;
6. return structured JSON:

```json
{
  "rows": [],
  "limit": 50,
  "count": 0
}
```

This endpoint only reads local journal data. It does not call Bybit and does not mutate files.

## Tests

Backend tests:

1. journal endpoint rejects missing token;
2. journal endpoint rejects invalid token;
3. journal endpoint returns recent rows newest first;
4. journal endpoint clamps limit;
5. journal endpoint does not expose secrets.

UI helper tests:

1. wallet summary extraction handles normal Bybit payloads;
2. wallet summary extraction handles missing fields;
3. open positions normalization derives PnL percentage;
4. open orders normalization keeps trigger prices and statuses;
5. scanner watchlist chooses latest causal scan before regular scan;
6. scanner watchlist falls back to regular scan when no causal scan exists;
7. token redaction still works in monitor errors.

Source-order test:

1. `Bot Monitor` renders before the `Jobs` section.

## Rollout

1. Add tests for journal endpoint and UI normalization helpers.
2. Add the journal endpoint.
3. Extract UI normalization helpers in `ui/streamlit_app.py` or a small `ui/bot_monitor.py` module if the Streamlit file becomes too large.
4. Render `Bot Monitor` above `Jobs`.
5. Keep the existing demo test-short form accessible, but visually secondary.
6. Run the test suite.
7. Restart backend and Streamlit locally.

## Success Criteria

The increment is complete when:

1. the first screen shows connection, account, positions, orders, history, and scanner watchlist in readable form;
2. raw Bybit payload tables are no longer the primary account view;
3. missing token or missing data does not break the page;
4. the existing scan and demo test-short flows still work;
5. all tests pass;
6. no secrets are exposed in UI errors, API responses, logs, or git.
