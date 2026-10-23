import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "model"))
from evaluate_agent_challenge import run_evaluation  # noqa: E402


def test_challenge_suite_has_broad_category_coverage():
    suite = json.loads((ROOT / "data/evaluation/agent_challenge_v1.json").read_text())
    assert len(suite["cases"]) >= 20
    categories = {case["category"] for case in suite["cases"]}
    assert {"paraphrase_reschedule", "cancel_only", "confirmation", "ambiguous", "compound_request"}.issubset(categories)


def test_challenge_evaluation_is_reproducible_and_reports_failures():
    result = run_evaluation()
    assert result["case_count"] == 24
    assert 0 <= result["intent_accuracy"] <= 1
    assert 0 <= result["safe_disposition_pass_rate"] <= 1
    assert len(result["failed_cases"]) == sum(
        not row["intent_correct"] or not row["disposition_pass"] for row in result["case_results"]
    )
    assert result["local_execution_latency_ms"]["p95"] >= result["local_execution_latency_ms"]["p50"]


def test_parser_handles_new_paraphrases_and_negated_cancellation():
    from communication_intelligence import extract_intent

    assert extract_intent("Can we move it to sometime after five days?")["intent"] == "Reschedule"
    assert extract_intent("Please discontinue the home visit.")["intent"] == "Cancel"
    assert extract_intent("Keep the appointment as planned; that is fine.")["intent"] == "Confirm"
    negated = extract_intent("Don't cancel my appointment; I'll confirm later.")
    assert negated["intent"] == "Unclear"
    assert negated["cancel_current"] is False
