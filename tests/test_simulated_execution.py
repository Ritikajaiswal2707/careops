import pytest
from fastapi.testclient import TestClient

import main
from approval_store import CaseConflictError, create_case, decide_case, get_case
from simulated_execution import RevalidationError, execute_approved_case


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setenv("CAREOPS_DB_PATH", str(tmp_path / "execution.sqlite3"))


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


def validator(proposal):
    return {
        "appointment_id": proposal["appointment_id"],
        "provider_id": proposal["provider_id"],
        "target_date": proposal["new_date"],
        "eligibility_revalidated": True,
        "execution_mode": "simulation_only",
    }


def test_execution_requires_approval():
    case = create_case(sample_result())
    with pytest.raises(CaseConflictError):
        execute_approved_case(case["case_id"], validator=validator)


def test_approved_case_is_revalidated_and_simulated_once():
    case = create_case(sample_result())
    decide_case(case["case_id"], "approve", "reviewed")
    first = execute_approved_case(case["case_id"], validator=validator)
    second = execute_approved_case(case["case_id"], validator=validator)
    assert first["workflow_status"] == "simulated_resolved"
    assert first["booking_executed"] is False
    assert first["simulated_execution"]["simulated"] is True
    assert first["simulated_execution"]["execution_id"] == second["simulated_execution"]["execution_id"]
    assert [e["event_type"] for e in second["events"]].count("simulated_recovery_executed") == 1


def test_revalidation_failure_does_not_record_execution():
    case = create_case(sample_result())
    decide_case(case["case_id"], "approve")
    def fail(_proposal):
        raise RevalidationError("No eligible provider")
    with pytest.raises(RevalidationError):
        execute_approved_case(case["case_id"], validator=fail)
    stored = get_case(case["case_id"])
    assert stored["simulated_execution"] is None
    assert "simulated_recovery_executed" not in [e["event_type"] for e in stored["events"]]


def test_revalidation_must_match_approved_proposal():
    case = create_case(sample_result())
    decide_case(case["case_id"], "approve")
    wrong_provider = lambda _proposal: {
        "appointment_id": "APT004512", "provider_id": "PR999",
        "target_date": "2026-08-30", "eligibility_revalidated": True,
    }
    with pytest.raises(CaseConflictError):
        execute_approved_case(case["case_id"], validator=wrong_provider)
    assert get_case(case["case_id"])["simulated_execution"] is None


def test_api_execute_endpoint_requires_approved_case(monkeypatch):
    client = TestClient(main.app)
    case = create_case(sample_result())
    response = client.post(f"/api/agent/cases/{case['case_id']}/execute")
    assert response.status_code == 409
    assert response.json()["detail"] == "Case must be approved before simulated execution."


def test_api_unknown_execution_case_returns_404():
    client = TestClient(main.app)
    response = client.post("/api/agent/cases/CASE-UNKNOWN/execute")
    assert response.status_code == 404


def test_end_to_end_synthetic_agent_approval_and_execution(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    client = TestClient(main.app)
    created = client.post("/api/agent/run", json={
        "appointment_id": "APT009737",
        "message": "Can we reschedule this visit?",
    })
    assert created.status_code == 200, created.text
    payload = created.json()
    assert payload.get("case_id") and payload.get("proposal")

    case_id = payload["case_id"]
    approved = client.post(f"/api/agent/cases/{case_id}/decision", json={"decision": "approve"})
    assert approved.status_code == 200, approved.text

    executed = client.post(f"/api/agent/cases/{case_id}/execute")
    assert executed.status_code == 200, executed.text
    result = executed.json()
    assert result["workflow_status"] == "simulated_resolved"
    assert result["simulated_execution"]["details"]["eligibility_revalidated"] is True
    assert result["booking_executed"] is False

    repeated = client.post(f"/api/agent/cases/{case_id}/execute")
    assert repeated.status_code == 200
    assert repeated.json()["simulated_execution"]["execution_id"] == result["simulated_execution"]["execution_id"]


def test_concurrent_execution_requests_create_one_simulated_record():
    from concurrent.futures import ThreadPoolExecutor
    case = create_case(sample_result())
    decide_case(case["case_id"], "approve", "reviewed")

    def run_once(_):
        return execute_approved_case(case["case_id"], validator=validator)

    with ThreadPoolExecutor(max_workers=5) as pool:
        results = list(pool.map(run_once, range(5)))

    execution_ids = {item["simulated_execution"]["execution_id"] for item in results}
    assert len(execution_ids) == 1
    stored = get_case(case["case_id"])
    assert [event["event_type"] for event in stored["events"]].count("simulated_recovery_executed") == 1
