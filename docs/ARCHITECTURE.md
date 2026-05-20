# Architecture

## Overview

The project is intentionally small and modular:

```text
                 +---------------------+
                 | Streamlit Dashboard |
                 +----------+----------+
                            |
                            v
                 +---------------------+
                 |   FastAPI Backend   |
                 +----------+----------+
                            |
                            v
                 +---------------------+
                 | File-Based Job Store|
                 +----------+----------+
                            |
                            v
+----------------+  +-------+--------+  +--------------------+
| Bybit Archive  +->+ Archive Cache  +->+ Strategy Core      |
+----------------+  +----------------+  +---------+----------+
                                               |
                                               v
                                      metrics.csv / trades.csv
```

## Components

### Strategy Core

Path:

```text
bybit_weak_intraday/core.py
bybit_weak_intraday/causal.py
```

Responsibilities:

- normalize raw tick data;
- build 5-minute bars;
- calculate cumulative VWAP;
- calculate weak/pump path metrics;
- score symbol/day candidates;
- simulate hypothetical short TP/SL exits.

The core is exchange-execution agnostic. It does not place orders.

`core.py` contains the historical research scanner primitives. `causal.py` contains live-scan-safe signal primitives that must only use data available at the signal timestamp.

### Archive Layer

Path:

```text
bybit_weak_intraday/archive.py
```

Responsibilities:

- construct public archive URLs;
- list visible USDT symbols;
- download `.csv.gz` files;
- load raw archive CSV data;
- maintain local cache paths.

### Scanner

Path:

```text
bybit_weak_intraday/scanner.py
```

Responsibilities:

- iterate symbols and dates;
- load current and previous day data;
- call strategy scoring;
- collect metrics and trade rows;
- return pandas DataFrames.

### Backend

Path:

```text
backend/app/
```

Responsibilities:

- expose scan API;
- validate scan requests;
- create scan jobs;
- execute scan jobs in a thread pool;
- store job metadata and CSV artifacts.

Current persistence is file-based for simplicity:

```text
data/jobs/{job_id}/meta.json
data/jobs/{job_id}/metrics.csv
data/jobs/{job_id}/trades.csv
```

### UI

Path:

```text
ui/streamlit_app.py
```

Responsibilities:

- configure scan parameters;
- start scan jobs;
- display job status;
- download result CSVs;
- show tables and basic charts.

### Deployment

Paths:

```text
docker-compose.yml
backend/Dockerfile
ui/Dockerfile
deploy/
```

Default services:

```text
backend: FastAPI on port 8000
ui:      Streamlit on port 8501
data:    bind-mounted ./data directory
```

## Data Flow

1. User submits scan settings from UI, CLI or API.
2. Backend creates a job id and stores request metadata.
3. Scanner downloads missing Bybit archive files into cache.
4. Scanner loads current and previous day ticks.
5. Core logic calculates metrics and optional candidate trade simulation.
6. Backend saves `metrics.csv` and `trades.csv`.
7. UI reads the CSVs through backend endpoints.

## Current Trade-Offs

### File-Based Job Store

Pros:

- simple;
- transparent;
- easy to inspect;
- good for MVP and small VPS.

Cons:

- no queue durability guarantees;
- no multi-instance coordination;
- no built-in cleanup policy;
- weaker for public production deployments.

Future replacement options:

- SQLite for local durable jobs;
- Postgres for multi-user deployments;
- Redis/RQ or Celery for job scheduling.

### ThreadPoolExecutor

Pros:

- minimal dependency footprint;
- enough for small private scans.

Cons:

- no distributed scheduling;
- no cancellation;
- no persistent queue;
- vulnerable to overload without API limits.

### Streamlit UI

Pros:

- fast to build;
- good for research dashboards;
- easy CSV/table/chart workflow.

Cons:

- not a polished multi-user web app;
- should be protected behind auth if public;
- server-side HTTP requests must be restricted in production.

## Recommended Hardening

Before any public demo server:

1. Add API auth or reverse-proxy auth.
2. Validate `job_id` with a strict regex.
3. Limit scan date range and full-universe access.
4. Add a disk cleanup policy.
5. Restrict Streamlit backend URL configuration.
6. Add backend API tests.

Before signal alerts:

1. Split historical labeling from causal signal features.
2. Add live-scan-safe state handling.
3. Add fees/funding/slippage modeling.
4. Add false-positive analysis on broader samples.
