# Bybit Demo Execution Design

## Цель

Добавить первый безопасный слой подключения к реальному Bybit Demo Trading аккаунту для USDT perpetual short-сделок (`category=linear`).

Первый этап не автоматизирует входы по сигналам. Он проверяет, что проект умеет безопасно подключаться к demo API, читать состояние аккаунта и отправлять одну маленькую тестовую short-заявку с контролируемыми лимитами.

## Почему не live

Проект остается research/signal lab. Этот этап нужен, чтобы не проверять сигналы руками, но реальные деньги не затрагиваются.

Разрешенный режим:

```text
BWI_EXECUTION_MODE=demo
```

Запрещено в первом этапе:

```text
mainnet order placement
auto-entry from signals
market-wide auto trading
large position sizing
storing API keys in git
```

## Источники API

Bybit V5 Demo Trading documentation:

```text
https://bybit-exchange.github.io/docs/v5/demo
```

Relevant Bybit V5 order documentation:

```text
https://bybit-exchange.github.io/docs/v5/market/instrument
https://bybit-exchange.github.io/docs/v5/market/tickers
https://bybit-exchange.github.io/docs/v5/order/create-order
https://bybit-exchange.github.io/docs/v5/position/trading-stop
https://bybit-exchange.github.io/docs/v5/guide
```

Key demo assumptions from the official docs:

- REST domain is `https://api-demo.bybit.com`.
- Demo API keys are created from the Bybit account after switching to Demo Trading.
- Demo Trading supports a limited subset of V5 APIs and is intended for trading experience/testing.
- Demo order records are not permanent, so this project must keep its own local journal.

## Scope

### In scope

1. Add demo-only execution settings.
2. Add a Bybit V5 demo client with signed REST requests.
3. Add read-only status methods:
   - wallet balance;
   - positions;
   - open orders.
4. Add one controlled test short endpoint:
   - `POST /execution/demo/place-test-short`.
5. Add a local execution journal for all attempts and responses.
6. Add a Streamlit `Demo Execution` view:
   - connection/config status;
   - wallet summary;
   - open positions;
   - open orders;
   - test short form;
   - recent journal rows.
7. Add tests around safety gates, request construction and disabled behavior.

### Out of scope

1. Auto-entry from causal signals.
2. Scheduler-triggered order placement.
3. Mainnet execution.
4. Long positions.
5. Cross-exchange execution.
6. Liquidation modeling.
7. Advanced order management, trailing stops or position scaling.

## Configuration

Add environment variables:

```text
BWI_EXECUTION_MODE=disabled
BWI_EXECUTION_ENABLED=false
BWI_BYBIT_DEMO_API_KEY=
BWI_BYBIT_DEMO_API_SECRET=
BWI_BYBIT_DEMO_BASE_URL=https://api-demo.bybit.com
BWI_EXECUTION_SYMBOL_WHITELIST=ENAUSDT,JTOUSDT
BWI_MAX_DEMO_NOTIONAL_USDT=25
BWI_MAX_OPEN_POSITIONS=1
BWI_MAX_DAILY_TEST_ORDERS=3
BWI_EXECUTION_JOURNAL_PATH=/app/data/execution_journal.csv
```

Rules:

- Default mode is disabled.
- Demo order placement requires both `BWI_EXECUTION_MODE=demo` and `BWI_EXECUTION_ENABLED=true`.
- `BWI_BYBIT_DEMO_BASE_URL` must equal `https://api-demo.bybit.com` for order placement.
- API keys are read from environment only.
- `.env.example` may document variable names but must not include secrets.

## Architecture

New package:

```text
bybit_weak_intraday/execution/
    __init__.py
    bybit_demo.py
    journal.py
    safety.py
```

Backend:

```text
backend/app/execution_routes.py
```

UI:

```text
ui/streamlit_app.py
```

Tests:

```text
tests/test_execution_safety.py
tests/test_bybit_demo_client.py
tests/test_execution_api.py
```

## Demo client interface

The client should expose a small, testable interface:

