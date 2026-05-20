# Project Specification

## 1. Purpose

Bybit Weak Intraday Lab is a research platform for studying short-side intraday weakness patterns in Bybit USDT perpetual markets.

The project turns an informal trading observation into a reproducible research workflow:

1. Download public Bybit tick-level trade archives.
2. Normalize trades into a consistent schema.
3. Build 5-minute bars and cumulative VWAP.
4. Score symbol/day combinations using weak-continuation and pump-and-fade rules.
5. Simulate hypothetical short entries and TP/SL exits.
6. Store metrics and candidate trades as CSV artifacts.
7. Display jobs, tables and charts in a lightweight dashboard.

The system is intentionally scoped to research, backtesting and signal analysis. It does not place orders.

## 2. Audience

The repository is prepared for three audiences:

- **Owner/researcher**: continue developing the strategy with Codex.
- **Technical reviewer**: inspect architecture, assumptions and implementation quality.
- **Partner/client**: understand the idea, current status, roadmap and risk boundaries.

## 3. Non-Goals

Current MVP does not include:

- live order execution;
- API key storage;
- exchange account access;
- position sizing;
- portfolio risk engine;
- liquidation modeling;
- fees, funding, slippage or order-book depth;
- production-grade authentication and scheduling.

These are deliberately excluded until the research signal is validated.

## 4. Data Source

Primary data source:

```text
https://public.bybit.com/trading/
```

The archive is accessed by symbol and date:

```text
https://public.bybit.com/trading/{SYMBOL}/{SYMBOL}{YYYY-MM-DD}.csv.gz
```

Expected raw columns include:

```text
timestamp, symbol, side, size, price, foreignNotional
```

Normalized tick schema:

```text
dt       UTC timestamp
ts_ns    timestamp in nanoseconds
side     Buy/Sell side as provided by archive
size     base quantity
price    trade price
quote    quote notional, preferably foreignNotional
```

## 5. Strategy Hypotheses

### 5.1 Weak Continuation / Failed Bounce

Concept:

Some tokens that were already weak on the previous day produce a limited intraday bounce, lose VWAP and continue lower.

Candidate rule:

```text
turnover_today >= 1,000,000 USDT
AND weak_score >= 9
AND entry = first 5m close below cumulative VWAP after selected weak peak
```

Score:

```text
+2 previous day return <= -4%
+2 previous day max drawdown <= -9%
+2 turnover_today / turnover_yesterday <= 0.8
+1 intraday runup between 3% and 12%
+1 weak peak time <= 11:00 UTC
+2 VWAP loss after peak
+1 sell share after peak >= 52%
```

Default exit simulation:

```text
TP = 6% underlying move
SL = 7% underlying move
max hold = 720 minutes
```

### 5.2 Pump-And-Fade

Concept:

Some low/mid-liquidity tokens produce large intraday pumps, lose VWAP or the impulse midpoint and fade later in the same day.

Candidate rule:

```text
turnover_today >= 1,000,000 USDT
AND pump_score >= 9
AND entry = first 5m close below cumulative VWAP after pump peak
```

Score:

```text
+2 turnover ratio >= 8x
+1 extra turnover ratio >= 15x
+2 intraday runup >= 25%
+1 pump peak between 07:00 and 11:30 UTC
+2 VWAP loss after pump peak
+1 impulse midpoint loss
+1 sell share after peak >= 52%
```

Default exit simulation:

```text
TP = 8% underlying move
SL = 7% underlying move
max hold = 720 minutes
```

## 6. Entry And Exit Model

Entry proxy:

```text
first 5-minute bar close below cumulative intraday VWAP after the selected peak
```

For each candidate, the scanner uses post-entry ticks to determine:

- MFE after entry;
- MAE after entry;
- first TP hit;
- first SL hit;
- time stop or EOD-style exit.

The current simulator evaluates price path only. It does not model:

- taker/maker fees;
- funding;
- spread;
- slippage;
- order-book depth;
- borrow constraints;
- exchange latency;
- partial fills.

## 7. Architecture

```text
CLI / Streamlit UI
        |
        v
FastAPI backend
        |
        v
file-based job runner
        |
        v
Bybit archive downloader -> cache
        |
        v
strategy core -> metrics.csv / trades.csv
```

Core modules:

```text
bybit_weak_intraday/core.py       strategy functions and simulation
bybit_weak_intraday/archive.py    archive URL, download and CSV loading
bybit_weak_intraday/scanner.py    multi-symbol/multi-day scan orchestration
backend/app/main.py               FastAPI routes
backend/app/job_store.py          job metadata and CSV artifacts
ui/streamlit_app.py               dashboard
scripts/run_archive_scan.py       command-line scanner
```

## 8. Backend API

### `GET /health`

Returns service status.

