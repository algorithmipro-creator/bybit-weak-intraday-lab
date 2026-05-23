# Signal Decision Layer and Demo Auto-Entry Design

Date: 2026-05-22

## Purpose

The project now has a stable scanner lifecycle, demo account monitor, and a guarded manual demo short endpoint. The next step is a decision layer between scanner candidates and demo execution.

This feature turns scanner output into explicit decisions, optionally sends safe demo orders, records every decision, and sends Telegram notifications. It remains demo-only. Telegram is outbound notifications only; it does not control the bot.

## Current State

- Scanner jobs produce `metrics.csv`, `trades.csv`, `signals.csv`, `evaluations.csv`, and progress metadata.
- `ui.bot_monitor.build_scanner_watchlist()` can normalize recent scan/causal results into candidate rows.
- Demo execution already has guarded routes under `/execution/demo`.
- `POST /execution/demo/place-test-short` validates mode, token, demo base URL, symbol whitelist, max notional, open position count, daily test order count, instrument rules, TP/SL, and journals order lifecycle rows.
- `Execution History` shows the execution journal.
- There is no formal decision journal explaining why a candidate was accepted, rejected, skipped, or entered.
- There is no Telegram notification layer.

## Goals

1. Add a deterministic Signal Decision Layer for latest scanner candidates.
2. Add demo auto-entry v1 that can place guarded demo short orders for qualified candidates.
3. Record every decision in a dedicated decision journal.
4. Send Telegram notifications for decisions and demo order outcomes.
5. Keep Telegram outbound-only.
6. Keep live trading disabled and out of scope.
7. Expose backend API endpoints and a Streamlit page for decisions.

## Non-Goals

- No live order execution.
- No Telegram commands such as `/pause`, `/resume`, `/status`, or order approval.
- No scheduler loop in this step.
- No long-running autonomous bot daemon in this step.
- No new database; use CSV journals for MVP consistency.
- No strategy-rule changes inside scanner scoring.

## Chosen Approach

Build a small, explicit layer:

```text
Scanner result
  -> latest candidates
  -> Signal Decision Layer
  -> risk and safety checks
  -> decision journal
  -> optional demo order
  -> execution journal
  -> Telegram notification
  -> UI
```

This keeps the execution path auditable. The system can explain not only "an order was sent", but also "why this signal was accepted or rejected".

## Decision Model

Each candidate is converted into one decision row.

Decision statuses:

- `qualified`: candidate passed decision checks, but no order was sent.
- `rejected`: candidate failed a hard rule.
- `entered`: demo order was sent.
- `skipped`: candidate was valid but intentionally not used, for example because one entry was already sent during this run.
- `error`: an unexpected decision, order, or notification error occurred.

Decision reasons:

- `qualified`
- `score_below_threshold`
- `symbol_not_whitelisted`
- `max_open_positions_reached`
- `execution_disabled`
- `execution_mode_not_demo`
- `missing_demo_keys`
- `daily_limit_reached`
- `cooldown_active`
- `notional_limit_exceeded`
- `candidate_missing_price`
- `no_scanner_candidates`
- `auto_entry_disabled`
- `dry_run`
- `already_entered_this_run`
- `order_sent`
- `order_rejected`
- `bybit_api_error`
- `bybit_transport_error`
- `telegram_disabled`
- `telegram_sent`
- `telegram_error`

The first MVP should keep the rule set intentionally small:

- supported side: short/sell only;
- candidate symbol must be in `execution_symbol_whitelist`;
- score must be at least `BWI_SIGNAL_MIN_SCORE`;
- execution mode must be `demo`;
- execution must be enabled;
- demo keys must be configured;
- notional must be at or below `max_demo_notional_usdt`;
- open position count must be below `max_open_positions`;
- daily test order count must be below `max_daily_test_orders`;
- optional cooldown per symbol prevents repeated entries too close together.

## Settings

Add settings with `BWI_` prefix:

