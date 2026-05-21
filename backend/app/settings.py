from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from bybit_weak_intraday.execution.safety import DEMO_BASE_URL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="BWI_")

    project_name: str = "Bybit Weak Intraday Lab"
    data_dir: Path = Path("/app/data")
    cache_dir: Path = Path("/app/data/bybit_archive_cache")
    jobs_dir: Path = Path("/app/data/jobs")
    max_workers: int = 1
    cors_origins: str = "*"
    execution_mode: str = "disabled"
    execution_enabled: bool = False
    bybit_demo_api_key: str = ""
    bybit_demo_api_secret: str = ""
    bybit_demo_base_url: str = DEMO_BASE_URL
    execution_symbol_whitelist: str = "ENAUSDT,JTOUSDT"
    max_demo_notional_usdt: float = 25.0
    max_open_positions: int = 1
    max_daily_test_orders: int = 3
    execution_journal_path: Path = Path("/app/data/execution_journal.csv")
    execution_api_token: str = ""


settings = Settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)
settings.cache_dir.mkdir(parents=True, exist_ok=True)
settings.jobs_dir.mkdir(parents=True, exist_ok=True)
