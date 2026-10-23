"""Audit parser error types without changing either evaluation suite.

Run from repository root: python model/evaluate_parser_safety.py
All results are offline and synthetic. This is a diagnostic, not a safety certification.
"""
from __future__ import annotations
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "model"))
from communication_intelligence import extract_intent  # noqa: E402

SUITES = {
    "development": ROOT / "data/evaluation/parser_development_v1.json",
    "frozen_holdout": ROOT / "data/evaluation/agent_holdout_v1.json",
}
OUTPUT = ROOT / "data/evaluation/latest_parser_safety_audit.json"
LABELS = ["Confirm", "Reschedule", "Cancel", "Unclear", "No Response"]


def evaluate_suite(name: str, path: Path) -> dict:
    suite = json.loads(path.read_text(encoding="utf-8"))
    cases = []
    confusion = Counter()
    by_expected = defaultdict(lambda: {"n": 0, "correct": 0})
    for case in suite["cases"]:
        expected = case.get("expected_intent", case.get("intent"))
        prediction = extract_intent(case.get("message", ""))["intent"]
        confusion[(expected, prediction)] += 1
        by_expected[expected]["n"] += 1
        by_expected[expected]["correct"] += int(expected == prediction)
        cases.append({"id": case["id"], "category": case.get("category"),
                      "expected_intent": expected, "predicted_intent": prediction,
                      "correct": expected == prediction})
    n = len(cases)
    fp_cancel = [r for r in cases if r["predicted_intent"] == "Cancel" and r["expected_intent"] != "Cancel"]
    fp_confirm = [r for r in cases if r["predicted_intent"] == "Confirm" and r["expected_intent"] != "Confirm"]
    missed_cancel = [r for r in cases if r["expected_intent"] == "Cancel" and r["predicted_intent"] != "Cancel"]
    missed_confirm = [r for r in cases if r["expected_intent"] == "Confirm" and r["predicted_intent"] != "Confirm"]
    return {
        "suite_name": suite.get("suite_name", name), "version": suite.get("version"),
        "source_file": str(path.relative_to(ROOT)), "case_count": n,
        "accuracy": round(sum(r["correct"] for r in cases) / n, 4) if n else None,
        "confusion_matrix": {actual: {pred: confusion[(actual, pred)] for pred in LABELS}
                             for actual in LABELS if any(a == actual for a, _ in confusion)},
        "per_expected_intent": {k: {**v, "recall": round(v["correct"] / v["n"], 4) if v["n"] else None}
                                for k, v in sorted(by_expected.items())},
        "false_cancellation_count": len(fp_cancel),
        "false_cancellation_cases": fp_cancel,
        "false_confirmation_count": len(fp_confirm),
        "false_confirmation_cases": fp_confirm,
        "missed_cancellation_count": len(missed_cancel),
        "missed_cancellation_cases": missed_cancel,
        "missed_confirmation_count": len(missed_confirm),
        "missed_confirmation_cases": missed_confirm,
        "limitations": suite.get("limitations", []) + [
            "Synthetic, author-created cases; not independently annotated or production sampled.",
            "False-confirmation and false-cancellation rates here are counts over the suite, not real-world risk estimates.",
            "This script evaluates intent labels only; it does not certify downstream actions as safe."
        ],
        "case_results": cases,
    }


def run_audit(output_path: Path = OUTPUT) -> dict:
    reports = {name: evaluate_suite(name, path) for name, path in SUITES.items()}
    report = {
        "report_name": "CareOps Parser Safety Error Audit",
        "report_version": "1.0.0",
        "run_mode": "offline rule-based parser; external LLM disabled",
        "suite_policy": "Development suite is mutable. Frozen holdout is read-only and must not be used for parser tuning.",
        "suites": reports,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report

if __name__ == "__main__":
    report = run_audit()
    for name, item in report["suites"].items():
        print(f"{name}: n={item['case_count']} accuracy={item['accuracy']} "
              f"false_cancel={item['false_cancellation_count']} "
              f"false_confirm={item['false_confirmation_count']} "
              f"missed_cancel={item['missed_cancellation_count']} "
              f"missed_confirm={item['missed_confirmation_count']}")
    print(f"Detailed report: {OUTPUT.relative_to(ROOT)}")