```env
BWI_SIGNAL_MIN_SCORE=9
BWI_SIGNAL_AUTO_ENTRY_ENABLED=false
BWI_SIGNAL_DEFAULT_NOTIONAL_USDT=25
BWI_SIGNAL_TAKE_PROFIT_PCT=0.06
BWI_SIGNAL_STOP_LOSS_PCT=0.07
BWI_SIGNAL_COOLDOWN_MINUTES=60
BWI_SIGNAL_DECISION_JOURNAL_PATH=data/signal_decisions.csv

BWI_TELEGRAM_ENABLED=false
BWI_TELEGRAM_BOT_TOKEN=
BWI_TELEGRAM_CHAT_ID=
```

The Telegram token must never be printed, returned from status endpoints, written to journals, or shown in Streamlit.

## Decision Journal

Use a dedicated CSV:

```text
data/signal_decisions.csv
```

Columns:

```text
created_at_utc
decision_id
job_id
job_type
symbol
mode
score
status
reason
side
notional_usdt
take_profit_pct
stop_loss_pct
candidate_price
candidate_time_utc
order_link_id
execution_status
telegram_status
telegram_error
details
```

Rules:

- Append-only.
- Stable header.
- Read functions tolerate missing, empty, malformed, or old-column files.
- Decision journal is separate from execution journal.
- If demo order is sent, store `order_link_id` and execution status.
- Store concise details, not raw Bybit responses and not secrets.

## Backend API

Add routes under a new router, likely `backend/app/signal_routes.py`.

Endpoints:

```text
GET  /signals/decisions?limit=100
POST /signals/evaluate-latest
POST /signals/demo-auto-entry
GET  /signals/telegram/status
POST /signals/telegram/test
```

Authentication:

- Read-only `/signals/decisions` can follow the same project-local pattern as current job endpoints.
- `demo-auto-entry` and `telegram/test` must require `X-BWI-Execution-Token`.
- `evaluate-latest` should require the token if it can trigger Telegram notifications, because notifications can leak trading state outside the local machine.

### `POST /signals/evaluate-latest`

Purpose: evaluate latest scanner candidates, write decision rows, and optionally send Telegram decision notifications. It does not place orders.

Input MVP:

```json
{
  "max_candidates": 20,
  "notify": true
}
```

Output:

```json
{
  "status": "evaluated",
  "count": 3,
  "decisions": [
    {
      "decision_id": "...",
      "symbol": "ENAUSDT",
      "status": "qualified",
      "reason": "qualified",
      "telegram_status": "sent"
    }
  ]
}
```

### `POST /signals/demo-auto-entry`

Purpose: evaluate latest candidates and send at most one demo order for the first qualified candidate.

Input MVP:

```json
{
  "max_candidates": 20,
  "notify": true,
  "dry_run": false
}
```

Rules:

- Requires execution token.
- Requires `BWI_SIGNAL_AUTO_ENTRY_ENABLED=true`.
- Still requires existing `BWI_EXECUTION_ENABLED=true`.
- Places at most one order per request.
- Uses existing demo execution safety logic instead of duplicating order placement rules.
- If `dry_run=true`, write decisions but do not call Bybit.

Output:

```json
{
  "status": "entered",
  "decision_id": "...",
  "symbol": "ENAUSDT",
  "order_link_id": "bwi-demo-...",
  "telegram_status": "sent"
}
```

### Telegram Endpoints

`GET /signals/telegram/status` returns:

```json
{
  "enabled": true,
  "bot_token_configured": true,
  "chat_id_configured": true
}
```

It never returns the token or chat id.

`POST /signals/telegram/test` sends a small test message and requires `X-BWI-Execution-Token`.

## Telegram Notification Layer

Create a small notifier module, for example:

```text
bybit_weak_intraday/notifications/telegram.py
```

Responsibilities:

- Validate configured/enabled status.
- Send text messages through Telegram Bot API.
- Return structured result: `sent`, `disabled`, `not_configured`, or `error`.
- Apply request timeout.
- Never raise token-containing errors to API responses or journals.

Message types:

- Signal qualified.
- Signal rejected.
- Demo order sent.
- Demo order rejected/error.
- Bot warning.

Example messages:

```text
Signal qualified
ENAUSDT | weak | score 10
Reason: qualified
Notional: $25.00 | TP: 6.00% | SL: 7.00%
```

```text
Demo order sent
ENAUSDT Sell
Notional: $25.00
TP: 0.09814 | SL: 0.11172
Decision: abc123
```

