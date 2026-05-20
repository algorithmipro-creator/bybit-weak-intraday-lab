# Codex Instructions

This repository is a research lab for Bybit weak-intraday short strategy discovery.

Before making changes, read:

```text
README.md
SPECIFICATION.md
PRESENTATION.md
.codex/project_brief.md
docs/ARCHITECTURE.md
docs/ROADMAP.md
```

## Safety And Scope

- Do not add live order execution unless explicitly requested in a separate reviewed task.
- Do not store API keys, secrets, Telegram tokens or exchange credentials in the repository.
- Treat all PnL as hypothetical research output.
- Fees, slippage, funding, latency, borrow constraints and liquidation risk must be modeled before any live use.
- Keep strategy logic deterministic and testable.
- Preserve the distinction between historical labeling and causal/live-scan-safe signals.

## Important Research Constraint

The current scanner is historical. Some fields use full-day data and are not safe as live signal inputs.

When adding signal functionality:

```text
historical mode = can use full-day data for labeling/research
causal mode     = can only use data available at signal time
```

Do not present historical labels as live-ready alerts.

## Code Conventions

- Core strategy logic lives in `bybit_weak_intraday/`.
- Backend API lives in `backend/app/`.
- Streamlit UX lives in `ui/`.
- CLI scripts live in `scripts/`.
- Documentation lives in `docs/` or top-level Markdown files.
- Avoid changing public function names without updating tests and docs.
- Prefer small, deterministic functions over hidden global state.

## Preferred Workflow

1. Understand the relevant docs and code path.
2. Add or modify tests under `tests/`.
3. Update implementation.
4. Run `python -m pytest -q`.
5. For API changes, verify `/health` and `/docs`.
6. For UX changes, verify Streamlit manually or through Docker when possible.
7. Update README/SPECIFICATION if behavior changes.

## Codex Tooling

Recommended setup:

```text
Superpowers skills for workflow discipline
Context7 MCP for current framework documentation
```

See:

```text
docs/CODEX_SUPERPOWERS_CONTEXT7.md
```

Use Context7 when changing framework-specific code such as FastAPI, Streamlit, pandas or Plotly usage.

## Next Research Tasks

- Add causal/live-scan-safe signal mode.
- Add TP/SL grid optimizer.
- Add API safety limits and tests.
- Add MFE/MAE distribution dashboard.
- Add funding/OI features from Bybit V5 API.
- Add symbol rank/market-cap filters from a separate data provider.
- Add paper-trading alert mode, not live execution.
