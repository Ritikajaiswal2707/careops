import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "model"))

from evaluate_agent import run_evaluation  # noqa: E402


def test_evaluation_suite_has_expected_coverage():
    suite = json.loads((ROOT / "data/evaluation/agent_scenarios_v1.json").read_text())
    assert len(suite["cases"]) >= 25
    intents = {case["expected_intent"] for case in suite["cases"]}
    assert {"Reschedule", "Cancel", "Confirm", "Unclear"}.issubset(intents)


def test_evaluation_has_no_response_integrity_errors():
    result = run_evaluation()
    assert result["response_integrity_error_count"] == 0


def test_ambiguous_messages_escalate_safely_without_llm():
    result = run_evaluation()
    assert result["ambiguous_safe_escalation_rate"] == 1.0


def test_negative_path_checks_pass():
    result = run_evaluation()
    assert result["all_negative_path_checks_passed"] is True


def test_evaluation_reports_observability_metrics():
    result = run_evaluation()
    assert result["case_count"] == 31
    assert result["tool_calls"]["total"] >= result["case_count"]
    assert result["local_execution_latency_ms"]["p50"] is not None
    assert result["local_execution_latency_ms"]["p95"] >= result["local_execution_latency_ms"]["p50"]
    assert sum(result["status_counts"].values()) == result["case_count"]


def test_invalid_llm_schema_is_included_in_negative_path_checks():
    result = run_evaluation()
    assert result["negative_path_checks"]["invalid_llm_schema_escalates"] is True
