# Presentation Brief

## One-Line Description

Bybit Weak Intraday Lab is a research platform for finding weak intraday USDT-perp tokens on Bybit using tick-level archive data, VWAP-loss entries and TP/SL path simulation.

## Problem

Intraday crypto moves often look obvious after the fact, but manual observation is hard to repeat:

- too many symbols;
- too much tick data;
- unclear entry rules;
- unclear TP/SL behavior;
- easy to overfit by memory.

This project turns the observation into a reproducible scanner and dashboard.

## Hypothesis

Two patterns may create short-side opportunities:

1. **Weak continuation**: previously weak token makes a limited bounce, loses VWAP and continues down.
2. **Pump-and-fade**: token makes a large intraday pump, then loses VWAP/impulse structure and fades.

The project scores each symbol/day, finds candidate entries and measures what happened after the entry.

## What The MVP Does

- Downloads Bybit public tick archives.
- Builds 5-minute OHLCV bars and cumulative VWAP.
- Scores weak-continuation and pump-and-fade setups.
- Simulates short-side TP/SL outcomes tick by tick.
- Saves metrics and trade simulations as CSV.
- Provides a FastAPI backend and Streamlit dashboard.
- Runs locally or on VPS through Docker Compose.

## What It Does Not Do

- It does not place live orders.
- It does not use exchange API keys.
- It does not manage real positions.
- It does not include fees, funding, slippage or order-book depth yet.

## Current Architecture

```text
Bybit public archive
        |
        v
archive cache
        |
        v
strategy core
        |
        v
metrics.csv / trades.csv
        |
        v
FastAPI backend + Streamlit dashboard
```

## Why The Structure Is Useful

The project is split into clean layers:

- `bybit_weak_intraday/`: reusable strategy and scanner logic;
- `backend/app/`: API and job runner;
- `ui/`: dashboard;
- `scripts/`: CLI experiments;
- `docs/`: explanation, setup and roadmap.

This makes it suitable for Codex-driven iteration: one can improve strategy logic, backend endpoints or UI independently.

## Main Research Caveat

The current scanner is historical. Some features use full-day information and are not yet safe for live signal generation.

The next important engineering step is a causal signal mode where every feature is calculated only from data available at signal time.

## Suggested Next Milestones

1. Causal/live-scan-safe signal engine.
2. TP/SL grid optimizer.
3. API auth, job limits and safer VPS defaults.
4. Funding/open-interest features.
5. Scheduled scans and signal alerts.
6. Paper-trading journal.

## Demo Flow

1. Open README and explain strategy idea.
2. Show `SPECIFICATION.md` for formal rules and limitations.
3. Run tests with `python -m pytest -q`.
4. Start Docker Compose.
5. Open Streamlit UI.
6. Launch a small symbol/date scan.
7. Download and inspect `metrics.csv` and `trades.csv`.
8. Discuss roadmap and risk boundaries.