```python
class BybitDemoClient:
    def instruments_info(self, symbol: str) -> dict: ...
    def ticker(self, symbol: str) -> dict: ...
    def wallet_balance(self, coin: str = "USDT") -> dict: ...
    def positions(self, symbol: str | None = None) -> dict: ...
    def open_orders(self, symbol: str | None = None) -> dict: ...
    def place_short_market_order(
        self,
        symbol: str,
        qty: str,
        take_profit: str | None,
        stop_loss: str | None,
        order_link_id: str,
    ) -> dict: ...
```

Implementation notes:

- Use Bybit V5 authentication headers.
- Keep request signing isolated in one function.
- Do not log API secrets or full signed headers.
- Use `orderLinkId` for idempotency and journal correlation.
- Use `category=linear`.
- Use `side=Sell`.
- Use one-way mode first with `positionIdx=0`, unless the account requires hedge-mode configuration later.

## Safety gates

Before any order placement:

1. `execution_mode == "demo"`.
2. `execution_enabled is True`.
3. base URL is exactly `https://api-demo.bybit.com`.
4. API key and secret are present.
5. symbol is in whitelist.
6. requested notional is less than or equal to `max_demo_notional_usdt`.
7. current open positions count is less than `max_open_positions`.
8. daily test order count is less than `max_daily_test_orders`.
9. TP and SL are present for test short orders.

If any gate fails, return a structured error and write a rejected journal row. Do not call Bybit.

## Test short endpoint

Endpoint:

```text
POST /execution/demo/place-test-short
```

Request:

```json
{
  "symbol": "ENAUSDT",
  "notional_usdt": 10,
  "take_profit_pct": 0.06,
  "stop_loss_pct": 0.07
}
```

Backend behavior:

1. Fetch instrument metadata from Bybit.
2. Fetch a recent ticker/reference price from Bybit.
3. Convert notional to quantity using instrument precision.
4. For a short:
   - take profit price is below entry/reference price;
   - stop loss price is above entry/reference price.
5. Submit market `Sell` order with TP/SL parameters when supported.
6. Store request, safety decision and Bybit response in the journal.

The endpoint must not accept a user-supplied reference price. It should derive quantity, TP and SL from Bybit metadata/ticker data so the test order path matches real execution conditions.

## Journal

Store all execution events in a local CSV or JSONL file under `data/`.

Minimum fields:

```text
created_at_utc
event_id
order_link_id
mode
symbol
side
category
requested_notional_usdt
qty
take_profit
stop_loss
status
reason
bybit_ret_code
bybit_ret_msg
raw_response_path
```

Do not rely on Bybit demo history as the only record, because demo records are time-limited.

## UI

Add a `Demo Execution` section with:

- execution mode badge;
- configured/not-configured status;
- wallet table;
- positions table;
- open orders table;
- test short form;
- recent journal table.

The test order button should be disabled or blocked when execution is not enabled. UI text must make it clear that this is Bybit Demo only.

## Error handling

Expected errors:

- missing API keys;
- disabled execution;
- non-demo base URL;
- symbol not whitelisted;
- too large notional;
- open position limit reached;
- Bybit API error;
- precision/qty conversion error.

All errors should return structured JSON from backend and be visible in the journal/UI.

## Testing

Unit tests:

- disabled mode blocks order placement;
- missing API keys blocks order placement;
- non-demo base URL blocks order placement;
- symbol whitelist blocks unknown symbols;
- notional limit blocks oversized order;
- open position limit blocks additional orders;
- order request uses `category=linear` and `side=Sell`;
- TP for short is below reference price and SL is above reference price;
- journal writes accepted and rejected attempts.

API tests:

- status endpoint works without API keys;
- order endpoint rejects when disabled;
- order endpoint rejects unknown symbol;
- order endpoint returns a structured response when client is mocked.

No tests should call real Bybit.

## Rollout

Phase A: settings, safety checks, journal, mocked client tests.

Phase B: signed demo client and read-only endpoints.

Phase C: controlled test short endpoint.

Phase D: Streamlit Demo Execution view.

Phase E: manual demo-account verification with tiny order size.

Auto-entry from causal signals starts only after this spec passes and a separate design is approved.

## Success Criteria

The first demo execution slice is complete when:

- the app can show demo wallet/positions/open orders;
- a whitelisted tiny short test order can be sent to Bybit Demo;
- rejected attempts are recorded without calling Bybit;
- accepted attempts and Bybit responses are recorded;
- all tests pass without touching real Bybit;
- mainnet order placement is impossible through this code path.
