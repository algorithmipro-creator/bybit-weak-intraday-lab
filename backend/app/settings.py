from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    project_name: str = "Bybit Weak Intraday Lab"
    data_dir: Path = Path("/app/data")
    cache_dir: Path = Path("/app/data/bybit_archive_cache")
    jobs_dir: Path = Path("/app/data/jobs")
    max_workers: int = 2
    cors_origins: str = "*"

    class Config:
        env_file = ".env"
        env_prefix = "BWI_"


settings = Settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)
settings.cache_dir.mkdir(parents=True, exist_ok=True)
settings.jobs_dir.mkdir(parents=True, exist_ok=True)
