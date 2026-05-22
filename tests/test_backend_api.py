from __future__ import annotations

import json

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.app import main
from backend.app import job_store
from backend.app.job_store import job_dir


client = TestClient(main.app)


@pytest.fixture(autouse=True)
def prevent_real_scan_jobs(monkeypatch):
    captured: dict = {}

    def fake_create_job(payload, job_type="scan"):
        captured["payload"] = payload
        captured["job_type"] = job_type
        return "abc123def456"

    class FakeExecutor:
        def submit(self, fn, job_id):
            captured["submitted"] = (fn, job_id)

    monkeypatch.setattr(main, "create_job", fake_create_job)
    monkeypatch.setattr(main, "executor", FakeExecutor())
    return captured


def _scan_payload(**overrides):
    payload = {
        "start": "2026-03-18",
        "end": "2026-03-18",
        "symbols": ["enausdt"],
        "full_universe": False,
        "min_turnover": 1_000_000,
        "weak_threshold": 9,
        "pump_threshold": 9,
        "tp_weak": 0.06,
        "sl_weak": 0.07,
        "tp_pump": 0.08,
        "sl_pump": 0.07,
        "max_hold_min": 720,
    }
    payload.update(overrides)
    return payload


def test_health_returns_ok():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_scan_rejects_reversed_dates():
    response = client.post("/jobs/scan", json=_scan_payload(start="2026-03-20", end="2026-03-18"))

    assert response.status_code == 422


def test_scan_rejects_too_large_regular_range():
    response = client.post("/jobs/scan", json=_scan_payload(start="2026-01-01", end="2026-02-15"))

    assert response.status_code == 422


def test_scan_rejects_full_universe_without_max_symbols():
    response = client.post(
        "/jobs/scan",
        json=_scan_payload(symbols=[], full_universe=True, start="2026-03-18", end="2026-03-20", max_symbols=0),
    )

    assert response.status_code == 422


def test_invalid_job_id_path_is_rejected():
    response = client.get("/jobs/not-a-job")

    assert response.status_code == 422


def test_job_dir_rejects_path_traversal():
    with pytest.raises(ValueError):
        job_dir("../outside")


def test_recover_interrupted_jobs_marks_stale_active_jobs_as_error(monkeypatch, tmp_path):
    monkeypatch.setattr(job_store.settings, "jobs_dir", tmp_path)
    running_dir = tmp_path / "111111111111"
    queued_dir = tmp_path / "222222222222"
    done_dir = tmp_path / "333333333333"
    for directory in (running_dir, queued_dir, done_dir):
        directory.mkdir(parents=True)
    (running_dir / "meta.json").write_text(
        json.dumps({"job_id": "111111111111", "status": "running", "message": "scan running"}),
        encoding="utf-8",
    )
    (queued_dir / "meta.json").write_text(
        json.dumps({"job_id": "222222222222", "status": "queued", "message": "queued"}),
        encoding="utf-8",
    )
    (done_dir / "meta.json").write_text(
        json.dumps({"job_id": "333333333333", "status": "done", "message": "scan complete"}),
        encoding="utf-8",
    )

    recovered = job_store.recover_interrupted_jobs()

    assert recovered == 2
    running_meta = json.loads((running_dir / "meta.json").read_text(encoding="utf-8"))
    queued_meta = json.loads((queued_dir / "meta.json").read_text(encoding="utf-8"))
    done_meta = json.loads((done_dir / "meta.json").read_text(encoding="utf-8"))
    assert running_meta["status"] == "error"
    assert queued_meta["status"] == "error"
    assert running_meta["message"] == "job interrupted by backend restart"
    assert queued_meta["message"] == "job interrupted by backend restart"
    assert done_meta["status"] == "done"


def test_valid_scan_queues_normalized_symbols(prevent_real_scan_jobs):
    response = client.post("/jobs/scan", json=_scan_payload(symbols=["enausdt", " JTOUSDT "]))

    assert response.status_code == 200
    assert response.json()["job_id"] == "abc123def456"
    assert prevent_real_scan_jobs["payload"]["symbols"] == ["ENAUSDT", "JTOUSDT"]
    assert prevent_real_scan_jobs["job_type"] == "scan"
    assert prevent_real_scan_jobs["submitted"][1] == "abc123def456"


def test_valid_causal_scan_queues_normalized_symbols(prevent_real_scan_jobs):
    response = client.post("/jobs/scan-causal", json=_scan_payload(symbols=["enausdt", " jtoUSDT "]))

    assert response.status_code == 200
    assert response.json()["job_id"] == "abc123def456"
    assert prevent_real_scan_jobs["payload"]["symbols"] == ["ENAUSDT", "JTOUSDT"]
    assert prevent_real_scan_jobs["job_type"] == "causal_scan"
    assert prevent_real_scan_jobs["submitted"][1] == "abc123def456"


def test_causal_scan_rejects_empty_symbols_without_full_universe():
    response = client.post("/jobs/scan-causal", json=_scan_payload(symbols=[]))

    assert response.status_code == 400


def test_optimizer_rejects_empty_tp_grid():
    response = client.post("/jobs/optimize-tp-sl", json={**_scan_payload(), "tp_grid": [], "sl_grid": [0.07]})

    assert response.status_code == 422


def test_valid_optimizer_queues_grid_job(prevent_real_scan_jobs):
    response = client.post(
        "/jobs/optimize-tp-sl",
        json={**_scan_payload(symbols=["enausdt"]), "tp_grid": [0.04, 0.06], "sl_grid": [0.05, 0.07]},
    )

    assert response.status_code == 200
    assert response.json()["job_id"] == "abc123def456"
    assert prevent_real_scan_jobs["job_type"] == "tp_sl_grid"
    assert prevent_real_scan_jobs["payload"]["tp_grid"] == [0.04, 0.06]
    assert prevent_real_scan_jobs["payload"]["sl_grid"] == [0.05, 0.07]


