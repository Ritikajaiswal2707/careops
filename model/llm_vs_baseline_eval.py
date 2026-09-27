"""
Module 2b: rule-based extractor vs. LLM, on a held-out set.

The 100% agreement number reported by communication_intelligence.py is
measured against the rules' *own* training labels -- the source CSV has
only 10 unique messages, and extracted_intent was already in the dataset
the rules were written to match. That number shows the rules reproduce
their own targets, not that they generalize to phrasing they haven't seen.

This module is the actual test: a held-out set of 103 messages, hand-labeled
(full gold structure -- intent, temporal signal, and reason, not just
intent), written independently of communications.csv's 10 templates --
deliberately including English, Hindi, Hinglish, typos, indirect/no-keyword
phrasing, sarcasm, compound requests, and a spread of temporal expressions
(explicit weekday, "next week", "next <weekday>", "kal"/tomorrow, weekend,
"after N days", and vague/no signal at all) -- the rule set was never tuned
against most of this. It scores, on the same set:
  1. The existing rule-based extractor (runs unconditionally -- no dependency)
  2. An LLM call via the Anthropic API, prompted to return the full
     structured extraction as JSON (runs only if ANTHROPIC_API_KEY is set --
     this sandbox has no key wired in, same limitation the README already
     discloses for communication_intelligence.py)

Metrics computed for whichever side(s) actually ran:
  - Intent accuracy + macro/per-class F1 (not just overall accuracy, which
    hides class imbalance -- Confirm is common and easy; Cancel/Reschedule
    without keywords are rare and hard, and a macro F1 doesn't let a strong
    Confirm score hide weak Cancel/Reschedule performance)
  - Temporal extraction accuracy (exact match on preferred_day, next_week,
    relative_day, offset_days as a tuple -- partial credit isn't given,
    because a wrong date is operationally a wrong date)
  - Reason extraction accuracy (exact match against the 3-category gold set)
  - JSON validity rate (trivially 100% for the rule-based side, since it's
    native Python; the real question is whether the LLM's output parses
    cleanly every time when asked to emit JSON)
  - Abstention rate (share of predictions the extractor itself flags as
    Unclear -- a system that abstains honestly is different from one that
    guesses wrong confidently, and this number distinguishes them)
  - Cost/message and latency/message (rule-based is $0 and sub-millisecond
    by construction; LLM numbers are only reported when a live run happened
    -- never estimated)

This is the experiment the case study argues for: does an LLM improve
intent + temporal + reason extraction enough to justify its added
cost/latency/complexity over a free, instant, fully-offline rule-based
baseline? Answering that requires actually running both sides -- this
script is set up to do that the moment an API key is available; it does
not simulate or assume an LLM result.
"""
import json
import os
import time
from collections import defaultdict
from communication_intelligence import extract_intent

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ---- Held-out set --------------------------------------------------------
# Hand-labeled, written independently of communications.csv's 10 message
# templates, and stored as a real data artifact (data/communication_eval.json)
# rather than embedded in this script -- so it's genuinely usable as "an
# independent evaluation dataset," not something that only exists buried
# inside the evaluator that scores against it. Every item carries the FULL
# gold structure the product needs (intent, preferred_day, next_week,
# relative_day, offset_days, reason) -- not just intent -- because
# intent-only was the gap the P0 review flagged: a coordinator seeing
# "Reschedule" still needs to know to when and why.
#
# Categories, roughly balanced against real-world class imbalance (Confirm
# is the most common real message; Cancel and no-keyword Reschedule are
# rarer but higher-stakes to get right): explicit/minimal/Hinglish/typo'd
# Confirm; Reschedule with explicit weekday, "next week", "next <weekday>",
# weekend, "kal"/tomorrow, "after N days", or no day named at all, each with
# a mix of doctor/work/late/no reason; explicit-keyword and indirect Cancel;
# genuinely ambiguous/non-committal/off-topic Unclear; empty No Response;
# plus sarcasm, compound requests, and Devanagari-script-only messages.
with open(os.path.join(BASE_DIR, "..", "data", "communication_eval.json"), encoding="utf-8") as f:
    HELD_OUT_SET = json.load(f)



