from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ScanRequest(BaseModel):
    start: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    end: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    symbols: list[str] = Field(default_factory=list)
    full_universe: bool = False
    include_majors: bool = False
    max_symbols: int = Field(0, ge=0, le=2000)
    min_turnover: float = Field(1_000_000, ge=0)
    weak_threshold: int = Field(9, ge=0, le=20)
    pump_threshold: int = Field(9, ge=0, le=20)
    tp_weak: float = Field(0.06, gt=0, le=1)
    sl_weak: float = Field(0.07, gt=0, le=1)
    tp_pump: float = Field(0.08, gt=0, le=1)
    sl_pump: float = Field(0.07, gt=0, le=1)
    max_hold_min: float = Field(720, gt=0, le=1440)


class JobResponse(BaseModel):
    job_id: str
    status: Literal["queued", "running", "done", "error"]
    message: str | None = None
    metrics_rows: int | None = None
    trades_rows: int | None = None
    metrics_url: str | None = None
    trades_url: str | None = None
