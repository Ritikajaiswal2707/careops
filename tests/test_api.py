import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import main

client = TestClient(main.app)


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["mode"] == "synthetic-demo"


def test_root_serves_dashboard_and_simulation_label():
    response = client.get("/")
    assert response.status_code == 200
    assert "CareOps Daily Simulation" in response.text
    assert "not live operations data" in response.text


def test_operations_endpoint_returns_fixed_snapshot():
    response = client.get("/api/operations")
    assert response.status_code == 200
    payload = response.json()
    assert payload["today"] == "2026-08-29"
    assert payload["summary"]["total"] == 95


def test_blank_analyze_message_is_rejected_without_echo():
    response = client.post("/api/analyze", json={"message": "   "})
    assert response.status_code == 422
    assert "input" not in response.text


def test_script_like_reschedule_message_is_safe_for_dashboard_rendering(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    message = "Maybe later <script>alert(1)</script>"
    response = client.post("/api/reschedule", json={
        "appointment_id": "APT004512", "message": message
    })
    assert response.status_code == 200
    assert message in response.text
    html = (Path(__file__).resolve().parents[1] / "dashboard" / "index.html").read_text(encoding="utf-8")
    assert "data.trace : []).map(l => `· ${escapeHtml(l)}`)" in html
    assert "${data.trace.map(l => `· ${l}`)" not in html


def test_oversized_message_is_rejected_without_echo():
    message = "X" * (main.MAX_MESSAGE_LENGTH + 1)
    response = client.post("/api/analyze", json={"message": message})
    assert response.status_code == 422
    assert message not in response.text


def test_analyze_returns_structured_signal_without_external_keys(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    response = client.post("/api/analyze", json={"message": "Haan theek hai, confirm kar do"})
    assert response.status_code == 200
    assert response.json()["intent"] == "Confirm"
    assert response.json()["source"] == "rule"


def test_invalid_date_format_returns_422():
    response = client.post("/api/recover", json={
        "appointment_id": "APT004512", "target_date": "29-08-2026"
    })
    assert response.status_code == 422


def test_out_of_range_date_returns_422():
    response = client.post("/api/recover", json={
        "appointment_id": "APT004512", "target_date": "2027-01-01"
    })
    assert response.status_code == 422


def test_unknown_appointment_returns_404_without_echo():
    response = client.post("/api/recover", json={
        "appointment_id": "APT999999", "target_date": "2026-08-29"
    })
    assert response.status_code == 404
    assert "APT999999" not in response.text


def test_bad_appointment_id_format_returns_422():
    response = client.post("/api/recover", json={
        "appointment_id": "<script>", "target_date": "2026-08-29"
    })
    assert response.status_code == 422
    assert "<script>" not in response.text


def test_recover_known_appointment_returns_candidates_list():
    response = client.post("/api/recover", json={
        "appointment_id": "APT004512", "target_date": "2026-08-29",
        "service_type": "Wound Dressing"
    })
    assert response.status_code == 200
    payload = response.json()
    assert payload["appointment_id"] == "APT004512"
    assert payload["simulated"] is True
    assert isinstance(payload["candidates"], list)


def test_reschedule_unknown_appointment_returns_404():
    response = client.post("/api/reschedule", json={
        "appointment_id": "APT999999", "message": "Can we reschedule?"
    })
    assert response.status_code == 404


def test_reschedule_rejects_blank_and_long_messages():
    blank = client.post("/api/reschedule", json={
        "appointment_id": "APT004512", "message": "   "
    })
    long = client.post("/api/reschedule", json={
        "appointment_id": "APT004512", "message": "x" * (main.MAX_MESSAGE_LENGTH + 1)
    })
    assert blank.status_code == 422
    assert long.status_code == 422
    assert "x" * 200 not in long.text


def test_dashboard_escapes_untrusted_trace_strings():
    html = (Path(__file__).resolve().parents[1] / "dashboard" / "index.html").read_text(encoding="utf-8")
    assert "function escapeHtml(value)" in html
    assert "${escapeHtml(e.message)}" in html
    assert "${escapeHtml((data && data.detail) || res.statusText)}" in html
