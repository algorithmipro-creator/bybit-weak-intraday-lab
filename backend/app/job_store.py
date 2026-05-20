from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

import pandas as pd

from bybit_weak_intraday.core import StrategyConfig
from bybit_weak_intraday.optimizer import run_archive_tp_sl_grid
from bybit_weak_intraday.scanner import run_archive_scan

from .settings import settings

_LOCK = Lock()
JOB_ID_PATTERN = r"^[a-f0-9]{12}$"
_JOB_ID_RE = re.compile(JOB_ID_PATTERN)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def validate_job_id(job_id: str) -> str:
    if not _JOB_ID_RE.fullmatch(job_id):
        raise ValueError("invalid job_id")
    return job_id


def job_dir(job_id: str) -> Path:
    return settings.jobs_dir / validate_job_id(job_id)


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


def create_job(payload: dict[str, Any], job_type: str = "scan") -> str:
    job_id = uuid.uuid4().hex[:12]
    meta = {
        "job_id": job_id,
        "job_type": job_type,
        "status": "queued",
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "request": payload,
        "message": "queued",
    }
    save_meta(job_id, meta)
    return job_id


def _strategy_config_from_request(req: dict[str, Any]) -> StrategyConfig:
    return StrategyConfig(
        min_turnover=req["min_turnover"],
        weak_threshold=req["weak_threshold"],
        pump_threshold=req["pump_threshold"],
        tp_weak=req["tp_weak"],
        sl_weak=req["sl_weak"],
        tp_pump=req["tp_pump"],
        sl_pump=req["sl_pump"],
        max_hold_min=req["max_hold_min"],
    )


def _run_scan_job(job_id: str, meta: dict[str, Any]) -> None:
    req = meta["request"]
    cfg = _strategy_config_from_request(req)
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


def _run_tp_sl_grid_job(job_id: str, meta: dict[str, Any]) -> None:
    req = meta["request"]
    cfg = _strategy_config_from_request(req)
    grid, grid_trades = run_archive_tp_sl_grid(
        start=req["start"],
        end=req["end"],
        symbols=req.get("symbols") or [],
        full_universe=req.get("full_universe", False),
        include_majors=req.get("include_majors", False),
        max_symbols=req.get("max_symbols", 0),
        cache_dir=settings.cache_dir,
        cfg=cfg,
        tp_grid=req.get("tp_grid") or [],
        sl_grid=req.get("sl_grid") or [],
    )
    out_dir = job_dir(job_id)
    grid_path = out_dir / "grid.csv"
    grid_trades_path = out_dir / "grid_trades.csv"
    grid.to_csv(grid_path, index=False)
    grid_trades.to_csv(grid_trades_path, index=False)
    meta.update(
        {
            "status": "done",
            "updated_at": now_iso(),
            "message": "tp/sl grid optimization complete",
            "grid_rows": int(len(grid)),
            "grid_trades_rows": int(len(grid_trades)),
            "grid_path": str(grid_path),
            "grid_trades_path": str(grid_trades_path),
        }
    )


def run_job(job_id: str) -> None:
    meta = load_meta(job_id)
    if not meta:
        return
    meta.update({"status": "running", "updated_at": now_iso(), "message": "scan running"})
    save_meta(job_id, meta)
    try:
        if meta.get("job_type") == "tp_sl_grid":
            _run_tp_sl_grid_job(job_id, meta)
        else:
            _run_scan_job(job_id, meta)
    except Exception as exc:
        meta.update({"status": "error", "updated_at": now_iso(), "message": str(exc)})
    save_meta(job_id, meta)