def _per_class_f1(pairs, labels):
    """pairs: list of (true, pred). Returns {label: f1} and macro F1."""
    f1s = {}
    for label in labels:
        tp = sum(1 for t, p in pairs if t == label and p == label)
        fp = sum(1 for t, p in pairs if t != label and p == label)
        fn = sum(1 for t, p in pairs if t == label and p != label)
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        f1s[label] = round(f1, 3)
    macro = round(sum(f1s.values()) / len(f1s), 3) if f1s else 0.0
    return f1s, macro


def _score(predictions):
    """predictions: list of dicts with true_* and pred_* keys per case, plus
    optional 'json_valid' and 'latency_s'. Returns the full metric bundle."""
    n = len(predictions)
    intent_labels = sorted({p["true_intent"] for p in predictions} | {p["pred_intent"] for p in predictions})
    intent_pairs = [(p["true_intent"], p["pred_intent"]) for p in predictions]
    intent_f1_by_class, intent_macro_f1 = _per_class_f1(intent_pairs, intent_labels)
    intent_accuracy = sum(t == pr for t, pr in intent_pairs) / n

    temporal_correct = sum(
        (p["true_temporal"] == p["pred_temporal"]) for p in predictions
    )
    reason_correct = sum(p["true_reason"] == p["pred_reason"] for p in predictions)
    abstentions = sum(1 for p in predictions if p["pred_intent"] == "Unclear")
    json_valid = [p.get("json_valid") for p in predictions if p.get("json_valid") is not None]

    return {
        "n": n,
        "intent_accuracy": round(intent_accuracy, 3),
        "intent_macro_f1": intent_macro_f1,
        "intent_f1_by_class": intent_f1_by_class,
        "temporal_extraction_accuracy": round(temporal_correct / n, 3),
        "reason_extraction_accuracy": round(reason_correct / n, 3),
        "abstention_rate": round(abstentions / n, 3),
        "json_validity_rate": round(sum(json_valid) / len(json_valid), 3) if json_valid else None,
    }


def run_rule_based_eval():
    predictions = []
    total_latency = 0.0
    for case in HELD_OUT_SET:
        t0 = time.perf_counter()
        pred = extract_intent(case["message"])
        total_latency += time.perf_counter() - t0
        predictions.append({
            "message": case["message"],
            "true_intent": case["intent"],
            "pred_intent": pred["intent"],
            "true_temporal": (case["preferred_day"], case["next_week"], case["relative_day"], case["offset_days"]),
            "pred_temporal": (pred["preferred_day"], pred["next_week"], pred["relative_day"], pred["offset_days"]),
            "true_reason": case["reason"],
            "pred_reason": pred["reason"],
            "json_valid": True,  # native Python dict -- always structurally valid
        })
    metrics = _score(predictions)
    metrics["cost_per_message_inr"] = 0.0
    metrics["avg_latency_ms"] = round((total_latency / len(predictions)) * 1000, 4)
    misclassified = [p for p in predictions if p["true_intent"] != p["pred_intent"]]
    return predictions, metrics, misclassified


