"""
Module 2c: score Claude's direct structured extraction against the held-out
set, as a documented alternative to llm_vs_baseline_eval.py's real-API path.

Context: llm_vs_baseline_eval.py's run_llm_eval() calls the Anthropic API and
only runs if ANTHROPIC_API_KEY is set. This sandbox has no key configured,
and provisioning one specifically to spend money on ~103 API calls for this
benchmark was declined. Rather than leaving the LLM side permanently null,
Claude performed the same structured extraction directly -- reading each of
the 103 held-out messages BLIND (predictions recorded in
model/my_llm_predictions.py before gold labels were consulted) and producing
the exact JSON schema run_llm_eval()'s system prompt specifies.

What this is and isn't:
  - IS a genuine, honest test of LLM-quality extraction on unseen phrasing:
    intent accuracy/F1, temporal extraction, reason extraction are all real,
    blind results -- not simulated, not copied from the gold set.
  - IS NOT a substitute for cost_per_message_inr or avg_latency_ms. Those
    require an actual metered API round-trip (token counts, wall-clock
    timing) that only happens through run_llm_eval()'s real client.
    They're reported as null here, not estimated -- see README for a clearly
    labeled illustrative range instead.

Re-running this is just `python3 llm_direct_eval.py` -- it has no external
dependency (no API key needed), unlike llm_vs_baseline_eval.py's LLM half.
"""
import json
import os

from llm_vs_baseline_eval import HELD_OUT_SET, _score, run_rule_based_eval
from my_llm_predictions import my_predictions

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def run_llm_direct_eval():
    assert len(my_predictions) == len(HELD_OUT_SET), (
        f"my_llm_predictions.py has {len(my_predictions)} entries, "
        f"held-out set has {len(HELD_OUT_SET)} -- these must line up 1:1."
    )
    predictions = []
    for case, pred in zip(HELD_OUT_SET, my_predictions):
        predictions.append({
            "message": case["message"],
            "true_intent": case["intent"],
            "pred_intent": pred["intent"],
            # my_llm_predictions.py was recorded blind under the ORIGINAL
            # 5-field schema, before cancel_current existed. Backfilling a
            # guess for it now would mix hindsight into a run that's only
            # credible because it was blind -- so pred_cancel_current is
            # left unscored (None) for this path. true_intent, though, DOES
            # pick up the taxonomy fix automatically (HELD_OUT_SET now
            # labels cases 50/81 as Reschedule): that's a correction to the
            # gold label, not new information handed to the predictor, so
            # it's fair to rescore against it.
            "true_cancel_current": case["cancel_current"],
            "pred_cancel_current": None,
            "true_temporal": (case["preferred_day"], case["next_week"], case["relative_day"], case["offset_days"]),
            "pred_temporal": (pred["preferred_day"], pred["next_week"], pred["relative_day"], pred["offset_days"]),
            "true_reason": case["reason"],
            "pred_reason": pred["reason"],
            "json_valid": True,  # Claude's direct output was already structured, not parsed from raw API text
        })
    metrics = _score(predictions)
    metrics["cost_per_message_inr"] = None
    metrics["avg_latency_ms"] = None
    metrics["methodology_note"] = (
        "No live Anthropic API call was made for this run. Claude performed the "
        "structured extraction directly on all 103 held-out messages, blind to "
        "gold labels at prediction time (see my_llm_predictions.py). Genuine "
        "test of extraction quality; cost/latency require a real metered API "
        "call and are reported as null, not estimated. cancel_current_accuracy "
        "is also null here: that field was added to the schema after this blind "
        "run, so there's no blind answer to grade it against -- a fresh blind "
        "(or live API) run against the updated schema would be needed for that "
        "number."
    )
    misclassified = [p for p in predictions if p["true_intent"] != p["pred_intent"]]
    temporal_mismatches = [p for p in predictions if p["true_temporal"] != p["pred_temporal"]]
    return predictions, metrics, misclassified, temporal_mismatches


if __name__ == "__main__":
    rule_predictions, rule_metrics, rule_misclassified = run_rule_based_eval()
    print(f"Rule-based extractor on {rule_metrics['n']} held-out messages:")
    print(f"  intent accuracy      {rule_metrics['intent_accuracy']:.1%}  (macro F1 {rule_metrics['intent_macro_f1']})")
    print(f"  temporal accuracy    {rule_metrics['temporal_extraction_accuracy']:.1%}")
    print(f"  reason accuracy      {rule_metrics['reason_extraction_accuracy']:.1%}")
    print(f"  abstention rate      {rule_metrics['abstention_rate']:.1%}")

    llm_predictions, llm_metrics, llm_misclassified, temporal_mismatches = run_llm_direct_eval()
    print(f"\nClaude (direct extraction, no metered API call) on the same {llm_metrics['n']} messages:")
    print(f"  intent accuracy      {llm_metrics['intent_accuracy']:.1%}  (macro F1 {llm_metrics['intent_macro_f1']})")
    print(f"  temporal accuracy    {llm_metrics['temporal_extraction_accuracy']:.1%}")
    print(f"  reason accuracy      {llm_metrics['reason_extraction_accuracy']:.1%}")
    print(f"  abstention rate      {llm_metrics['abstention_rate']:.1%}")
    print(f"  cost / latency       not measured (no metered API call was made)")

    print(f"\nintent misclassifications: {len(llm_misclassified)} / {llm_metrics['n']}")
    for p in llm_misclassified:
        print(f"  {p['message']!r}: true={p['true_intent']!r} pred={p['pred_intent']!r}")

    print(f"\ntemporal mismatches: {len(temporal_mismatches)} / {llm_metrics['n']}")
    if temporal_mismatches:
        for p in temporal_mismatches:
            print(f"  {p['message']!r}: true={p['true_temporal']!r} pred={p['pred_temporal']!r}")

    output = {
        "held_out_set_size": len(HELD_OUT_SET),
        "rule_based": {"metrics": rule_metrics, "misclassified": rule_misclassified},
        "llm": {"metrics": llm_metrics, "misclassified": llm_misclassified},
    }
    with open(os.path.join(BASE_DIR, "llm_vs_baseline_results.json"), "w") as f:
        json.dump(output, f, indent=2, default=str)
    print("\nwrote model/llm_vs_baseline_results.json")
