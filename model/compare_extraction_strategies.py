"""Compare rules-only, saved blind LLM predictions, and rule-first hybrid.

Offline and deterministic: this script makes no external API calls. The direct
LLM and hybrid LLM-side results reuse the documented saved predictions in
my_llm_predictions.py; cost/latency for those predictions are therefore not
measured. Use llm_vs_baseline_eval.py with ANTHROPIC_API_KEY configured for a
metered live comparison.

Run from the repository root:
    python model/compare_extraction_strategies.py
"""
from __future__ import annotations
import json
from pathlib import Path
import sys

MODEL_DIR = Path(__file__).resolve().parent
ROOT_DIR = MODEL_DIR.parent
sys.path.insert(0, str(MODEL_DIR))

from llm_vs_baseline_eval import run_rule_based_eval  # noqa: E402
from llm_direct_eval import run_llm_direct_eval  # noqa: E402
from hybrid_extraction import run_hybrid_offline_eval  # noqa: E402

OUT = ROOT_DIR / "data" / "evaluation" / "extraction_strategy_comparison.json"


def _strategy_summary(metrics: dict, *, method_note: str) -> dict:
    return {
        "n": metrics.get("n"),
        "intent_accuracy": metrics.get("intent_accuracy"),
        "intent_macro_f1": metrics.get("intent_macro_f1"),
        "intent_f1_by_class": metrics.get("intent_f1_by_class"),
        "temporal_extraction_accuracy": metrics.get("temporal_extraction_accuracy"),
        "reason_extraction_accuracy": metrics.get("reason_extraction_accuracy"),
        "abstention_rate": metrics.get("abstention_rate"),
        "llm_route_rate": metrics.get("llm_route_rate"),
        "escalation_rate": metrics.get("escalation_rate"),
        "cost_per_message_inr": metrics.get("cost_per_message_inr"),
        "avg_latency_ms": metrics.get("avg_latency_ms"),
        "methodology_note": method_note,
    }


def run_comparison(output_path: Path = OUT) -> dict:
    rule_predictions, rule_metrics, rule_errors = run_rule_based_eval()
    llm_predictions, llm_metrics, llm_errors, _ = run_llm_direct_eval()
    hybrid_predictions, hybrid_metrics, hybrid_errors = run_hybrid_offline_eval()

    # Use the same 103-message gold set. Deltas are percentage points, rounded
    # to 1 decimal; null stays null if a metric wasn't measured.
    def pp_delta(candidate, baseline):
        if candidate is None or baseline is None:
            return None
        return round((candidate - baseline) * 100, 1)

    strategies = {
        "rules_only": _strategy_summary(
            rule_metrics,
            method_note="Real rules-based extractor run locally on the 103-message labeled set. Local latency is measured; cost is zero for the offline rules path.",
        ),
        "saved_blind_llm_predictions": _strategy_summary(
            llm_metrics,
            method_note="Saved structured predictions produced blind to the gold labels, then scored locally. No live API request was made; cost and latency are unknown, not zero.",
        ),
        "rules_first_hybrid": _strategy_summary(
            hybrid_metrics,
            method_note="Real rules-first routing on the same 103 messages, using saved blind LLM predictions only when rules return Unclear. No live API request was made; cost and latency are unknown.",
        ),
    }
    report = {
        "title": "CareOps extraction strategy comparison",
        "dataset": {
            "name": "communication_eval.json",
            "n": len(rule_predictions),
            "same_gold_set_for_all_strategies": True,
            "data_type": "synthetic, manually labeled messages",
        },
        "strategies": strategies,
        "deltas_vs_rules_only_percentage_points": {
            "saved_blind_llm_intent_accuracy": pp_delta(
                llm_metrics.get("intent_accuracy"), rule_metrics.get("intent_accuracy")
            ),
            "saved_blind_llm_macro_f1": pp_delta(
                llm_metrics.get("intent_macro_f1"), rule_metrics.get("intent_macro_f1")
            ),
            "hybrid_intent_accuracy": pp_delta(
                hybrid_metrics.get("intent_accuracy"), rule_metrics.get("intent_accuracy")
            ),
            "hybrid_macro_f1": pp_delta(
                hybrid_metrics.get("intent_macro_f1"), rule_metrics.get("intent_macro_f1")
            ),
        },
        "error_counts": {
            "rules_only_intent_errors": len(rule_errors),
            "saved_blind_llm_intent_errors": len(llm_errors),
            "hybrid_intent_errors": len(hybrid_errors),
        },
        "interpretation": [
            "This comparison measures structured message extraction, not end-to-end appointment recovery success.",
            "The saved LLM predictions are not a live API benchmark. Do not claim API cost or latency from this report.",
            "The LLM-only and hybrid results reuse the same saved prediction artifact, so they are not independent replications.",
            "The message set is synthetic and small; validate with domain reviewers and a new locked test set before making broad generalisation claims.",
        ],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


if __name__ == "__main__":
    report = run_comparison()
    print(f"Dataset: {report['dataset']['n']} synthetic labeled messages")
    print("\nStrategy                     Intent acc   Macro F1   Temporal   Reason   LLM route")
    print("-" * 84)
    for key, label in [
        ("rules_only", "Rules only"),
        ("saved_blind_llm_predictions", "Saved blind LLM"),
        ("rules_first_hybrid", "Rules-first hybrid"),
    ]:
        m = report["strategies"][key]
        fmt = lambda value: "N/M" if value is None else f"{value:.1%}"
        print(f"{label:28} {fmt(m['intent_accuracy']):>10} {fmt(m['intent_macro_f1']):>10} {fmt(m['temporal_extraction_accuracy']):>10} {fmt(m['reason_extraction_accuracy']):>8} {fmt(m['llm_route_rate']):>10}")
    print("\nDelta vs rules-only (percentage points):")
    for name, value in report["deltas_vs_rules_only_percentage_points"].items():
        print(f"  {name}: {'not measured' if value is None else f'{value:+.1f} pp'}")
    print(f"\nDetailed report: {OUT}")