### `POST /jobs/scan`

Starts an archive scan job.

Required:

```text
start, end
symbols OR full_universe=true
```

Main configurable fields:

```text
min_turnover
weak_threshold
pump_threshold
tp_weak
sl_weak
tp_pump
sl_pump
max_hold_min
max_symbols
include_majors
```

### `POST /jobs/optimize-tp-sl`

Starts an offline TP/SL grid optimizer job.

The optimizer uses the same archive scanner and tick-level first-barrier simulation as normal scan jobs. It reruns the scan once per TP/SL pair, so it is slower but avoids inferring first-barrier ordering from MFE/MAE alone.

Additional fields:

```text
tp_grid: list of decimal TP values, for example [0.04, 0.06, 0.08]
sl_grid: list of decimal SL values, for example [0.05, 0.07]
```

### `GET /jobs`

Lists known scan jobs.

### `GET /jobs/{job_id}`

Returns job metadata.

### `GET /jobs/{job_id}/metrics.csv`

Downloads symbol/day metrics.

### `GET /jobs/{job_id}/trades.csv`

Downloads candidate trade simulations.

### `GET /jobs/{job_id}/grid.csv`

Downloads TP/SL grid aggregate output for optimizer jobs.

### `GET /jobs/{job_id}/grid_trades.csv`

Downloads per-combo trade output for optimizer jobs.

## 9. Output Artifacts

`metrics.csv` contains one row per scored symbol/day where data was available.

Important fields:

```text
date
symbol
turnover_usdt
prev_turnover_usdt
turnover_ratio_vs_prev
prev_day_ret_pct
prev_day_max_dd_pct
max_short_move_pct
max_runup_pct
weak_score
pump_score
candidate_score
main_candidate
selected_mode
```

`trades.csv` contains candidate simulations.

Important fields:

```text
date
symbol
mode
entry_time_utc
entry_price
tp_pct
sl_pct
mfe_after_entry_pct
mae_after_entry_pct
outcome
exit_time_utc
exit_price
pnl_underlying_pct
minutes_to_exit
```

## 10. Known Limitations

### 10.1 Research Look-Ahead Risk

The current scanner is designed for historical analysis. Some metrics are computed using full-day data:

- total current-day turnover;
- max intraday short path;
- max intraday runup;
- sell share after selected peak.

That means the current output is useful for labeling and hypothesis testing, but it should not be treated as a live-ready signal feed.

Required future improvement:

```text
Add causal/live-scan-safe features that only use data available at signal time.
```

### 10.2 Public Deployment Risk

The MVP backend is designed for private/local use. Before exposing it publicly:

- add authentication;
- validate `job_id` path params;
- limit date ranges;
- limit concurrent jobs;
- protect full-universe mode;
- hide or restrict direct backend access.

Current backend safety limits:

```text
job_id must match ^[a-f0-9]{12}$
regular scan range <= 31 days
full-universe scan range <= 7 days
full-universe scans must set max_symbols from 1 to 500
manual symbol lists are capped at 500 symbols
```

These limits reduce accidental resource exhaustion. They are not a substitute for authentication or reverse-proxy access control.

### 10.3 Statistical Validation Risk

The sample reports are useful early evidence, not a complete statistical proof.

Before trading decisions:

- run full-universe tests over larger windows;
- separate train/test periods;
- include fees, funding and slippage;
- compare against random/control symbols;
- evaluate false positives and opportunity frequency.

### 10.4 Causal Mode Boundary

Causal mode keeps signal generation separate from post-signal evaluation.

Signal generation cannot use:

- MFE or MAE;
- full-day current turnover;
- future sell share;
- future high/low;
- TP/SL outcome;
- full-day path metrics that are only known after the day is complete.

Post-signal evaluation may use future ticks only after a signal has already been emitted.

## 11. Testing

Current tests cover:

- tick normalization;
- OHLC/VWAP bar construction path metrics;
- default strategy config.

Run:

```bash
python -m pytest -q
```

Recommended next tests:

- API request validation;
- job path safety;
- known fixture scan;
- TP/SL edge cases;
- causal signal regression tests.

## 12. Roadmap

Phase 1: Repo and research hardening

```text
documentation
GitHub setup
API tests
job safety
causal/live-scan-safe feature split
```

Phase 2: Strategy analysis

```text
TP/SL grid optimizer
MFE/MAE distribution dashboard
score tier analysis
turnover tier analysis
time-of-day analysis
```

Phase 3: More market context

```text
funding data
open interest data
market cap/rank filters
symbol metadata
```

Phase 4: Alerts and paper mode

```text
scheduled scans
Telegram/Discord alerts
paper-trading journal
no live execution by default
```

Phase 5: Execution review

```text
Only after validation: decide whether live execution belongs in a separate repository/module.
```
