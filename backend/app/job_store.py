from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

import pandas as pd

from bybit_weak_intraday.core import StrategyConfig
from bybit_weak_intraday.scanner import run_archive_scan

from .settings import settings

_LOCK = Lock()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def job_dir(job_id: str) -> Path:
    return settings.jobs_dir / job_id


def job_meta_path(job_id: str) -> Path:
    return job_dir(job_id) / "meta.json"


def save_meta(job_id: str, meta: dict[str, Any]) -> None:
    job_dir(job_id).mkdir(parents=True, exist_ok=True)
    tmp = job_meta_path(job_id).with_suffix(".tmp")
    tmp.write_text(json.dumps(meta, indent=2, ensure_ascii=False))
    tmp.replace(job_meta_path(job_id))


def load_meta(job_id: str) -> dict[str, Any] | None:
    p = job_meta_path(job_id)
    if not p.exists():
        return None
    return json.loads(p.read_text())


def list_jobs() -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    for p in sorted(settings.jobs_dir.glob("*/meta.json"), reverse=True):
        try:
            jobs.append(json.loads(p.read_text()))
        except Exception:
            continue
    return jobs


def create_job(payload: dict[str, Any]) -> str:
    job_id = uuid.uuid4().hex[:12]
    meta = {
        "job_id": job_id,
        "status": "queued",
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "request": payload,
        "message": "queued",
    }
    save_meta(job_id, meta)
    return job_id


def run_job(job_id: str) -> None:
    meta = load_meta(job_id)
    if not meta:
        return
    req = meta["request"]
    meta.update({"status": "running", "updated_at": now_iso(), "message": "scan running"})
    save_meta(job_id, meta)
    try:
        cfg = StrategyConfig(
            min_turnover=req["min_turnover"],
            weak_threshold=req["weak_threshold"],
            pump_threshold=req["pump_threshold"],
            tp_weak=req["tp_weak"],
            sl_weak=req["sl_weak"],
            tp_pump=req["tp_pump"],
            sl_pump=req["sl_pump"],
            max_hold_min=req["max_hold_min"],
        )
        metrics, trades = run_archive_scan(
            start=req["start"],
            end=req["end"],
            symbols=req.get("symbols") or [],
            full_universe=req.get("full_universe", False),
            include_majors=req.get("include_majors", False),
            max_symbols=req.get("max_symbols", 0),
            cache_dir=settings.cache_dir,
            cfg=cfg,
        )
        out_dir = job_dir(job_id)
        metrics_path = out_dir / "metrics.csv"
        trades_path = out_dir / "trades.csv"
        metrics.to_csv(metrics_path, index=False)
        trades.to_csv(trades_path, index=False)
        meta.update(
            {
                "status": "done",
                "updated_at": now_iso(),
                "message": "scan complete",
                "metrics_rows": int(len(metrics)),
                "trades_rows": int(len(trades)),
                "metrics_path": str(metrics_path),
                "trades_path": str(trades_path),
            }
        )
    except Exception as exc:
        meta.update({"status": "error", "updated_at": now_iso(), "message": str(exc)})
    save_meta(job_id, meta)
