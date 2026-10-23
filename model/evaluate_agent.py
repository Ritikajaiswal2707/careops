"""Run CareOps' deterministic, synthetic recovery-agent regression suite.

Usage from repository root: python model/evaluate_agent.py
This disables external LLM calls. It is a small authored regression suite,
not an independent holdout or a claim of real-world performance.
"""
from __future__ import annotations

import json
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

MODEL_DIR = Path(__file__).resolve().parent
ROOT_DIR = MODEL_DIR.parent
sys.path.insert(0, str(MODEL_DIR))

from capacity_recovery import UnknownAppointmentError  # noqa: E402
from recovery_agent import run_recovery_agent  # noqa: E402

SUITE_PATH = ROOT_DIR / "data" / "evaluation" / "agent_scenarios_v1.json"
OUTPUT_PATH = ROOT_DIR / "data" / "evaluation" / "latest_agent_eval.json"


def _rate(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def _output_integrity(result: dict[str, Any]) -> list[str]:
    """Check basic agent response invariants; not a full domain safety audit."""
    errors = []
    proposal = result.get("proposal")
    if proposal is not None:
        if result.get("intent") != "Reschedule":
            errors.append("proposal_for_non_reschedule_intent")
        if proposal.get("approval_required") is not True:
            errors.append("proposal_without_approval_gate")
        if proposal.get("appointment_id") != result.get("appointment_id"):
            errors.append("proposal_appointment_mismatch")
    if result.get("simulated") is not True:
        errors.append("synthetic_result_not_marked_simulated")
    return errors


def run_evaluation() -> dict[str, Any]:
    suite = json.loads(SUITE_PATH.read_text(encoding="utf-8"))
    rows = []
    case_latencies_ms = []
    status_counts = Counter()
    tool_call_counts = []
    intent_correct = 0
    disposition_correct = 0
    integrity_errors = 0
    reschedule_cases = 0
    reschedule_proposals = 0
    unclear_cases = 0
    unclear_escalated = 0

    for case in suite["cases"]:
        # LLM is intentionally disabled for a deterministic offline regression run.
        started = time.perf_counter()
        result = run_recovery_agent(
            suite["appointment_id"], case["message"], llm_call=None
        )
        elapsed_ms = (time.perf_counter() - started) * 1000
        case_latencies_ms.append(elapsed_ms)
        status_counts[result.get("status", "missing_status")] += 1
        tool_call_counts.append(len(result.get("tool_trace", [])))
        got_intent = result.get("intent")
        expected_intent = case["expected_intent"]
        intent_ok = got_intent == expected_intent
        intent_correct += int(intent_ok)

        disposition = case["expected_disposition"]
        if disposition == "recovery_or_no_option":
            disposition_ok = (
                result.get("status") in {"awaiting_coordinator_approval", "no_feasible_option"}
                and (result.get("proposal") is None or result.get("approval_required") is True)
            )
            reschedule_cases += 1
            reschedule_proposals += int(result.get("status") == "awaiting_coordinator_approval")
        elif disposition == "unsupported_without_proposal":
            disposition_ok = result.get("status") == "unsupported_intent" and result.get("proposal") is None
        elif disposition == "human_review_without_proposal":
            disposition_ok = result.get("status") == "needs_human_review" and result.get("proposal") is None and result.get("escalate_to_human") is True
            unclear_cases += 1
            unclear_escalated += int(disposition_ok)
        else:
            disposition_ok = False

        errors = _output_integrity(result)
        integrity_errors += len(errors)
        disposition_correct += int(disposition_ok)
        rows.append({
            "case_id": case["id"],
            "elapsed_ms": round(elapsed_ms, 3),
            "tool_call_count": len(result.get("tool_trace", [])),
            "expected_intent": expected_intent,
            "predicted_intent": got_intent,
            "intent_correct": intent_ok,
            "expected_disposition": disposition,
            "actual_status": result.get("status"),
            "disposition_correct": disposition_ok,
            "proposal_present": result.get("proposal") is not None,
            "integrity_errors": errors,
        })

    # Negative-path checks use injected dependencies to avoid relying on data luck.
    negative_checks = {}
    try:
        run_recovery_agent("APT999999", "Can we reschedule this visit?", llm_call=None)
        negative_checks["unknown_appointment_rejected"] = False
    except UnknownAppointmentError:
        negative_checks["unknown_appointment_rejected"] = True

    def no_candidates_builder(_date):
        import pandas as pd
        return {"cand": pd.DataFrame({"available_today": []})}

    def no_candidates_recommender(*_args, **_kwargs):
        return []

    no_option = run_recovery_agent(
        suite["appointment_id"], "Can we reschedule this visit to Saturday?",
        llm_call=None, candidate_builder=no_candidates_builder,
        recommender=no_candidates_recommender,
    )
    negative_checks["no_candidate_escalates_without_proposal"] = (
        no_option.get("status") == "no_feasible_option" and no_option.get("proposal") is None
    )

    def broken_builder(_date):
        raise RuntimeError("synthetic recovery tool outage")

    tool_failure = run_recovery_agent(
        suite["appointment_id"], "Can we reschedule this visit to Saturday?",
        llm_call=None, candidate_builder=broken_builder,
    )
    negative_checks["tool_failure_fails_closed"] = (
        tool_failure.get("status") == "needs_human_review"
        and tool_failure.get("escalate_to_human") is True
        and tool_failure.get("proposal") is None
        and tool_failure.get("tool_trace", [{}])[-1].get("status") == "error"
        and "synthetic recovery tool outage" not in json.dumps(tool_failure)
    )

    # A malformed LLM response must be rejected and escalated, never trusted.
    invalid_llm_result = run_recovery_agent(
        suite["appointment_id"],
        "I might need to change my visit",
        llm_call=lambda _message: {"intent": "Reschedule"},
    )
    negative_checks["invalid_llm_schema_escalates"] = (
        invalid_llm_result.get("status") == "needs_human_review"
        and invalid_llm_result.get("proposal") is None
        and invalid_llm_result.get("escalate_to_human") is True
    )

    # Percentile summaries are diagnostic only: local synthetic timings are not
    # representative of hosted API latency or production performance.
    ordered_latencies = sorted(case_latencies_ms)
    def percentile(values, p):
        if not values:
            return None
        idx = min(len(values) - 1, max(0, int(round((len(values) - 1) * p))))
        return round(values[idx], 3)

    summary = {
        "suite_name": suite["suite_name"],
        "suite_version": suite["version"],
        "run_mode": "offline; external LLM disabled; synthetic data only",
        "case_count": len(rows),
        "status_counts": dict(sorted(status_counts.items())),
        "tool_calls": {
            "total": sum(tool_call_counts),
            "average_per_case": round(sum(tool_call_counts) / len(tool_call_counts), 3) if tool_call_counts else None,
        },
        "local_execution_latency_ms": {
            "p50": percentile(ordered_latencies, 0.50),
            "p95": percentile(ordered_latencies, 0.95),
            "mean": round(sum(case_latencies_ms) / len(case_latencies_ms), 3) if case_latencies_ms else None,
            "note": "Local offline Python execution only; excludes live LLM/API latency and is not a production SLO measurement.",
        },
        "intent_accuracy_on_authored_suite": _rate(intent_correct, len(rows)),
        "expected_disposition_pass_rate": _rate(disposition_correct, len(rows)),
        "reschedule_cases": reschedule_cases,
        "reschedule_proposal_rate": _rate(reschedule_proposals, reschedule_cases),
        "ambiguous_cases": unclear_cases,
        "ambiguous_safe_escalation_rate": _rate(unclear_escalated, unclear_cases),
        "response_integrity_error_count": integrity_errors,
        "negative_path_checks": negative_checks,
        "all_negative_path_checks_passed": all(negative_checks.values()),
        "limitations": suite["limitations"],
        "case_results": rows,
    }
    OUTPUT_PATH.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return summary


if __name__ == "__main__":
    report = run_evaluation()
    compact = {key: value for key, value in report.items() if key != "case_results"}
    print(json.dumps(compact, indent=2, ensure_ascii=False))
    print(f"\nDetailed report: {OUTPUT_PATH.relative_to(ROOT_DIR)}")