```text
Signal rejected
JTOUSDT | pump | score 9
Reason: max_open_positions_reached
```

## Demo Order Integration

The auto-entry layer should reuse existing execution safety code.

Preferred implementation shape:

- Extract the core of `place_test_short()` into a reusable function that receives a validated request and returns a structured result.
- Keep the existing endpoint behavior unchanged.
- New signal auto-entry route calls the reusable function under the same `_ORDER_LOCK`.

This avoids a second, inconsistent execution path.

The decision layer must not bypass:

- execution token;
- demo mode;
- demo base URL;
- API key presence;
- symbol whitelist;
- max notional;
- max open positions;
- daily order count;
- instrument quantity/price rules;
- TP/SL calculation;
- execution journal append.

## UI Design

Add a new menu item:

```text
Signal Decisions
```

It should show:

- Latest scanner candidates.
- Decision table.
- Status and reason.
- Order link id when present.
- Telegram status.
- Buttons:
  - `Evaluate latest`
  - `Demo auto-entry`
  - `Dry-run auto-entry`

`Settings` should show Telegram configuration status:

```text
Telegram
Enabled: yes/no
Bot token: configured/not configured
Chat ID: configured/not configured
[Send test message]
```

The Monitor page should remain focused on live account state and should not become a decision report page.

## Data Flow

Evaluate latest:

```text
UI -> POST /signals/evaluate-latest
Backend -> latest completed scanner job
Backend -> normalized candidates
Backend -> decision rules
Backend -> decision journal
Backend -> Telegram notification, if enabled/requested
UI <- decision rows
```

Demo auto-entry:

```text
UI -> POST /signals/demo-auto-entry
Backend -> execution token check
Backend -> latest completed scanner job
Backend -> decision rules
Backend -> first qualified candidate
Backend -> existing demo order safety path
Backend -> decision journal + execution journal
Backend -> Telegram notification
UI <- entered/rejected/skipped result
```

## Error Handling

- Missing scanner results: return a user-facing `no_scanner_candidates` result, not a server crash.
- Telegram disabled: record `telegram_status=disabled`, do not fail decision.
- Telegram network error: record `telegram_status=error`, keep decision/order result.
- Bybit API error: record decision `error` or `rejected` with `bybit_api_error`, notify if possible, and keep existing execution journal behavior.
- Malformed decision journal: read as empty, preserve stable output columns.
- Missing execution token: reject protected routes before any order or Telegram side effect.

## Security and Safety

- All order-producing routes require `X-BWI-Execution-Token`.
- Telegram test and notification-triggering routes require the token.
- Telegram token and chat id are never returned or logged.
- Demo auto-entry is gated by both `BWI_SIGNAL_AUTO_ENTRY_ENABLED` and existing execution enablement.
- The feature remains demo-only.
- At most one demo order is sent per auto-entry request.
- Default auto-entry is disabled.

## Testing

Unit and API tests should cover:

- Decision journal append/read/empty/malformed behavior.
- Decision rules for qualified, score below threshold, whitelist reject, execution disabled, max positions, daily limit, cooldown.
- Telegram notifier disabled/not configured/sent/error without exposing token.
- Telegram status endpoint redacts token/chat id.
- Telegram test endpoint requires execution token.
- Evaluate-latest writes decisions and optionally sends notifications.
- Demo auto-entry rejects when disabled.
- Demo auto-entry dry run writes decisions and sends no order.
- Demo auto-entry sends at most one order.
- Existing `place-test-short` endpoint behavior remains unchanged.
- Streamlit source-level tests for new page/menu/settings controls.
- Full test suite remains green.

## Rollout

1. Implement decision journal.
2. Implement Telegram notifier.
3. Extract reusable demo short placement function without changing existing endpoint behavior.
4. Implement decision engine.
5. Add backend signal routes.
6. Add Streamlit `Signal Decisions` page and Telegram settings status.
7. Verify with tests.
8. Manually test Telegram with `BWI_TELEGRAM_ENABLED=true` only after user configures token/chat id.

## Open Decisions Resolved

- Telegram v1 is notifications only.
- Auto-entry v1 is demo-only.
- No scheduler loop in this step.
- No Telegram command handling in this step.
- Decision journal is separate from execution journal.
- Existing execution safety checks remain authoritative.
