"""
Module 2d: rule-first hybrid extraction, LLM fallback.

Naming note: an earlier version of this module called this "confidence-gated."
That's not accurate -- the gate below is the rule-based extractor's own
binary abstention ("Unclear" vs. not), not a calibrated confidence score, and
there's no scored/thresholded probability anywhere in this pipeline. Calling
it "confidence-gated" implied more machinery than exists. "Rule-first hybrid
with LLM fallback" describes exactly what it does: rules run first and are
trusted whenever they don't abstain; the LLM is only ever consulted as a
fallback when they do.

The head-to-head comparison in llm_direct_eval.py answers "does an LLM
extract intent better than the rules?" (yes, substantially -- 100% vs 44.7%
intent accuracy on the 103-message held-out set, in a BLIND OFFLINE
evaluation -- see the caveat below, this is not a production or live-API
number). It does not answer "should every message go to the LLM?" This
module is the product decision built on top of that result: route a message
to the LLM only when the deterministic parser doesn't already have an
answer, rather than paying for an LLM call on every message.

Gate used: the rule-based extractor's own "Unclear" intent, i.e. abstention,
not a confidence score. communication_intelligence.extract_intent() already
abstains (returns intent="Unclear") rather than guessing when none of its
keyword rules fire -- see its docstring and the README's abstention-rate
discussion. That abstention is repurposed here as the gate, deliberately
instead of building a separate calibrated confidence model just to justify
a fancier name for this:

    message
      |
      v
    rule-based extractor (communication_intelligence.extract_intent)
      |
      +-- intent != "Unclear"  -> accept rule prediction (fast, free, no LLM call)
      |
      +-- intent == "Unclear"  -> LLM fallback
                                     |
                                     +-- valid schema, intent != "Unclear" -> accept LLM prediction
                                     |
                                     +-- invalid JSON / still "Unclear"    -> escalate_to_human = True

Measured on the 103-message held-out set (communication_eval.json), the rule
based extractor abstains on 65.0% of messages (67/103) -- see
llm_vs_baseline_results.json's rule_based.metrics.abstention_rate. That's the
real routing rate for this dataset: notably higher than a "most messages are
obvious" assumption might suggest, because the held-out set was deliberately
built to include casual/typo'd/indirect/sarcastic/compound phrasing (see
llm_vs_baseline_eval.py's docstring) rather than only easy cases. Whatever
the true routing rate turns out to be on live traffic, the architecture's
value doesn't depend on it being small -- it's that the LLM is only ever
paid for when the free deterministic path already gave up, not billed
against every message regardless of difficulty.

Of the 67 messages routed to the LLM in this held-out set, 13 (12.6% of the
full 103) come back "Unclear" from the blind LLM extraction too (see
my_llm_predictions.py) -- these are the genuinely ambiguous/off-topic/
non-committal messages neither path can confidently resolve, and this
module's escalation policy sends them to a human rather than guessing.
12.6% is therefore this dataset's honest floor on human-in-the-loop volume
for this system, not zero.

What this module is NOT:
  - Not a live production integration. run_hybrid_offline_eval() below
    reuses the SAME blind, unmetered LLM predictions (my_llm_predictions.py)
    that llm_direct_eval.py uses, for the same reason disclosed there: this
    sandbox has no ANTHROPIC_API_KEY configured. default_llm_call() below
    is wired for a real Anthropic API call and will be used automatically
    the moment a key is set -- see llm_vs_baseline_eval.py's run_llm_eval()
    for the identical request shape this borrows.
  - Not a cost/latency measurement. Because the LLM side of this evaluation
    is still an unmetered blind run, hybrid cost/latency are reported as
    null here too, same as llm_direct_eval.py -- NOT estimated by multiplying
    the routing rate against the README's illustrative per-message range.
    The architecture's cost ADVANTAGE over calling an LLM on every message
    is structural (only 65% of messages would ever reach it here) even
    though the per-message ₹ figure itself is still unmeasured.
"""
import json
import os

from communication_intelligence import extract_intent
from llm_vs_baseline_eval import HELD_OUT_SET, _score
from my_llm_predictions import my_predictions

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

ALLOWED_INTENTS = {"Confirm", "Reschedule", "Cancel", "Unclear", "No Response"}
ALLOWED_DAYS = {"Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"}
ALLOWED_REASONS = {"Conflicting doctor visit", "Work conflict", "Provider/patient running late"}


