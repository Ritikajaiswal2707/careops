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


def test_root_serves_dashboard_and_synthetic_data_disclosure():
    response = client.get("/")
    assert response.status_code == 200
    assert "<title>CareOps · AI operations copilot for home healthcare</title>" in response.text
    assert "og:image" in response.text  # link previews on LinkedIn and in email
    # The header line was removed in the redesign; the page must still disclose synthetic data.
    assert "Synthetic data from a simulated home-care operation" in response.text
    assert "Not for clinical use" in response.text


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
    assert "Fix a visit" in html
    assert "Find a replacement" in html
    assert "Run recovery agent" not in html
    assert "Legacy reschedule flow" not in html
    assert "data.trace.map(l => `· ${l}`)" not in html


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


def _dashboard_source():
    """The page is split into index.html (markup and generated data) and app.js (behaviour)."""
    root = Path(__file__).resolve().parents[1] / "dashboard"
    return "\n".join((root / name).read_text(encoding="utf-8") for name in ("index.html", "app.js", "styles.css"))


def test_dashboard_escapes_untrusted_trace_strings():
    html = _dashboard_source()
    assert "function escapeHtml(value)" in html
    assert "${escapeHtml(e.message)}" in html
    assert "This public demo can recommend a fix, but cannot record an approval or change a schedule." in html
    assert "CareOps could not complete that request." in html


def test_public_read_only_mode_blocks_agent_case_mutations(monkeypatch):
    monkeypatch.setenv("CAREOPS_PUBLIC_DEMO_READ_ONLY", "true")
    run_response = client.post("/api/agent/run", json={
        "appointment_id": "APT004512", "message": "Can we reschedule for tomorrow?"
    })
    decision_response = client.post("/api/agent/cases/CASE-DOESNOTEXIST/decision", json={"decision": "approve"})
    execute_response = client.post("/api/agent/cases/CASE-DOESNOTEXIST/execute")
    get_response = client.get("/api/agent/cases/CASE-DOESNOTEXIST")
    assert run_response.status_code == 403
    assert decision_response.status_code == 403
    assert execute_response.status_code == 403
    assert get_response.status_code == 403


def test_external_llm_can_be_disabled_for_public_demo(monkeypatch):
    from hybrid_extraction import default_llm_call
    monkeypatch.setenv("CAREOPS_DISABLE_EXTERNAL_LLM", "true")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-must-not-be-used")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-must-not-be-used")
    assert default_llm_call("please reschedule") is None


def test_dashboard_never_marks_unassigned_visit_as_handled():
    html = client.get("/").text + client.get("/app.js").text
    assert client.get("/app.js").status_code == 200 and client.get("/styles.css").status_code == 200
    # Trust rules from coordinator walkthroughs: an escalated visit stays unassigned,
    # and a nurse is told only after the family agrees.
    assert "Marked as handled" not in html
    assert "Escalated · unassigned" in html
    assert "She is not told yet" in html
    assert "Already confirmed by the family" in html


def test_nurse_day_lists_one_nurses_visits_read_only():
    response = client.get("/api/nurse-day/PR016")
    assert response.status_code == 200
    body = response.json()
    assert body["provider_id"] == "PR016" and body["visits"]
    assert all(v["appointment_id"].startswith("APT") for v in body["visits"])
    assert client.get("/api/nurse-day/PR999").status_code == 404
    assert client.get("/api/nurse-day/../x").status_code in (404, 422)


def test_dashboard_separates_operator_view_from_demo_notes():
    html = client.get("/").text + client.get("/app.js").text + client.get("/styles.css").text
    # Visitor-only framing is marked so the coordinator's view can hide it.
    assert 'class="demo-banner visitor"' in html and 'class="visitor pitch"' in html
    assert "body.operator .visitor{display:none" in html
    assert "See the coordinator's view" in html and "Show demo notes" in html
    # The operator's first line is today's work, not a product description.
    assert 'id="today-line"' in html and "families wrote in" in html


def test_dashboard_keeps_progress_and_finishes_reminders():
    js = client.get("/app.js").text
    # A refresh must not wipe a coordinator's morning.
    assert "careops-progress-v1" in js and "function loadProgress" in js and "function clearProgress" in js
    # Reminders can be finished, and acted-on visits are grouped apart from the to-do list.
    assert "Family confirmed" in js and "No reply" in js
    assert "Waiting on someone else" in js
