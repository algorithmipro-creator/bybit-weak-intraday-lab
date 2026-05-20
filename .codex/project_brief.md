# Project Brief For Codex

We are building a research platform for Bybit USDT-perp intraday weakness strategies.

Read these files first:

```text
README.md
SPECIFICATION.md
AGENTS.md
docs/ARCHITECTURE.md
docs/ROADMAP.md
docs/CODEX_SUPERPOWERS_CONTEXT7.md
```

## Current Hypotheses

### 1. Weak Continuation / Failed Bounce

- previous-day weakness;
- reduced turnover vs previous day;
- limited intraday bounce;
- selected peak followed by VWAP loss;
- target range: roughly 4-6% underlying move.

### 2. Pump-And-Fade

- turnover spike vs previous day;
- intraday runup >= 25%;
- peak around 07:00-11:30 UTC;
- VWAP loss or midpoint loss after pump impulse;
- target range: roughly 6-8% underlying move.

## MVP Goal

- Run archive scans from UI/API/CLI.
- Store metrics/trades CSV by job.
- Visualize candidates, outcomes and MFE/MAE.
- Keep live trading disabled.

## Critical Constraint

The current scanner is historical. Some values are computed from full-day data and may include look-ahead from a live-trading perspective.

Any future alert/live-scan feature must introduce a causal mode:

```text
only use data known at the signal timestamp
```

Do not present historical labels as live-ready signals.

## Preferred Next Task

Add a causal/live-scan-safe signal mode while preserving the existing historical scanner for research labels. Add tests proving that future ticks are not used.
