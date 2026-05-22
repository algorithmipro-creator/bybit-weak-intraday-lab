from __future__ import annotations

import datetime as dt
from pathlib import Path

from bybit_weak_intraday import archive
from bybit_weak_intraday.archive import download_archive_file, download_archive_file_result


class FakeResponse:
    def __init__(self, *, status_code: int = 200, chunks: list[bytes] | None = None):
        self.status_code = status_code
        self._chunks = chunks or [b"timestamp,symbol,side,size,price,foreignNotional\n"]

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def iter_content(self, chunk_size: int):
        yield from self._chunks


class FakeSession:
    def __init__(self, response: FakeResponse):
        self.response = response
        self.calls = []

    def get(self, url: str, *, stream: bool, timeout: int):
        self.calls.append({"url": url, "stream": stream, "timeout": timeout})
        return self.response


class SequencedSession:
    def __init__(self, responses: list[FakeResponse]):
        self.responses = responses
        self.calls = []

    def get(self, url: str, *, stream: bool, timeout: int):
        self.calls.append({"url": url, "stream": stream, "timeout": timeout})
        return self.responses.pop(0)


def test_download_archive_file_result_reports_cache_hit_without_network(tmp_path: Path) -> None:
    out = archive.cache_path(tmp_path, "ENAUSDT", dt.date(2026, 3, 18))
    out.parent.mkdir(parents=True)
    out.write_bytes(b"cached")
    session = FakeSession(FakeResponse())

    result = download_archive_file_result(session, "ENAUSDT", dt.date(2026, 3, 18), tmp_path, sleep=0)

    assert result.path == out
    assert result.status == "cache_hit"
    assert result.warning is None
    assert result.error is None
    assert session.calls == []


def test_download_archive_file_result_uses_unique_temp_paths(monkeypatch, tmp_path: Path) -> None:
    generated: list[Path] = []

    def fake_tmp_path(out: Path) -> Path:
        tmp = out.with_name(f"{out.name}.{len(generated)}.tmp")
        generated.append(tmp)
        return tmp

    monkeypatch.setattr(archive, "_unique_tmp_path", fake_tmp_path)
    session = FakeSession(FakeResponse(chunks=[b"abc"]))

    first = download_archive_file_result(session, "ENAUSDT", dt.date(2026, 3, 18), tmp_path, sleep=0)
    out = archive.cache_path(tmp_path, "ENAUSDT", dt.date(2026, 3, 18))
    out.unlink()
    second = download_archive_file_result(session, "ENAUSDT", dt.date(2026, 3, 18), tmp_path, sleep=0)

    assert first.status == "downloaded"
    assert second.status == "downloaded"
    assert generated[0] != generated[1]
    assert all(not path.exists() for path in generated)


def test_download_archive_file_result_reports_missing_on_404(tmp_path: Path) -> None:
    result = download_archive_file_result(
        FakeSession(FakeResponse(status_code=404)),
        "ENAUSDT",
        dt.date(2026, 3, 18),
        tmp_path,
        sleep=0,
    )

    assert result.path is None
    assert result.status == "missing"
    assert result.error is None


def test_download_archive_file_result_does_not_fail_on_temp_cleanup_error(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(archive, "_safe_unlink", lambda path: "locked temp file")

    result = download_archive_file_result(
        FakeSession(FakeResponse(status_code=500)),
        "ENAUSDT",
        dt.date(2026, 3, 18),
        tmp_path,
        retries=1,
        sleep=0,
    )

    assert result.path is None
    assert result.status == "error"
    assert result.warning == "locked temp file"
    assert "HTTP 500" in str(result.error)


def test_download_archive_file_result_preserves_prior_cleanup_warning_after_retry_success(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(archive, "_safe_unlink", lambda path: "locked temp file")
    monkeypatch.setattr(archive.time, "sleep", lambda seconds: None)
    session = SequencedSession([FakeResponse(status_code=500), FakeResponse(chunks=[b"abc"])])

    result = download_archive_file_result(
        session,
        "ENAUSDT",
        dt.date(2026, 3, 18),
        tmp_path,
        retries=2,
        sleep=0,
    )

    assert result.path == archive.cache_path(tmp_path, "ENAUSDT", dt.date(2026, 3, 18))
    assert result.status == "downloaded"
    assert result.warning == "locked temp file"
    assert result.error is None


def test_download_archive_file_keeps_path_or_none_compatibility(tmp_path: Path) -> None:
    path = download_archive_file(
        FakeSession(FakeResponse(chunks=[b"abc"])),
        "ENAUSDT",
        dt.date(2026, 3, 18),
        tmp_path,
        sleep=0,
    )

    assert path == archive.cache_path(tmp_path, "ENAUSDT", dt.date(2026, 3, 18))
