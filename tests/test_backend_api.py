from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app import main
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


def test_done_causal_job_exposes_signals_url(monkeypatch):
    monkeypatch.setattr(
        main,
        "load_meta",
        lambda job_id: {
            "job_id": job_id,
            "job_type": "causal_scan",
            "status": "done",
            "signals_rows": 3,
            "message": "causal scan complete",
        },
    )

    response = client.get("/jobs/abc123def456")

    assert response.status_code == 200
    assert response.json()["signals_url"] == "/jobs/abc123def456/signals.csv"
