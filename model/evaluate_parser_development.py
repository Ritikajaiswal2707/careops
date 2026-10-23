"""Evaluate the offline intent parser on the mutable development suite.

Run from repository root: python model/evaluate_parser_development.py
This is a development diagnostic, not an independent benchmark.
"""
from __future__ import annotations
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "model"))
from communication_intelligence import extract_intent  # noqa: E402

SUITE = ROOT / "data/evaluation/parser_development_v1.json"
OUTPUT = ROOT / "data/evaluation/latest_parser_development_eval.json"


def run_evaluation(suite_path: Path = SUITE, output_path: Path = OUTPUT) -> dict:
    suite = json.loads(suite_path.read_text(encoding="utf-8"))
    rows = []
    groups = defaultdict(lambda: {"n": 0, "correct": 0})
    for case in suite["cases"]:
        prediction = extract_intent(case["message"])["intent"]
        correct = prediction == case["expected_intent"]
        bucket = groups[case["category"]]
        bucket["n"] += 1
        bucket["correct"] += int(correct)
        rows.append({**case, "predicted_intent": prediction, "correct": correct})
    n_correct = sum(row["correct"] for row in rows)
    report = {
        "suite_name": suite["suite_name"], "suite_version": suite["version"],
        "run_mode": "offline rule-based parser; external LLM disabled",
        "case_count": len(rows), "correct_count": n_correct,
        "accuracy": round(n_correct / len(rows), 4) if rows else None,
        "category_summary": {k: {**v, "accuracy": round(v["correct"] / v["n"], 4)} for k, v in sorted(groups.items())},
        "failed_cases": [r for r in rows if not r["correct"]],
        "limitations": suite["limitations"], "case_results": rows,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report

if __name__ == "__main__":
    report = run_evaluation()
    print(json.dumps({k: v for k, v in report.items() if k not in {"case_results", "failed_cases"}}, indent=2))
    print("Failed cases:", json.dumps(report["failed_cases"], ensure_ascii=False))