def _valid_schema(pred: dict) -> bool:
    """
    Guards against a malformed or off-schema LLM response before it's
    trusted downstream -- the abstention policy this module implements
    treats "the LLM answered something that doesn't fit the contract" the
    same as "the LLM abstained": escalate, don't act on it.
    """
    if not isinstance(pred, dict):
        return False
    if pred.get("intent") not in ALLOWED_INTENTS:
        return False
    day = pred.get("preferred_day")
    if day is not None and day not in ALLOWED_DAYS:
        return False
    reason = pred.get("reason")
    if reason is not None and reason not in ALLOWED_REASONS:
        return False
    return True


def default_llm_call(message: str):
    """
    Real Anthropic API call, used only for messages the rule-based gate
    already flagged as Unclear -- the production fallback path, not the
    offline evaluation path below (see run_hybrid_offline_eval()). Returns
    None if ANTHROPIC_API_KEY isn't set, same disclosed limitation as
    llm_vs_baseline_eval.run_llm_eval(), whose request shape this mirrors
    exactly so the two stay comparable.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None

    import anthropic  # local import: only needed on this path
    from llm_vs_baseline_eval import HELD_OUT_SET as _  # noqa: F401 (keeps import style consistent)

    client = anthropic.Anthropic(api_key=api_key)
    system = (
        "Extract structured information from a home-healthcare patient "
        "message (English, Hindi, Hinglish, or a mix, possibly with typos). "
        "Respond with ONLY a JSON object, no other text, matching exactly:\n"
        '{"intent": "Confirm"|"Reschedule"|"Cancel"|"Unclear"|"No Response", '
        '"cancel_current": true|false, '
        '"preferred_day": "Monday".."Sunday" or null, '
        '"next_week": true|false, '
        '"relative_day": "tomorrow"|"weekend"|null, '
        '"offset_days": integer or null, '
        '"reason": "Conflicting doctor visit"|"Work conflict"|'
        '"Provider/patient running late"|null}'
    )
    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=200,
        system=system,
        messages=[{"role": "user", "content": message or "(empty message)"}],
    )
    try:
        return json.loads(resp.content[0].text.strip())
    except json.JSONDecodeError:
        return None


def extract_intent_hybrid(message: str, llm_call=default_llm_call) -> dict:
    """
    Production entry point. llm_call is injectable (defaults to
    default_llm_call) so tests / offline evaluation can swap in the blind
    predictions instead of a live API call without this function's gating
    logic changing at all.

    Adds two fields on top of extract_intent()'s normal output:
      - source: "rule" | "llm" | "escalation"
      - escalate_to_human: True whenever neither path produced a usable
        answer -- the abstention policy a healthcare messaging product
        needs, so an ambiguous patient message gets a human's eyes rather
        than a silent wrong guess or a silently dropped message.
    """
    rule_pred = extract_intent(message)
    if rule_pred["intent"] != "Unclear":
        return {**rule_pred, "source": "rule", "escalate_to_human": False}

    llm_pred = llm_call(message) if llm_call else None
    if llm_pred is None or not _valid_schema(llm_pred) or llm_pred.get("intent") == "Unclear":
        return {**rule_pred, "source": "escalation", "escalate_to_human": True}

    merged = {
        "intent": llm_pred.get("intent"),
        "cancel_current": llm_pred.get("cancel_current", False),
        "preferred_day": llm_pred.get("preferred_day"),
        "urgency": rule_pred["urgency"],  # urgency keyword scan still runs on the raw text either way
        "reason": llm_pred.get("reason"),
        "next_week": llm_pred.get("next_week", False),
        "relative_day": llm_pred.get("relative_day"),
        "offset_days": llm_pred.get("offset_days"),
    }
    return {**merged, "source": "llm", "escalate_to_human": False}


def run_hybrid_offline_eval():
    """
    Offline evaluation of the gate itself, on the same 103-message held-out
    set llm_vs_baseline_eval.py and llm_direct_eval.py use. Every message is
    first classified by the rule-based extractor; whichever ones it marks
    Unclear are then "routed" to the blind LLM prediction already recorded
    in my_llm_predictions.py (index-aligned with HELD_OUT_SET) instead of a
    metered API call, for the same reason disclosed throughout this module
    and llm_direct_eval.py: no ANTHROPIC_API_KEY in this sandbox. This scores
    the ARCHITECTURE (routing + escalation), not a new extraction method --
    the rule and LLM predictions themselves are identical to the ones
    already scored individually elsewhere.
    """
    predictions = []
    routed_to_llm = 0
    escalated = 0

    for case, blind_llm_pred in zip(HELD_OUT_SET, my_predictions):
        rule_pred = extract_intent(case["message"])

        if rule_pred["intent"] != "Unclear":
            final = rule_pred
            source = "rule"
        else:
            routed_to_llm += 1
            # my_llm_predictions.py was frozen under the original 5-field
            # schema (no cancel_current) -- see its docstring -- so that
            # field is left None here for LLM-sourced predictions, same
            # "don't backfill a guess" rule llm_direct_eval.py follows.
            if blind_llm_pred.get("intent") == "Unclear":
                escalated += 1
                final = rule_pred  # nothing better to act on; flagged for a human
                source = "escalation"
            else:
                final = {
                    "intent": blind_llm_pred["intent"],
                    "cancel_current": None,
                    "preferred_day": blind_llm_pred["preferred_day"],
                    "reason": blind_llm_pred["reason"],
                    "next_week": blind_llm_pred["next_week"],
                    "relative_day": blind_llm_pred["relative_day"],
                    "offset_days": blind_llm_pred["offset_days"],
                }
                source = "llm"

        predictions.append({
            "message": case["message"],
            "source": source,
            "true_intent": case["intent"],
            "pred_intent": final["intent"],
            "true_cancel_current": case["cancel_current"],
            "pred_cancel_current": final.get("cancel_current"),
            "true_temporal": (case["preferred_day"], case["next_week"], case["relative_day"], case["offset_days"]),
            "pred_temporal": (final.get("preferred_day"), final.get("next_week", False),
                               final.get("relative_day"), final.get("offset_days")),
            "true_reason": case["reason"],
            "pred_reason": final.get("reason"),
            "json_valid": True,
        })

    metrics = _score(predictions)
    n = len(predictions)
    metrics["llm_route_rate"] = round(routed_to_llm / n, 3)
    metrics["escalation_rate"] = round(escalated / n, 3)
    metrics["cost_per_message_inr"] = None
    metrics["avg_latency_ms"] = None
    metrics["methodology_note"] = (
        "Routing decision (rule Unclear -> LLM fallback) is real and measured "
        "on this held-out set. The LLM side of that fallback reuses the same "
        "blind, unmetered predictions from my_llm_predictions.py that "
        "llm_direct_eval.py scores independently -- no live API call was made "
        "here either, so cost_per_message_inr and avg_latency_ms are null, "
        "not estimated. A live run only requires pointing extract_intent_hybrid() "
        "at default_llm_call() with ANTHROPIC_API_KEY set; the gating logic "
        "itself does not change."
    )
    misclassified = [p for p in predictions if p["true_intent"] != p["pred_intent"]]
    return predictions, metrics, misclassified


if __name__ == "__main__":
    predictions, metrics, misclassified = run_hybrid_offline_eval()
    print(f"Rule-first hybrid extraction (LLM fallback) on {metrics['n']} held-out messages:")
    print(f"  intent accuracy       {metrics['intent_accuracy']:.1%}  (macro F1 {metrics['intent_macro_f1']})")
    print(f"  per-class F1          {metrics['intent_f1_by_class']}")
    print(f"  temporal accuracy     {metrics['temporal_extraction_accuracy']:.1%}")
    print(f"  reason accuracy       {metrics['reason_extraction_accuracy']:.1%}")
    print(f"  routed to LLM         {metrics['llm_route_rate']:.1%}  (rule-based accepted the rest unconditionally)")
    print(f"  escalated to human    {metrics['escalation_rate']:.1%}  (both rule and LLM fallback returned Unclear)")
    print(f"  cost / latency        not measured (LLM side is still the blind, unmetered run -- see methodology_note)")

    print(f"\nintent misclassifications: {len(misclassified)} / {metrics['n']}")
    for p in misclassified:
        print(f"  [{p['source']}] {p['message']!r}: true={p['true_intent']!r} pred={p['pred_intent']!r}")

    with open(os.path.join(BASE_DIR, "hybrid_eval_results.json"), "w") as f:
        json.dump({"held_out_set_size": metrics["n"], "hybrid": {"metrics": metrics, "misclassified": misclassified}},
                   f, indent=2, default=str)
    print("\nwrote model/hybrid_eval_results.json")
