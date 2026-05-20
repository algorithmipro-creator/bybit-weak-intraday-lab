from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


MAX_SCAN_DAYS = 31
MAX_FULL_UNIVERSE_DAYS = 7
MAX_REQUEST_SYMBOLS = 500


class ScanRequest(BaseModel):
    start: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    end: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    symbols: list[str] = Field(default_factory=list, max_length=MAX_REQUEST_SYMBOLS)
    full_universe: bool = False
    include_majors: bool = False
    max_symbols: int = Field(0, ge=0, le=MAX_REQUEST_SYMBOLS)
    min_turnover: float = Field(1_000_000, ge=0)
    weak_threshold: int = Field(9, ge=0, le=20)
    pump_threshold: int = Field(9, ge=0, le=20)
    tp_weak: float = Field(0.06, gt=0, le=1)
    sl_weak: float = Field(0.07, gt=0, le=1)
    tp_pump: float = Field(0.08, gt=0, le=1)
    sl_pump: float = Field(0.07, gt=0, le=1)
    max_hold_min: float = Field(720, gt=0, le=1440)

    @field_validator("symbols")
    @classmethod
    def normalize_symbols(cls, symbols: list[str]) -> list[str]:
        return [s.upper().strip() for s in symbols if s.strip()]

    @model_validator(mode="after")
    def validate_scan_limits(self) -> "ScanRequest":
        start_date = datetime.strptime(self.start, "%Y-%m-%d").date()
        end_date = datetime.strptime(self.end, "%Y-%m-%d").date()
        if end_date < start_date:
            raise ValueError("end must be greater than or equal to start")

        days = (end_date - start_date).days + 1
        max_days = MAX_FULL_UNIVERSE_DAYS if self.full_universe else MAX_SCAN_DAYS
        if days > max_days:
            raise ValueError(f"scan range must be {max_days} days or less")

        if self.full_universe and self.max_symbols <= 0:
            raise ValueError("full_universe scans must set max_symbols between 1 and 500")

        return self


class JobResponse(BaseModel):
    job_id: str
    status: Literal["queued", "running", "done", "error"]
    message: str | None = None
    metrics_rows: int | None = None
    trades_rows: int | None = None
    metrics_url: str | None = None
    trades_url: str | None = None
