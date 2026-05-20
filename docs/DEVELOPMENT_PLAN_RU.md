# План развития проекта

Этот документ приводит черновую спецификацию из `file.md` к рабочему виду для репозитория.

Проект остается research/backtest/signal lab. Live trading не является текущей целью и может рассматриваться только после causal-сигналов, full-universe validation, paper trading и отдельного risk review.

## Текущая стадия

```text
Статус: оформленный research-MVP
Код: strategy core + archive scanner + FastAPI + Streamlit + Docker Compose
Документы: README, specification, presentation, architecture, roadmap
GitHub: public repository
Live trading: disabled
```

## Приоритетный порядок этапов

### 1. Causal / Live-Scan-Safe Mode

Цель: убрать look-ahead bias из будущих сигналов.

Система должна уметь считать отдельный causal-сигнал, используя только:

- данные предыдущего дня;
- current-day ticks/bars с timestamp `<= signal_time`;
- cumulative VWAP, turnover, runup и sell pressure только до момента сигнала.

Запрещено использовать для signal decision:

- full-day current turnover;
- будущий high/low после сигнала;
- MFE/MAE;
- sell share после сигнала;
- max short path, известный только после окончания дня.

Output этапа:

```text
bybit_weak_intraday/causal.py
tests/test_causal.py
документация causal vs historical fields
```

### 2. Backend Safety

Цель: сделать private/VPS usage безопаснее до scheduler и alerts.

Нужно:

- валидировать `job_id`;
- ограничить диапазон дат;
- ограничить full-universe scans;
- добавить API tests;
- описать auth/reverse-proxy protection.

### 3. TP/SL Grid Optimizer

Цель: offline-анализ TP/SL по уже найденным candidate trades.

Первая версия должна быть именно offline grid optimizer, а не динамическая модель.

Нужно:

- считать агрегаты по TP/SL сетке;
- группировать результаты по `mode`, `score tier`, `turnover tier`;
- добавить backend endpoint;
- добавить Streamlit page;
- добавить tests.

### 4. Full-Universe Validation

Цель: проверить гипотезу на большом наборе символов и дат.

Нужно:

- запускать full-universe scans ограниченными batch jobs;
- сохранять результаты воспроизводимо;
- анализировать false positives, opportunity frequency, score tiers;
- отделять train/test periods.

### 5. Scheduler

Цель: автоматизировать запуск research/live-scan jobs.

Scheduler добавлять только после backend safety.

Варианты:

- APScheduler для простого VPS;
- external cron для минимальной надежной схемы;
- полноценная queue later, если потребуется.

### 6. Alerts

Цель: отправлять только research/paper signals.

Нужно:

- Telegram или Discord integration;
- secrets только через `.env`;
- no exchange keys;
- no live order placement;
- UI для включения/выключения alerts.

### 7. Paper Trading

Цель: наблюдать сигналы в безопасном режиме.

Нужно:

- журнал paper trades;
- signal lifecycle;
- simulated entries/exits;
- summary по дням/неделям;
- comparison vs historical expectations.

### 8. Live Trading Decision

Цель: не автоматизировать торговлю, а принять отдельное решение после проверки.

Перед live trading должны быть готовы:

- causal signals;
- full-universe validation;
- fees/funding/slippage;
- risk model;
- paper trading results;
- отдельный security review;
- отдельный модуль или отдельный repository для execution.

Default decision:

```text
No live trading in this repository.
```

## Что делаем первым

Первый implementation-ready план:

```text
docs/IMPLEMENTATION_PLAN_CAUSAL_SCAN.md
```

Он описывает, какие файлы создать/изменить, какие тесты написать и как проверить, что будущие данные не используются.
