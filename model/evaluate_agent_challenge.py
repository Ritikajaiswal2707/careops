"""Evaluate CareOps against a separately authored synthetic challenge suite.

Run from repo root: python model/evaluate_agent_challenge.py
This is exploratory regression evidence, not an external/production benchmark.
External LLM calls are disabled to keep results reproducible and cost-free.
"""
from __future__ import annotations
import argparse
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

MODEL_DIR = Path(__file__).resolve().parent
ROOT_DIR = MODEL_DIR.parent
sys.path.insert(0, str(MODEL_DIR))
from recovery_agent import run_recovery_agent  # noqa: E402

SUITE_PATH = ROOT_DIR / "data" / "evaluation" / "agent_challenge_v1.json"
OUTPUT_PATH = ROOT_DIR / "data" / "evaluation" / "latest_agent_challenge_eval.json"


def _rate(n: int, d: int) -> float | None:
    return round(n / d, 4) if d else None


def _disposition_pass(case: dict[str, Any], result: dict[str, Any]) -> bool:
    expected = case["expected_disposition"]
    if expected == "recovery_or_no_option":
        return result.get("status") in {"awaiting_coordinator_approval", "no_feasible_option"} and (
            result.get("proposal") is None or result.get("approval_required") is True
        )
    if expected == "unsupported_without_proposal":
        return result.get("status") == "unsupported_intent" and result.get("proposal") is None
    if expected == "human_review_without_proposal":
        return result.get("status") == "needs_human_review" and result.get("proposal") is None and result.get("escalate_to_human") is True
    return False


def run_evaluation(suite_path: Path = SUITE_PATH, output_path: Path = OUTPUT_PATH) -> dict[str, Any]:
    suite = json.loads(suite_path.read_text(encoding="utf-8"))
    rows = []
    category_counts: dict[str, dict[str, int]] = defaultdict(lambda: {"n": 0, "intent_correct": 0, "disposition_pass": 0})
    intent_correct = disposition_pass = 0
    latencies = []
    for case in suite["cases"]:
        started = time.perf_counter()
        result = run_recovery_agent(suite["appointment_id"], case["message"], llm_call=None)
        elapsed_ms = (time.perf_counter() - started) * 1000
        latencies.append(elapsed_ms)
        intent_ok = result.get("intent") == case["expected_intent"]
        disposition_ok = _disposition_pass(case, result)
        intent_correct += int(intent_ok)
        disposition_pass += int(disposition_ok)
        bucket = category_counts[case["category"]]
        bucket["n"] += 1
        bucket["intent_correct"] += int(intent_ok)
        bucket["disposition_pass"] += int(disposition_ok)
        rows.append({
            "case_id": case["id"], "category": case["category"],
            "message": case["message"], "expected_intent": case["expected_intent"],
            "predicted_intent": result.get("intent"), "intent_correct": intent_ok,
            "expected_disposition": case["expected_disposition"],
            "actual_status": result.get("status"), "disposition_pass": disposition_ok,
            "proposal_present": result.get("proposal") is not None,
            "elapsed_ms": round(elapsed_ms, 3),
        })
    category_summary = {
        name: {**counts,
               "intent_accuracy": _rate(counts["intent_correct"], counts["n"]),
               "disposition_pass_rate": _rate(counts["disposition_pass"], counts["n"])}
        for name, counts in sorted(category_counts.items())
    }
    sorted_latency = sorted(latencies)
    def percentile(p: float):
        if not sorted_latency:
            return None
        idx = min(len(sorted_latency) - 1, round((len(sorted_latency) - 1) * p))
        return round(sorted_latency[idx], 3)
    report = {
        "suite_name": suite["suite_name"], "suite_version": suite["version"],
        "run_mode": "offline rules-first path; external LLM disabled; synthetic data only",
        "case_count": len(rows),
        "intent_accuracy": _rate(intent_correct, len(rows)),
        "safe_disposition_pass_rate": _rate(disposition_pass, len(rows)),
        "category_summary": category_summary,
        "local_execution_latency_ms": {"p50": percentile(0.5), "p95": percentile(0.95),
            "note": "Local offline execution only; excludes hosted LLM/API latency and is not a production SLO."},
        "failed_cases": [row for row in rows if not row["intent_correct"] or not row["disposition_pass"]],
        "limitations": suite["limitations"], "case_results": rows,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate CareOps against a synthetic challenge suite.")
    parser.add_argument("--suite", type=Path, default=SUITE_PATH, help="Path to a challenge-suite JSON file")
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH, help="Path for the JSON evaluation report")
    args = parser.parse_args()
    report = run_evaluation(args.suite, args.output)
    compact = {k: v for k, v in report.items() if k not in {"case_results", "failed_cases"}}
    compact["failed_case_count"] = len(report["failed_cases"])
    print(json.dumps(compact, indent=2, ensure_ascii=False))
    print(f"\nDetailed report: {args.output}")
