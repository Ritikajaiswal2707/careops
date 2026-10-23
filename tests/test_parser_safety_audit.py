import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "model"))
from evaluate_parser_safety import evaluate_suite, SUITES  # noqa: E402


def test_safety_audit_reports_false_cancel_and_false_confirm_counts():
    report = evaluate_suite("development", SUITES["development"])
    assert report["case_count"] == 36
    assert report["false_cancellation_count"] == len(report["false_cancellation_cases"])
    assert report["false_confirmation_count"] == len(report["false_confirmation_cases"])
    assert "confusion_matrix" in report
    assert "limitations" in report


def test_frozen_holdout_source_is_not_modified_by_safety_audit():
    suite_path = SUITES["frozen_holdout"]
    before = suite_path.read_bytes()
    evaluate_suite("frozen_holdout", suite_path)
    after = suite_path.read_bytes()
    assert before == after
