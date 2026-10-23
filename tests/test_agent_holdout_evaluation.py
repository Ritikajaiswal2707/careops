import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "model"))
from evaluate_agent_holdout import run_evaluation  # noqa: E402


def test_holdout_suite_is_frozen_and_diverse():
    suite = json.loads((ROOT / "data/evaluation/agent_holdout_v1.json").read_text())
    assert len(suite["cases"]) == 30
    categories = {case["category"] for case in suite["cases"]}
    assert {"direct_reschedule", "cancel_only", "confirmation", "ambiguous", "negated_action", "compound_request"}.issubset(categories)
    assert "Do not use this set to tune rules" in suite["purpose"]


def test_holdout_report_includes_end_to_end_disposition_and_proposal_integrity(tmp_path):
    report = run_evaluation(output_path=tmp_path / "holdout.json")
    assert report["case_count"] == 30
    assert 0 <= report["intent_accuracy"] <= 1
    assert 0 <= report["safe_disposition_pass_rate"] <= 1
    assert report["proposal_count"] >= report["proposal_revalidation_pass_count"]
    assert len(report["failed_cases"]) == sum(
        not row["intent_correct"] or not row["disposition_pass"] or row["proposal_integrity_pass"] is False
        for row in report["case_results"]
    )
    assert report["local_execution_latency_ms"]["p95"] >= report["local_execution_latency_ms"]["p50"]
