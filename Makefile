.PHONY: up down logs test scan-sample

up:
	docker compose up --build -d

down:
	docker compose down

logs:
	docker compose logs -f

test:
	pytest -q

scan-sample:
	python scripts/run_archive_scan.py \
	  --start 2026-03-18 \
	  --end 2026-03-27 \
	  --symbols EIGENUSDT,GRASSUSDT,RVNUSDT,ENJUSDT,JTOUSDT,STGUSDT,ENAUSDT \
	  --cache-dir ./data/bybit_archive_cache \
	  --out-metrics ./data/sample_metrics.csv \
	  --out-trades ./data/sample_trades.csv
