# Roadmap

## Phase 0: Repository Presentation

Status: current focus.

Deliverables:

- polished README;
- formal specification;
- presentation brief;
- architecture notes;
- GitHub setup instructions;
- Codex/Superpowers/Context7 setup instructions.

## Phase 1: Research Correctness

Goal: separate historical labeling from live-signal-safe calculations.

Status: causal core implemented in `bybit_weak_intraday/causal.py`; backend/UI causal scan integration is available through `POST /jobs/scan-causal` and the Streamlit "Causal signal scan" mode. Causal jobs now keep no-lookahead `signals.csv` separate from post-signal `evaluations.csv`.

Detailed implementation plan:

```text
docs/IMPLEMENTATION_PLAN_CAUSAL_SCAN.md
```

Tasks:

1. Add causal signal functions that only use data available at the signal timestamp. Initial implementation complete.
2. Keep current full-day scanner as historical research mode.
3. Add tests for no-look-ahead behavior. Initial implementation complete.
4. Add post-signal evaluation for causal signals. Initial implementation complete.
5. Add known fixture datasets for reproducible strategy tests.
6. Document which fields are historical-only and which are causal-safe.

Success criteria:

```text
A reviewer can tell exactly which metrics can be used live and which are only for research labels.
```

## Phase 2: Backend Hardening

Goal: make private VPS usage safer.

Tasks:

1. Validate `job_id` with a strict regex.
2. Limit date ranges.
3. Limit full-universe scans.
4. Add API tests.
5. Add basic auth or reverse-proxy auth documentation.
6. Add job cleanup policy.

Success criteria:

```text
A small VPS can run scans without accidental open-ended resource usage.
```

## Phase 3: Strategy Analytics

Goal: improve research feedback loops.

Status: initial offline TP/SL grid optimizer implemented with backend job support and Streamlit view.

Tasks:

1. Add TP/SL grid optimizer. Initial offline implementation complete.
2. Add MFE/MAE distribution views.
3. Add score tier analysis.
4. Add time-of-day analysis.
5. Add turnover tier analysis.
6. Compare candidates vs near-miss controls.

Success criteria:

```text
The dashboard helps decide whether thresholds are robust or overfit.
```

## Phase 4: Market Context

Goal: enrich signals with broader market variables.

Tasks:

1. Add funding history.
2. Add open interest features.
3. Add market-cap/rank filters.
4. Add exchange instrument metadata.
5. Track symbol listing/delisting availability.

Success criteria:

```text
Scanner can segment results by liquidity, rank, funding and OI behavior.
```

## Phase 5: Alerts And Paper Mode

Goal: move from pure backtest to monitored research signals.

Tasks:

1. Add scheduled scans.
2. Add Telegram/Discord signal alerts.
3. Add paper-trading journal.
4. Add signal lifecycle states.
5. Track missed/expired/invalidated setups.

Success criteria:

```text
Signals can be observed in real time without placing live orders.
```

## Phase 6: Execution Decision

Goal: decide whether live execution should exist at all.

This phase requires separate review.

Questions:

- Is the signal statistically validated?
- Are fees, funding and slippage included?
- Is risk management defined?
- Is failure behavior understood?
- Should execution live in this repository or a separate isolated module?

Default answer until proven otherwise:

```text
No live execution in this repository.
```
