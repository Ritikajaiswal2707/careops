"""Evaluate end-to-end CareOps behaviour on a frozen synthetic holdout.

Run from repo root:
    python model/evaluate_agent_holdout.py

This is offline, synthetic, author-created evidence—not an independent or
production benchmark. Do not tune the parser on this holdout; use challenge
and development suites for iteration.
"""
from __future__ import annotations
import json
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "model"
sys.path.insert(0, str(MODEL))
from recovery_agent import run_recovery_agent  # noqa: E402
from simulated_execution import revalidate_proposal, RevalidationError  # noqa: E402

SUITE = ROOT / "data/evaluation/agent_holdout_v1.json"
OUTPUT = ROOT / "data/evaluation/latest_agent_holdout_eval.json"


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


def run_evaluation(suite_path: Path = SUITE, output_path: Path = OUTPUT) -> dict[str, Any]:
    suite = json.loads(suite_path.read_text(encoding="utf-8"))
    rows = []
    categories: dict[str, dict[str, int]] = defaultdict(lambda: {"n": 0, "intent_correct": 0, "disposition_pass": 0})
    intent_correct = disposition_pass = proposal_count = proposal_integrity_pass = 0
    latencies = []
    for case in suite["cases"]:
        started = time.perf_counter()
        result = run_recovery_agent(suite["appointment_id"], case["message"], llm_call=None)
        elapsed = (time.perf_counter() - started) * 1000
        latencies.append(elapsed)
        intent_ok = result.get("intent") == case["expected_intent"]
        disposition_ok = _disposition_pass(case, result)
        proposal = result.get("proposal")
        proposal_integrity = None
        if proposal:
            proposal_count += 1
            required = {"appointment_id", "provider_id", "new_date", "approval_required"}
            schema_ok = required.issubset(proposal) and proposal.get("approval_required") is True and str(proposal.get("appointment_id")) == str(suite["appointment_id"])
            if schema_ok:
                try:
                    revalidate_proposal(proposal)
                    proposal_integrity = True
                except (RevalidationError, ValueError, FileNotFoundError):
                    proposal_integrity = False
            else:
                proposal_integrity = False
            proposal_integrity_pass += int(proposal_integrity)
        intent_correct += int(intent_ok)
        disposition_pass += int(disposition_ok)
        cat = categories[case["category"]]
        cat["n"] += 1
        cat["intent_correct"] += int(intent_ok)
        cat["disposition_pass"] += int(disposition_ok)
        rows.append({
            "case_id": case["id"], "category": case["category"],
            "expected_intent": case["expected_intent"], "predicted_intent": result.get("intent"),
            "intent_correct": intent_ok, "expected_disposition": case["expected_disposition"],
            "actual_status": result.get("status"), "disposition_pass": disposition_ok,
            "proposal_present": bool(proposal), "proposal_integrity_pass": proposal_integrity,
            "elapsed_ms": round(elapsed, 3),
        })
    ordered = sorted(latencies)
    def percentile(p: float):
        return round(ordered[min(len(ordered)-1, max(0, round((len(ordered)-1)*p)))], 3) if ordered else None
    cat_report = {name: {**counts, "intent_accuracy": _rate(counts["intent_correct"], counts["n"]),
                         "disposition_pass_rate": _rate(counts["disposition_pass"], counts["n"])}
                  for name, counts in sorted(categories.items())}
    report = {
        "suite_name": suite["suite_name"], "suite_version": suite["version"],
        "run_mode": "offline rules-first; external LLM disabled; synthetic data only",
        "holdout_policy": "Frozen author-created holdout; do not tune on this suite. It is not an independently sampled benchmark.",
        "case_count": len(rows), "intent_accuracy": _rate(intent_correct, len(rows)),
        "safe_disposition_pass_rate": _rate(disposition_pass, len(rows)),
        "proposal_count": proposal_count,
        "proposal_revalidation_pass_rate": _rate(proposal_integrity_pass, proposal_count),
        "proposal_revalidation_pass_count": proposal_integrity_pass,
        "category_summary": cat_report,
        "local_execution_latency_ms": {"p50": percentile(0.5), "p95": percentile(0.95),
            "note": "Local offline Python execution only; excludes hosted API latency and is not a production SLO."},
        "failed_cases": [r for r in rows if not r["intent_correct"] or not r["disposition_pass"] or r["proposal_integrity_pass"] is False],
        "limitations": suite["limitations"], "case_results": rows,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report

if __name__ == "__main__":
    report = run_evaluation()
    print(json.dumps({k:v for k,v in report.items() if k not in {"case_results", "failed_cases"}}, indent=2))
    print(f"Detailed report: {OUTPUT.relative_to(ROOT)}")
