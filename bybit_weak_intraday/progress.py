from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .archive import ArchiveDownloadResult

ProgressCallback = Callable[[dict[str, Any]], None]


@dataclass
class ProgressState:
    total: int
    processed: int = 0
    cache_hits: int = 0
    downloads: int = 0
    missing_files: int = 0
    errors: int = 0

    def add_archive_result(self, result: ArchiveDownloadResult) -> None:
        if result.status == "cache_hit":
            self.cache_hits += 1
        elif result.status == "downloaded":
            self.downloads += 1
        elif result.status == "missing":
            self.missing_files += 1
        elif result.status == "error":
            self.errors += 1

    def advance(self, symbol: str, date: str, *, message: str | None = None) -> dict[str, Any]:
        self.processed += 1
        status_message = message or f"scanning {symbol} {date}"
        return {
            "processed": self.processed,
            "total": self.total,
            "current_symbol": symbol,
            "current_date": date,
            "cache_hits": self.cache_hits,
            "downloads": self.downloads,
            "missing_files": self.missing_files,
            "errors": self.errors,
            "message": status_message,
        }

    def warnings_for_results(
        self,
        symbol: str,
        date: str,
        results: list[ArchiveDownloadResult],
    ) -> list[dict[str, str]]:
        warnings: list[dict[str, str]] = []
        for result in results:
            if result.status == "missing":
                warnings.append({"symbol": symbol, "date": date, "message": "archive file missing"})
            elif result.status == "error":
                message = result.error or "archive download failed"
                if result.warning:
                    message = f"{message}; {result.warning}"
                warnings.append({"symbol": symbol, "date": date, "message": message})
            elif result.warning:
                warnings.append({"symbol": symbol, "date": date, "message": result.warning})
        return warnings