def run_llm_eval():
    """
    Calls the Anthropic API to extract the FULL structure (intent,
    preferred_day, next_week, relative_day, offset_days, reason) for the
    same held-out set, as JSON. Only runs if ANTHROPIC_API_KEY is set --
    this sandbox does not have one wired in (same disclosed limitation as
    communication_intelligence.py's docstring). Returns None if unavailable,
    rather than fabricating or estimating a result. This is deliberately the
    same architecture P0-6 argues for: the LLM only does "understand ->
    structured JSON", never scheduling logic.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None

    import anthropic  # local import: only needed on this path
    client = anthropic.Anthropic(api_key=api_key)

    system = (
        "Extract structured information from a home-healthcare patient "
        "message (English, Hindi, Hinglish, or a mix, possibly with typos). "
        "Respond with ONLY a JSON object, no other text, matching exactly:\n"
        '{"intent": "Confirm"|"Reschedule"|"Cancel"|"Unclear"|"No Response", '
        '"preferred_day": "Monday".."Sunday" or null, '
        '"next_week": true|false, '
        '"relative_day": "tomorrow"|"weekend"|null, '
        '"offset_days": integer or null, '
        '"reason": "Conflicting doctor visit"|"Work conflict"|'
        '"Provider/patient running late"|null}'
    )

    # Illustrative INR pricing for the model used here, at the time of
    # writing -- not fetched live, so treat this as a placeholder to
    # recompute against current published rates before quoting it externally.
    INPUT_PER_TOKEN_INR = 0.00025
    OUTPUT_PER_TOKEN_INR = 0.00125

    predictions = []
    total_latency = 0.0
    total_cost = 0.0
    for case in HELD_OUT_SET:
        t0 = time.perf_counter()
        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=200,
            system=system,
            messages=[{"role": "user", "content": case["message"] or "(empty message)"}],
        )
        total_latency += time.perf_counter() - t0
        total_cost += (resp.usage.input_tokens * INPUT_PER_TOKEN_INR
                       + resp.usage.output_tokens * OUTPUT_PER_TOKEN_INR)

        raw = resp.content[0].text.strip()
        try:
            parsed = json.loads(raw)
            json_valid = True
        except json.JSONDecodeError:
            parsed = {}
            json_valid = False

        predictions.append({
            "message": case["message"],
            "true_intent": case["intent"],
            "pred_intent": parsed.get("intent", "PARSE_ERROR"),
            "true_temporal": (case["preferred_day"], case["next_week"], case["relative_day"], case["offset_days"]),
            "pred_temporal": (parsed.get("preferred_day"), parsed.get("next_week", False),
                               parsed.get("relative_day"), parsed.get("offset_days")),
            "true_reason": case["reason"],
            "pred_reason": parsed.get("reason"),
            "json_valid": json_valid,
        })

    metrics = _score(predictions)
    metrics["cost_per_message_inr"] = round(total_cost / len(predictions), 4)
    metrics["avg_latency_ms"] = round((total_latency / len(predictions)) * 1000, 1)
    misclassified = [p for p in predictions if p["true_intent"] != p["pred_intent"]]
    return predictions, metrics, misclassified


if __name__ == "__main__":
    rule_predictions, rule_metrics, rule_misclassified = run_rule_based_eval()
    print(f"Rule-based extractor on {rule_metrics['n']} held-out messages:")
    print(f"  intent accuracy      {rule_metrics['intent_accuracy']:.1%}  (macro F1 {rule_metrics['intent_macro_f1']})")
    print(f"  per-class F1         {rule_metrics['intent_f1_by_class']}")
    print(f"  temporal accuracy    {rule_metrics['temporal_extraction_accuracy']:.1%}")
    print(f"  reason accuracy      {rule_metrics['reason_extraction_accuracy']:.1%}")
    print(f"  abstention rate      {rule_metrics['abstention_rate']:.1%}")
    print(f"  cost / latency       Rs.{rule_metrics['cost_per_message_inr']} / {rule_metrics['avg_latency_ms']} ms per message")

    output = {
        "held_out_set_size": len(HELD_OUT_SET),
        "rule_based": {"metrics": rule_metrics, "misclassified": rule_misclassified},
        "llm": None,
    }

    llm_out = run_llm_eval()
    if llm_out:
        llm_predictions, llm_metrics, llm_misclassified = llm_out
        print(f"\nLLM (claude-sonnet-4-6), structured JSON extraction, same {llm_metrics['n']} messages:")
        print(f"  intent accuracy      {llm_metrics['intent_accuracy']:.1%}  (macro F1 {llm_metrics['intent_macro_f1']})")
        print(f"  temporal accuracy    {llm_metrics['temporal_extraction_accuracy']:.1%}")
        print(f"  reason accuracy      {llm_metrics['reason_extraction_accuracy']:.1%}")
        print(f"  JSON validity        {llm_metrics['json_validity_rate']:.1%}")
        print(f"  cost / latency       Rs.{llm_metrics['cost_per_message_inr']} / {llm_metrics['avg_latency_ms']} ms per message")
        output["llm"] = {"metrics": llm_metrics, "misclassified": llm_misclassified}
    else:
        print("\nLLM comparison skipped: no ANTHROPIC_API_KEY in this environment. "
              "Set the key and re-run to get the actual head-to-head result across "
              "all five metrics -- this script does not simulate or assume one.")

    with open(os.path.join(BASE_DIR, "llm_vs_baseline_results.json"), "w") as f:
        json.dump(output, f, indent=2, default=str)
    print("\nwrote model/llm_vs_baseline_results.json")
