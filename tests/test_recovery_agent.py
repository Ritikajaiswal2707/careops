import pandas as pd
import pytest
from fastapi.testclient import TestClient

import main
from capacity_recovery import UnknownAppointmentError
from recovery_agent import run_recovery_agent


@pytest.fixture
def def_data():
    # Keep tests grounded in the repository's bundled synthetic records.
    from recovery_agent import _load_data
    return _load_data()


def test_agent_escalates_ambiguous_message_without_guessing(def_data):
    result = run_recovery_agent(
        "APT004512", "Maybe, I will see", llm_call=None, data=def_data
    )
    assert result["status"] == "needs_human_review"
    assert result["escalate_to_human"] is True
    assert result["proposal"] is None
    assert [item["tool"] for item in result["tool_trace"]] == [
        "lookup_appointment", "interpret_disruption"
    ]


def test_agent_routes_non_reschedule_intent_without_searching(def_data):
    result = run_recovery_agent(
        "APT004512", "Cancel my visit", llm_call=None, data=def_data
    )
    assert result["status"] == "unsupported_intent"
    assert result["proposal"] is None
    assert len(result["tool_trace"]) == 2


def test_agent_returns_approval_gated_proposal_when_candidate_exists(def_data):
    def fake_builder(_date):
        return {"cand": pd.DataFrame({"available_today": [True]})}

    def fake_recommender(_appointment_id, _date, _ctx, service_type=None, top_n=1):
        assert top_n == 3
        return [{
            "provider_id": "PR019",
            "area": "Test Area",
            "remaining_capacity": 2,
            "score": 42.5,
            "reasons": ["eligible synthetic test candidate"],
        }]

    result = run_recovery_agent(
        "APT004512",
        "Can we reschedule this visit to Saturday?",
        llm_call=None,
        data=def_data,
        candidate_builder=fake_builder,
        recommender=fake_recommender,
    )
    assert result["status"] == "awaiting_coordinator_approval"
    assert result["proposal"]["provider_id"] == "PR019"
    assert result["proposal"]["state"] == "PROPOSED"
    assert result["proposal"]["approval_required"] is True
    assert result["simulated"] is True
    assert result["tool_trace"][-1]["tool"] == "search_recovery_options"
    assert "booking" not in str(result).lower() or result["proposal"] is not None


def test_agent_rejects_unknown_appointment_before_parsing():
    with pytest.raises(UnknownAppointmentError):
        run_recovery_agent("APT999999", "Can we reschedule this visit?", llm_call=None)


def test_agent_api_exposes_tool_trace_and_does_not_claim_real_booking(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    client = TestClient(main.app)
    response = client.post("/api/agent/run", json={
        "appointment_id": "APT004512",
        "message": "Maybe, I will see",
    })
    assert response.status_code == 200
    payload = response.json()
    assert payload["simulated"] is True
    assert payload["status"] == "needs_human_review"
    assert payload["proposal"] is None
    assert all("tool" in step and "status" in step for step in payload["tool_trace"])


def test_agent_api_rejects_unknown_appointment():
    client = TestClient(main.app)
    response = client.post("/api/agent/run", json={
        "appointment_id": "APT999999",
        "message": "Can we reschedule this visit?",
    })
    assert response.status_code == 404


def test_agent_real_synthetic_path_returns_proposal_when_feasible():
    # Known case in the bundled synthetic dataset; no external LLM key is used.
    result = run_recovery_agent(
        "APT009737", "Doctor visit hai usi din, reschedule possible?", llm_call=None
    )
    assert result["status"] == "awaiting_coordinator_approval"
    assert result["proposal"]["state"] == "PROPOSED"
    assert result["proposal"]["approval_required"] is True
    assert result["proposal"]["provider_id"]
    assert result["simulated"] is True


def test_agent_fails_closed_when_recovery_tool_raises(def_data):
    def broken_builder(_date):
        raise RuntimeError("synthetic tool outage")

    result = run_recovery_agent(
        "APT004512",
        "Can we reschedule this visit to Saturday?",
        llm_call=None,
        data=def_data,
        candidate_builder=broken_builder,
    )
    assert result["status"] == "needs_human_review"
    assert result["escalate_to_human"] is True
    assert result["proposal"] is None
    assert result["tool_trace"][-1]["tool"] == "search_recovery_options"
    assert result["tool_trace"][-1]["status"] == "error"
    assert "synthetic tool outage" not in str(result)
