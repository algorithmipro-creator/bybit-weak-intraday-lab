from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path as FilePath
from typing import Annotated

from fastapi import FastAPI, HTTPException, Path
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .job_store import JOB_ID_PATTERN, create_job, job_dir, list_jobs, load_meta, run_job
from .schemas import JobResponse, ScanRequest
from .settings import settings

app = FastAPI(title=settings.project_name)
executor = ThreadPoolExecutor(max_workers=settings.max_workers)
JobId = Annotated[str, Path(pattern=JOB_ID_PATTERN)]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.cors_origins == "*" else settings.cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "project": settings.project_name}


@app.post("/jobs/scan", response_model=JobResponse)
def start_scan(req: ScanRequest) -> JobResponse:
    if not req.full_universe and not req.symbols:
        raise HTTPException(status_code=400, detail="Provide symbols or set full_universe=true")
    payload = req.model_dump()
    payload["symbols"] = [s.upper().strip() for s in payload.get("symbols", []) if s.strip()]
    job_id = create_job(payload)
    executor.submit(run_job, job_id)
    return JobResponse(job_id=job_id, status="queued", message="scan queued")


@app.get("/jobs")
def jobs() -> list[dict]:
    return list_jobs()


@app.get("/jobs/{job_id}")
def job(job_id: JobId) -> dict:
    meta = load_meta(job_id)
    if not meta:
        raise HTTPException(status_code=404, detail="job not found")
    if meta.get("status") == "done":
        meta["metrics_url"] = f"/jobs/{job_id}/metrics.csv"
        meta["trades_url"] = f"/jobs/{job_id}/trades.csv"
    return meta


def _job_file(job_id: str, name: str) -> FilePath:
    p = job_dir(job_id) / name
    if not p.exists():
        raise HTTPException(status_code=404, detail=f"{name} not found")
    return p


@app.get("/jobs/{job_id}/metrics.csv")
def metrics_csv(job_id: JobId) -> FileResponse:
    return FileResponse(_job_file(job_id, "metrics.csv"), media_type="text/csv", filename=f"{job_id}_metrics.csv")


@app.get("/jobs/{job_id}/trades.csv")
def trades_csv(job_id: JobId) -> FileResponse:
    return FileResponse(_job_file(job_id, "trades.csv"), media_type="text/csv", filename=f"{job_id}_trades.csv")
