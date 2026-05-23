# Bot Monitor Signal Decisions Design

Date: 2026-05-23

## Goal

Make the main Bot Monitor show what the algorithm is deciding, not only what the account and scanner currently show.

The monitor should answer four questions at a glance:

- Is the demo connection alive?
- What is the account and open position state?
- What scanner candidates are currently visible?
- What did the signal decision layer do with those candidates?

This change is intentionally display-only. Decision controls stay on the Signal Decisions page, and demo order submission remains behind the existing execution token and backend guards.

## Recommended UX

Add a compact Signal Decisions panel to the Bot Monitor screen.

The main screen remains focused on monitoring:

- Top summary: connection, mode, execution state, token state, position/order counts, equity, PnL and margin.
- Main panels: Open Positions and Scanner Watchlist.
- New panel: Signal Decisions, showing the latest decisions from `/signals/decisions`.

Each decision row should show:

- symbol
- status, such as `qualified`, `skipped`, `entered`, or `error`
- reason, such as `qualified`, `dry_run`, `already_entered_this_run`, `cooldown_active`, or `no_scanner_candidates`
- Telegram state, such as `sent`, `disabled`, or `error`
- order link id only when present

The visual treatment should match the existing Bot Monitor cards and use the current Streamlit theme variables, so light theme stays light and dark theme stays coherent.

## Non-Goals

- Do not move execution buttons into Bot Monitor.
- Do not enable live trading.
- Do not enable demo auto-entry by default.
- Do not expose API keys, secrets, Telegram token, or chat id.
- Do not turn the main screen into a full report page.

## Data Flow

The UI will call:

`GET /signals/decisions?limit=5`

The backend already returns public decision rows with safe fields:

- `decision_id`
- `symbol`
- `status`
- `reason`
- `order_link_id`
- `execution_status`
- `telegram_status`
- `telegram_error`

The Bot Monitor should tolerate missing backend data. If the endpoint fails, it should show a small warning outside the visual card. If there are no rows, it should show a calm empty state: `No signal decisions yet.`

## Components

Add small formatting helpers in the existing UI layer:

- normalize the decision rows returned by the API
- render the latest decision rows as HTML inside the existing Bot Monitor visual style
- assign simple tones by status:
  - `qualified` and `entered`: success
  - `skipped`: muted
  - `error`: negative
  - all other statuses: neutral

Keep the existing Signal Decisions page as the detailed operational page. It continues to own:

- Evaluate latest
- Dry-run auto-entry
- Demo auto-entry
- full decision table

## Testing

Add focused tests for:

- Signal Decisions panel renders rows and escapes dynamic values.
- Empty Signal Decisions panel renders the empty state.
- Bot Monitor fetches `/signals/decisions?limit=5`.
- Signal Decisions page still owns the action buttons.

Run the existing test suite after implementation.
