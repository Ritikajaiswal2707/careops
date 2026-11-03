"""The Confirm guardrail may only ever downgrade Confirm to a human review."""
import json

import pytest

import confirm_guardrail
import hybrid_extraction
import summarize_llm_evals


@pytest.mark.parametrize("message,reason", [
    ("The caregiver is running late", "third_party_delay"),
    ("driver traffic mein phasa hai", "third_party_delay"),
    ("ok, but Tuesday rakh lo", "change_language"),
    ("ok fine, shift it to next week", "change_language"),
    ("ok but not today", "negation"),
    ("Thanks!", "gratitude_only"),
    ("🙏", "gratitude_only"),
    ("shukriya", "gratitude_only"),
])
def test_unsafe_confirms_are_downgraded(message, reason):
    assert confirm_guardrail.check(message, "Confirm") == ("Unclear", reason)


@pytest.mark.parametrize("message", ["yes", "👍", "Confirmed, thank you!", "theek hai, aa jaiye",
                                     "running 5 min late but we'll be there"])
def test_genuine_confirms_pass(message):
    assert confirm_guardrail.check(message, "Confirm") == ("Confirm", None)


@pytest.mark.parametrize("intent", ["Reschedule", "Cancel", "Unclear", "No Response"])
def test_never_touches_other_labels(intent):
    # Even a message that would trigger every rule is left alone if it is not a Confirm.
    assert confirm_guardrail.check("Thanks, the nurse is late, not Monday", intent) == (intent, None)


def test_hybrid_escalates_vetoed_llm_confirm():
    def fake_llm(message):
        return {"intent": "Confirm", "cancel_current": False, "preferred_day": None, "next_week": False,
                "relative_day": None, "offset_days": None, "reason": None}

    out = hybrid_extraction.extract_intent_hybrid("the attendant is stuck in traffic", llm_call=fake_llm)
    assert out["intent"] == "Unclear" and out["escalate_to_human"] is True
    assert out["source"] == "guardrail" and out["guardrail_reason"] == "third_party_delay"


def test_summary_rescores_saved_runs(tmp_path):
    run = {"model": "m", "prompt_version": "v3", "suite": "holdout2", "metrics": {"p50_latency_ms": 1.0},
           "predictions": [
               {"message": "Thanks.", "true_intent": "Unclear", "pred_intent": "Confirm"},
               {"message": "yes", "true_intent": "Confirm", "pred_intent": "Confirm"},
           ]}
    path = tmp_path / "x_eval.json"
    path.write_text(json.dumps(run))
    (row,) = summarize_llm_evals.summarize([str(path)])
    assert row["raw"]["false_confirmations"] == 1 and row["raw"]["intent_accuracy"] == 0.5
    assert row["with_guardrail"]["false_confirmations"] == 0 and row["with_guardrail"]["intent_accuracy"] == 1.0
    assert row["with_guardrail"]["true_confirms_sent_to_human"] == 0
