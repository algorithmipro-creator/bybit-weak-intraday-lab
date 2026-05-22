# Clean Monitor Navigation Design

## Goal

Replace the overloaded Streamlit first screen with a simpler app flow:

1. Start on a connection screen.
2. After connection, show only the Bot Monitor as the main screen.
3. Move reports, scanner jobs, execution history details, and settings into separate menu sections.

The main monitor should answer one question quickly: is the demo bot connected, what is the account/position risk, and what is the scanner watching now?

## Chosen Direction

Use the selected Variant 3:

```text
Start / Connect screen -> Clean Bot Monitor -> Secondary menus
```

The execution token and backend URL are entered on the start screen or Settings. They should not stay as always-visible sidebar controls during monitoring.

## Primary User Flow

### 1. Start Screen

The app opens with a focused connection page:

```text
Bybit Demo Connection

Backend API URL
Execution API token

[Connect]
```

After a successful connection check, the app stores only session-local connection state and moves to the monitor.

The start screen may show minimal status feedback:

```text
Backend online/offline
Demo mode demo/disabled
Keys configured/missing
Token accepted/missing/invalid
```

No wallet tables, scanner tables, job launch controls, or reports appear on this screen.

### 2. Bot Monitor

The monitor is the default post-login screen. It keeps only the core live state:

```text
Bot Monitor
Demo account control room: connection, account risk, active position state, and scanner candidates.

DEMO CONNECTED

Backend online
Mode demo
Execution enabled
Keys configured
Token entered
Positions 1
Orders 2
Max notional $25.00

Equity
$179,040.57
Wallet $99,934.15 | Available $99,933.15

Unreal PnL
$-0.00

Margin
$1.00
Positions 1 | Orders 2

Signals
0 waiting

Open Positions
ENAUSDT
Sell 95
Entry 0.10441
Mark 0.10442
PnL $-0.00 (-0.01%)
Lev 10x
TP 0.09814
SL 0.11172

Scanner Watchlist
No scanner candidates yet.

Position PnL
Scanner Scores
```

This screen should be larger and quieter than the current PR version:

- no Jobs table;
- no scan launch controls;
- no raw execution history table;
- no API token input;
- no constantly open configuration sidebar;
- no report/backtest panels.

Detailed tables can remain available, but they must not compete with the monitor on the first screen.

### 3. Secondary Menu

Use a compact menu after connection:

```text
Monitor
Reports
Scanner Jobs
Execution History
Settings
```

Menu behavior:

- `Monitor`: clean live dashboard only.
- `Reports`: backtest summaries, TP/SL optimizer results, account backtest reports, charts.
- `Scanner Jobs`: scan launch forms, active jobs table, CSV downloads, job result details.
- `Execution History`: local journal table, order attempts, rejected/sent events, filters.
- `Settings`: backend URL, execution token, refresh behavior, safety/config status.

The menu can be a compact top segmented control or a collapsed sidebar. It should not keep all forms visible at once.

## Layout Rules

### Monitor

The monitor should use large visual blocks:

1. Header/status block.
2. Account/risk KPI row.
3. Open position card.
4. Scanner watchlist card.
5. Two small charts: Position PnL and Scanner Scores.

The monitor may show empty states, but they should be quiet:

```text
No open demo positions.
No scanner candidates yet.
No score chart yet.
```

### Reports

Reports can use tables and charts because this is analysis mode, not live monitoring.

Reports include:

- trade result summaries;
- account backtest;
- TP/SL optimizer;
- MFE/MAE charts;
- historical scan result details.

### Scanner Jobs

Scanner Jobs contains operational controls:

- job type;
- date range;
- symbol list;
- thresholds;
- start job button;
- active/completed jobs table;
- CSV downloads.

This content should not appear on the Monitor screen.

### Execution History

Execution History contains the local journal table and filters.

The Monitor can show only a small status/count if needed, but not the full journal table.

### Settings

Settings owns connection inputs:

- backend API URL;
- execution token;
- auto-refresh toggle;
- display of safety config;
- optional reconnect/disconnect buttons.

The start screen and Settings may share the same connection helper logic.

## State Rules

Use Streamlit session state for:

- backend API URL;
- execution token;
- connection status;
- selected menu page;
- whether the user has completed the connection screen.

The execution token must remain local to the Streamlit session. It must not be logged, written to files, shown in the UI, or sent to endpoints that do not need it.

## Data Rules

The Monitor reads:

```text
GET /health
GET /execution/demo/status
GET /execution/demo/wallet
GET /execution/demo/positions
GET /execution/demo/open-orders
GET /jobs
GET /jobs/{job_id}/signals.csv
GET /jobs/{job_id}/evaluations.csv
GET /jobs/{job_id}/trades.csv
```

Execution History reads:

```text
GET /execution/demo/journal
```

Scanner Jobs reads/writes the existing scan job endpoints.

Reports read existing job result CSV endpoints.

## Error Handling

The connection screen should block progression when:

- backend is unreachable;
- execution status cannot be read;
- token is missing or invalid for private account data.

The Monitor should degrade section-by-section after connection:

- if wallet fails, still show positions/scanner if available;
- if scanner job files are missing, show no scanner candidates;
- if positions are empty, show a clear empty state;
- never show raw exception text containing the execution token.

## Test Requirements

Add tests that prove:

1. The default app flow renders a connection/start path before monitor content.
2. The Monitor page does not contain Jobs controls or scan launch controls.
3. Connection inputs are not rendered inside the Monitor page.
4. The menu includes Monitor, Reports, Scanner Jobs, Execution History, and Settings.
5. Token redaction still works for all connection and account errors.
6. Existing backend/job/report behavior remains available in secondary pages.

## Out Of Scope

- Mainnet/live execution.
- Auto-entry from scanner signals.
- Closing positions.
- Cancelling orders.
- Leverage or margin mode changes.
- Replacing Streamlit with React.

## Success Criteria

The redesign is complete when:

1. opening the app first shows a connection screen;
2. after connecting, the first screen is only Bot Monitor;
3. the monitor visually matches the simplified content listed above;
4. jobs/reports/history/settings are accessible but hidden from the monitor;
5. token/API URL controls are not always visible;
6. all tests pass;
7. PR screenshots/manual review confirm the screen is visibly simpler than the current PR version.
