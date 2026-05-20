# Bybit Weak Intraday Lab

Research-платформа для поиска слабых intraday-токенов на Bybit USDT perpetual markets.

Проект формализует две short-гипотезы:

- **Weak continuation / failed bounce**: токен уже был слабым, делает слабый отскок и теряет VWAP.
- **Pump-and-fade**: токен резко пампится, затем теряет VWAP/импульс и переходит в fade.

Это **research/backtest/signal lab**. Проект не размещает live orders, не хранит API keys и не является production trading bot.

## Current Status

MVP уже включает:

- deterministic strategy core;
- tick-level Bybit public archive scanner;
- FastAPI backend with scan jobs;
- Streamlit dashboard;
- Docker Compose deployment;
- sample v5 research outputs;
- Codex-ready project instructions;
- CI workflow with pytest.

Главная цель текущей версии: быстро проверять гипотезы на публичных historical trades, смотреть candidates, MFE/MAE, TP/SL outcomes и развивать стратегию без включения live execution.

## Repository Map

```text
bybit_weak_intraday/       strategy core, archive loader, scanner
backend/app/               FastAPI API and file-based job runner
ui/                        Streamlit dashboard
scripts/                   CLI scan tools
data/sample/               sample v5 reports and CSV outputs
configs/                   default strategy config
deploy/                    VPS notes and Caddy example
docs/                      project documentation and handoff notes
.codex/                    Codex project brief
.github/workflows/         CI
AGENTS.md                  coding-agent instructions
SPECIFICATION.md           formal project and strategy specification
PRESENTATION.md            short overview for showing the project
```

## Strategy Summary

### Weak Continuation

```text
turnover_today >= 1,000,000 USDT
AND weak_score >= 9
AND entry = first 5m close below cumulative VWAP after selected weak peak
```

Score components:

```text
+2 previous day return <= -4%
+2 previous day max drawdown <= -9%
+2 turnover_today / turnover_yesterday <= 0.8
+1 intraday runup between 3% and 12%
+1 weak peak time <= 11:00 UTC
+2 VWAP loss after peak
+1 sell share after peak >= 52%
```

### Pump-And-Fade

```text
turnover_today >= 1,000,000 USDT
AND pump_score >= 9
AND entry = first 5m close below cumulative VWAP after pump peak
```

Score components:

```text
+2 turnover ratio >= 8x
+1 extra turnover ratio >= 15x
+2 intraday runup >= 25%
+1 pump peak between 07:00 and 11:30 UTC
+2 VWAP loss after pump peak
+1 impulse midpoint loss
+1 sell share after peak >= 52%
```

## Important Research Caveat

The current scanner is a historical research scanner. Some metrics are computed from full-day data and should not be treated as live-ready signals without a causal/live-scan rewrite.

Before paper/live alerting, the next key step is to separate:

- **historical labeling metrics**: useful for research and analysis;
- **causal signal metrics**: available only at the exact signal time.

See [SPECIFICATION.md](SPECIFICATION.md) for details.

## Quick Start

### Local Python

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pytest -q
```

On Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pytest -q
```

### Docker

```bash
cp .env.example .env
docker compose up --build
```

Open:

- UI: `http://localhost:8501`
- API docs: `http://localhost:8000/docs`

## CLI Scan Example

```bash
python scripts/run_archive_scan.py \
  --start 2026-03-18 \
  --end 2026-03-27 \
  --symbols EIGENUSDT,GRASSUSDT,RVNUSDT,ENJUSDT,JTOUSDT,STGUSDT,ENAUSDT \
  --cache-dir ./data/bybit_archive_cache \
  --out-metrics ./data/sample_metrics.csv \
  --out-trades ./data/sample_trades.csv
```

Full-universe scans are disk and network heavy. Start with:

```bash
python scripts/run_archive_scan.py \
  --start 2026-03-01 \
  --end 2026-03-31 \
  --full-universe \
  --max-symbols 50 \
  --cache-dir ./data/bybit_archive_cache \
  --out-metrics ./data/bybit_metrics_2026_03.csv \
  --out-trades ./data/bybit_trades_2026_03.csv
```

## API

```text
GET  /health
POST /jobs/scan
GET  /jobs
GET  /jobs/{job_id}
GET  /jobs/{job_id}/metrics.csv
GET  /jobs/{job_id}/trades.csv
```

Safety limits in the current backend:

```text
job_id must match ^[a-f0-9]{12}$
regular scan range <= 31 days
full-universe scan range <= 7 days
full-universe scans must set max_symbols from 1 to 500
manual symbol lists are capped at 500 symbols
```

Example:

```bash
curl -X POST http://localhost:8000/jobs/scan \
  -H "Content-Type: application/json" \
  -d '{
    "start":"2026-03-18",
    "end":"2026-03-27",
    "symbols":["EIGENUSDT","GRASSUSDT","RVNUSDT","ENJUSDT","JTOUSDT","STGUSDT","ENAUSDT"],
    "full_universe":false,
    "min_turnover":1000000,
    "weak_threshold":9,
    "pump_threshold":9,
    "tp_weak":0.06,
    "sl_weak":0.07,
    "tp_pump":0.08,
    "sl_pump":0.07,
    "max_hold_min":720
  }'
```

## Documentation

- [SPECIFICATION.md](SPECIFICATION.md): formal strategy, system, data, API and limitations spec.
- [PRESENTATION.md](PRESENTATION.md): concise project description for sharing.
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): component and data-flow overview.
- [docs/DEVELOPMENT_PLAN_RU.md](docs/DEVELOPMENT_PLAN_RU.md): Russian development roadmap refined from the project draft.
- [docs/IMPLEMENTATION_PLAN_CAUSAL_SCAN.md](docs/IMPLEMENTATION_PLAN_CAUSAL_SCAN.md): implementation-ready plan for causal/live-scan-safe mode.
- [docs/GITHUB_SETUP.md](docs/GITHUB_SETUP.md): how to initialize and push the repository.
- [docs/CODEX_SUPERPOWERS_CONTEXT7.md](docs/CODEX_SUPERPOWERS_CONTEXT7.md): Codex, Superpowers and Context7 setup.
- [deploy/README_VPS.md](deploy/README_VPS.md): VPS deployment notes.

## Roadmap

Near-term:

1. Add causal/live-scan-safe signal calculations.
2. Add TP/SL grid optimizer endpoint and UI page.
3. Add job limits, API auth and safer public deployment defaults.
4. Add funding/open-interest features from Bybit V5.
5. Add market-cap/rank filters from an external provider.

Later:

1. Add scheduled full-universe scans.
2. Add Telegram/Discord signal alerts.
3. Add paper-trading mode.
4. Evaluate whether live execution should exist as a separate isolated module.

## Safety Boundaries

- No exchange credentials in the repository.
- No live order placement in the MVP.
- Backtest output excludes fees, funding, slippage, latency and order-book depth.
- Public deployment should protect API endpoints with authentication or network restrictions.
- Research results must be validated on broader full-universe samples before any trading use.
