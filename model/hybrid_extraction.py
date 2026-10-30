"""
Module 2d: rule-first hybrid extraction, LLM fallback.

Rules run first. The LLM is consulted only when the rule-based extractor
returns "Unclear". Invalid LLM output is rejected and escalated to a human.
Offline evaluation uses saved predictions and never calls external APIs.
"""

import json
import os

from communication_intelligence import extract_intent
from llm_vs_baseline_eval import HELD_OUT_SET, _score
from my_llm_predictions import my_predictions

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

ALLOWED_INTENTS = {"Confirm", "Reschedule", "Cancel", "Unclear", "No Response"}
ALLOWED_DAYS = {
    "Monday", "Tuesday", "Wednesday", "Thursday",
    "Friday", "Saturday", "Sunday",
}
ALLOWED_REASONS = {
    "Conflicting doctor visit",
    "Work conflict",
    "Provider/patient running late",
}
ALLOWED_RELATIVE_DAYS = {"tomorrow", "weekend"}
REQUIRED_LLM_FIELDS = {
    "intent",
    "cancel_current",
    "preferred_day",
    "next_week",
    "relative_day",
    "offset_days",
    "reason",
}


def _valid_schema(pred: dict) -> bool:
    """Validate the complete live LLM contract before trusting its result."""
    if not isinstance(pred, dict) or set(pred) != REQUIRED_LLM_FIELDS:
        return False

    if pred.get("intent") not in ALLOWED_INTENTS:
        return False

    if type(pred.get("cancel_current")) is not bool:
        return False

    if type(pred.get("next_week")) is not bool:
        return False

    day = pred.get("preferred_day")
    if day is not None and day not in ALLOWED_DAYS:
        return False

    relative_day = pred.get("relative_day")
    if relative_day is not None and relative_day not in ALLOWED_RELATIVE_DAYS:
        return False

    offset = pred.get("offset_days")
    if offset is not None and (
        type(offset) is not int or offset < 0 or offset > 60
    ):
        return False

    reason = pred.get("reason")
    if reason is not None and reason not in ALLOWED_REASONS:
        return False

    return True


def default_llm_call(message: str):
    """
    Try Gemini first, then an OpenAI-compatible provider (Groq/OpenRouter),
    then Anthropic -- whichever are configured.

    Invalid provider responses are rejected. None is returned if neither
    provider produces a valid extraction.
    """
    # Public portfolio deployments can disable external model calls to avoid
    # unbounded provider cost and prevent user-submitted text leaving the demo.
    if os.getenv("CAREOPS_DISABLE_EXTERNAL_LLM", "false").strip().lower() in {"1", "true", "yes", "on"}:
        return None

    from gemini_llm import gemini_llm_call

    gemini_result = gemini_llm_call(message)
    if gemini_result is not None and _valid_schema(gemini_result):
        return gemini_result

    # Free, no-credit-card OpenAI-compatible providers (Groq, OpenRouter, ...).
    from openai_compat_llm import openai_compat_llm_call

    compat_result = openai_compat_llm_call(message)
    if compat_result is not None and _valid_schema(compat_result):
        return compat_result

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None

    try:
        import anthropic

        client = anthropic.Anthropic(
            api_key=api_key,
            timeout=15.0,
            max_retries=0,
        )

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
            messages=[
                {
                    "role": "user",
                    "content": message or "(empty message)",
                }
            ],
        )

        parsed = json.loads(resp.content[0].text.strip())
        return parsed if _valid_schema(parsed) else None

    except Exception as exc:
        # Avoid logging provider exception text or request metadata.
        print(
            "CareOps optional Anthropic fallback failed "
            f"({type(exc).__name__})."
        )
        return None


def extract_intent_hybrid(message: str, llm_call=default_llm_call) -> dict:
    """
    Production entry point.

    Accept rule-based predictions when they are not Unclear. Otherwise,
    use the LLM fallback and escalate if it cannot return a valid answer.
    """
    rule_pred = extract_intent(message)

    if rule_pred["intent"] != "Unclear":
        return {
            **rule_pred,
            "source": "rule",
            "escalate_to_human": False,
        }

    llm_pred = llm_call(message) if llm_call else None

    if (
        llm_pred is None
        or not _valid_schema(llm_pred)
        or llm_pred.get("intent") == "Unclear"
    ):
        return {
            **rule_pred,
            "source": "escalation",
            "escalate_to_human": True,
        }

    merged = {
        "intent": llm_pred.get("intent"),
        "cancel_current": llm_pred.get("cancel_current", False),
        "preferred_day": llm_pred.get("preferred_day"),
        "urgency": rule_pred["urgency"],
        "reason": llm_pred.get("reason"),
        "next_week": llm_pred.get("next_week", False),
        "relative_day": llm_pred.get("relative_day"),
        "offset_days": llm_pred.get("offset_days"),
    }

    return {
        **merged,
        "source": "llm",
        "escalate_to_human": False,
    }


def run_hybrid_offline_eval():
    """
    Evaluate the rule-first routing architecture using saved blind LLM
    predictions. This function makes no external API calls.
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

            # Saved blind predictions use the original five-field schema.
            if blind_llm_pred.get("intent") == "Unclear":
                escalated += 1
                final = rule_pred
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
            "true_temporal": (
                case["preferred_day"],
                case["next_week"],
                case["relative_day"],
                case["offset_days"],
            ),
            "pred_temporal": (
                final.get("preferred_day"),
                final.get("next_week", False),
                final.get("relative_day"),
                final.get("offset_days"),
            ),
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
        "on this held-out set. The LLM side reuses saved blind, unmetered "
        "predictions from my_llm_predictions.py; no live API call was made. "
        "Cost and latency are not measured."
    )

    misclassified = [
        p for p in predictions
        if p["true_intent"] != p["pred_intent"]
    ]

    return predictions, metrics, misclassified


if __name__ == "__main__":
    predictions, metrics, misclassified = run_hybrid_offline_eval()

    print(
        f"Rule-first hybrid extraction (LLM fallback) on "
        f"{metrics['n']} held-out messages:"
    )
    print(
        f"  intent accuracy       {metrics['intent_accuracy']:.1%} "
        f"(macro F1 {metrics['intent_macro_f1']})"
    )
    print(f"  per-class F1          {metrics['intent_f1_by_class']}")
    print(
        f"  temporal accuracy     "
        f"{metrics['temporal_extraction_accuracy']:.1%}"
    )
    print(
        f"  reason accuracy       "
        f"{metrics['reason_extraction_accuracy']:.1%}"
    )
    print(f"  routed to LLM         {metrics['llm_route_rate']:.1%}")
    print(f"  escalated to human    {metrics['escalation_rate']:.1%}")
    print("  cost / latency        not measured")

    print(f"\nintent misclassifications: {len(misclassified)} / {metrics['n']}")
    for prediction in misclassified:
        print(
            f"  [{prediction['source']}] "
            f"{prediction['message']!r}: "
            f"true={prediction['true_intent']!r} "
            f"pred={prediction['pred_intent']!r}"
        )

    with open(
        os.path.join(BASE_DIR, "hybrid_eval_results.json"),
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            {
                "held_out_set_size": metrics["n"],
                "hybrid": {
                    "metrics": metrics,
                    "misclassified": misclassified,
                },
            },
            f,
            indent=2,
            default=str,
        )

    print("\nwrote model/hybrid_eval_results.json")