def test_done_causal_job_exposes_signal_and_evaluation_urls(monkeypatch):
    monkeypatch.setattr(
        main,
        "load_meta",
        lambda job_id: {
            "job_id": job_id,
            "job_type": "causal_scan",
            "status": "done",
            "signals_rows": 3,
            "evaluations_rows": 3,
            "message": "causal scan complete",
        },
    )

    response = client.get("/jobs/abc123def456")

    assert response.status_code == 200
    assert response.json()["signals_url"] == "/jobs/abc123def456/signals.csv"
    assert response.json()["evaluations_url"] == "/jobs/abc123def456/evaluations.csv"


def test_run_job_persists_progress_and_warnings(monkeypatch, tmp_path):
    monkeypatch.setattr(job_store.settings, "jobs_dir", tmp_path)
    monkeypatch.setattr(job_store.settings, "cache_dir", tmp_path / "cache")

    job_id = job_store.create_job(_scan_payload(symbols=["ENAUSDT"]))

    def fake_run_archive_scan(**kwargs):
        kwargs["progress_callback"](
            {
                "processed": 1,
                "total": 1,
                "current_symbol": "ENAUSDT",
                "current_date": "2026-03-18",
                "cache_hits": 1,
                "downloads": 1,
                "missing_files": 0,
                "errors": 0,
                "message": "scanning ENAUSDT 2026-03-18",
                "warnings": [
                    {"symbol": "ENAUSDT", "date": "2026-03-18", "message": "locked temp cleanup skipped"}
                ],
            }
        )
        return pd.DataFrame([{"symbol": "ENAUSDT"}]), pd.DataFrame()

    monkeypatch.setattr(job_store, "run_archive_scan", fake_run_archive_scan)

    job_store.run_job(job_id)

    meta = job_store.load_meta(job_id)
    assert meta["status"] == "done"
    assert meta["progress"] == {
        "processed": 1,
        "total": 1,
        "current_symbol": "ENAUSDT",
        "current_date": "2026-03-18",
        "cache_hits": 1,
        "downloads": 1,
        "missing_files": 0,
        "errors": 0,
    }
    assert meta["message"] == "scan complete"
    assert meta["warnings"] == [
        {"symbol": "ENAUSDT", "date": "2026-03-18", "message": "locked temp cleanup skipped"}
    ]


def test_run_job_deduplicates_progress_warnings(monkeypatch, tmp_path):
    monkeypatch.setattr(job_store.settings, "jobs_dir", tmp_path)
    monkeypatch.setattr(job_store.settings, "cache_dir", tmp_path / "cache")

    job_id = job_store.create_job(_scan_payload(symbols=["ENAUSDT"]))
    warning = {"symbol": "ENAUSDT", "date": "2026-03-18", "message": "locked temp cleanup skipped"}

    def fake_run_archive_scan(**kwargs):
        kwargs["progress_callback"]({"warnings": [warning, warning]})
        kwargs["progress_callback"]({"warnings": [warning]})
        return pd.DataFrame(), pd.DataFrame()

    monkeypatch.setattr(job_store, "run_archive_scan", fake_run_archive_scan)

    job_store.run_job(job_id)

    meta = job_store.load_meta(job_id)
    assert meta["warnings"] == [warning]


def test_run_causal_job_receives_progress_callback(monkeypatch, tmp_path):
    monkeypatch.setattr(job_store.settings, "jobs_dir", tmp_path)
    monkeypatch.setattr(job_store.settings, "cache_dir", tmp_path / "cache")

    job_id = job_store.create_job(_scan_payload(symbols=["ENAUSDT"]), job_type="causal_scan")

    def fake_run_archive_causal_scan_outputs(**kwargs):
        assert kwargs["progress_callback"] is not None
        kwargs["progress_callback"]({"processed": 1, "total": 1, "message": "causal progress"})
        return pd.DataFrame([{"symbol": "ENAUSDT"}]), pd.DataFrame()

    monkeypatch.setattr(job_store, "run_archive_causal_scan_outputs", fake_run_archive_causal_scan_outputs)

    job_store.run_job(job_id)

    meta = job_store.load_meta(job_id)
    assert meta["status"] == "done"
    assert meta["progress"]["processed"] == 1


def test_run_grid_job_receives_progress_callback(monkeypatch, tmp_path):
    monkeypatch.setattr(job_store.settings, "jobs_dir", tmp_path)
    monkeypatch.setattr(job_store.settings, "cache_dir", tmp_path / "cache")

    job_id = job_store.create_job(
        {**_scan_payload(symbols=["ENAUSDT"]), "tp_grid": [0.04], "sl_grid": [0.05]},
        job_type="tp_sl_grid",
    )

    def fake_run_archive_tp_sl_grid(**kwargs):
        assert kwargs["progress_callback"] is not None
        kwargs["progress_callback"]({"processed": 1, "total": 1, "message": "grid progress"})
        return pd.DataFrame([{"tp": 0.04, "sl": 0.05}]), pd.DataFrame()

    monkeypatch.setattr(job_store, "run_archive_tp_sl_grid", fake_run_archive_tp_sl_grid)

    job_store.run_job(job_id)

    meta = job_store.load_meta(job_id)
    assert meta["status"] == "done"
    assert meta["progress"]["processed"] == 1
