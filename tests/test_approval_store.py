import pytest
from fastapi.testclient import TestClient

import main
from approval_store import CaseConflictError, CaseNotFoundError, create_case, decide_case, get_case


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setenv("CAREOPS_DB_PATH", str(tmp_path / "cases.sqlite3"))


def sample_result():
    return {
        "appointment_id": "APT004512",
        "agent_version": "test",
        "approval_required": True,
        "proposal": {
            "appointment_id": "APT004512", "provider_id": "PR019",
            "new_date": "2026-08-30", "approval_required": True,
        },
    }


def test_create_case_persists_proposal_and_audit_event():
    case = create_case(sample_result())
    assert case["status"] == "pending_approval"
    assert case["booking_executed"] is False
    assert case["proposal"]["provider_id"] == "PR019"
    assert [e["event_type"] for e in case["events"]] == ["proposal_created"]
    assert get_case(case["case_id"])["case_id"] == case["case_id"]


def test_decision_is_persisted_and_approval_does_not_book():
    case = create_case(sample_result())
    decided = decide_case(case["case_id"], "approve", "Looks feasible")
    assert decided["status"] == "approved"
    assert decided["booking_executed"] is False
    assert decided["decision_note"] == "Looks feasible"
    assert decided["events"][-1]["event_type"] == "proposal_approved"


def test_same_decision_is_idempotent_and_opposite_decision_conflicts():
    case = create_case(sample_result())
    case_id = case["case_id"]
    first = decide_case(case_id, "reject", "No suitable fit")
    second = decide_case(case_id, "reject", "No suitable fit")
    assert len(first["events"]) == len(second["events"]) == 2
    with pytest.raises(CaseConflictError):
        decide_case(case_id, "approve")


def test_unknown_case_raises_not_found():
    with pytest.raises(CaseNotFoundError):
        get_case("CASE-DOES-NOT-EXIST")


def test_api_run_returns_case_id_and_decision_endpoints(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    client = TestClient(main.app)
    response = client.post("/api/agent/run", json={
        "appointment_id": "APT009737", "message": "Can we reschedule this visit?"
    })
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["case_id"].startswith("CASE-")
    assert payload["booking_executed"] is False
    case_response = client.get(f"/api/agent/cases/{payload['case_id']}")
    assert case_response.status_code == 200
    decision = client.post(f"/api/agent/cases/{payload['case_id']}/decision", json={
        "decision": "approve", "note": "Coordinator reviewed synthetic proposal"
    })
    assert decision.status_code == 200, decision.text
    assert decision.json()["status"] == "approved"
    assert decision.json()["booking_executed"] is False


def test_api_unknown_case_and_conflicting_decision(monkeypatch):
    client = TestClient(main.app)
    assert client.get("/api/agent/cases/CASE-UNKNOWN").status_code == 404
    response = client.post("/api/agent/cases/CASE-UNKNOWN/decision", json={"decision": "approve"})
    assert response.status_code == 404
