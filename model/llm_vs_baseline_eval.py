"""
Module 2b: rule-based extractor vs. LLM, on a held-out set.

The 100% agreement number reported by communication_intelligence.py is
measured against the rules' *own* training labels — the source CSV has
only 10 unique messages, and extracted_intent was already in the dataset
the rules were written to match. That number shows the rules reproduce
their own targets, not that they generalize to phrasing they haven't seen.

This module is the actual test: a held-out set of 30 messages, hand-labeled,
written independently of communications.csv's 10 templates - deliberately
including phrasing (typos, mixed-script code-switching, sarcasm, compound
requests) the rule set was never tuned against. It scores:
  1. The existing rule-based extractor (runs unconditionally - no dependency)
  2. An LLM call via the Anthropic API (runs only if ANTHROPIC_API_KEY is
     set - this sandbox has no key wired in, same limitation the README
     already discloses for communication_intelligence.py)

This is the experiment the case study argues for: does an LLM improve
intent extraction enough to justify its added cost/latency/complexity over
a free, instant, fully-offline rule-based baseline? Answering that requires
actually running both sides - this script is set up to do that the moment
an API key is available; it does not simulate or assume an LLM result.
"""
import json
import os
from communication_intelligence import extract_intent

# ---- Held-out set --------------------------------------------------------
# Hand-labeled, written independently of communications.csv's 10 message
# templates. Mixes English, Hinglish, typos, and a few genuinely ambiguous
# cases on purpose - a rule set built for clean templates should struggle
# on some of these even if it nails the training templates perfectly.
HELD_OUT_SET = [
    {"message": "Hey, can we push this to sometime next week?", "intent": "Reschedule"},
    {"message": "Sorry yaar, kal nahi ho payega, agle hafte try karte hain",
     "intent": "Reschedule"},  # "agle hafte" = "next week" in Hindi - not in RESCHEDULE_WORDS at all
    {"message": "Confirmed, thank you!", "intent": "Confirm"},
    {"message": "haan bilkul, wahi time pe aa jaana", "intent": "Confirm"},
    {"message": "I don't think I can make it anymore, please cancel", "intent": "Cancel"},
    {"message": "mujhe nahi karna ab, cancel kar do please", "intent": "Cancel"},
    {"message": "running 10 min behind, still coming though", "intent": "Confirm"},
    {"message": "can we do Tuesday instead? something came up",
     "intent": "Reschedule"},
    {"message": "aaj cancel, kal aa jaunga", "intent": "Cancel"},  # cancel today, but mentions "kal" too
    {"message": "yes see u then", "intent": "Confirm"},
    {"message": "not sure, will confirm later", "intent": "Unclear"},
    {"message": "we're not going to need this appointment", "intent": "Cancel"},
    {"message": "can u come a bit later in the day instead? like evening?",
     "intent": "Reschedule"},  # time-of-day shift, not day shift - no weekday, no "reschedule"/"shift" keyword
    {"message": "ok", "intent": "Confirm"},
    {"message": "please don't come, we're out of town",
     "intent": "Cancel"},  # no "cancel"/"not possible" keyword at all
    {"message": "sab thik hai, appointment as is", "intent": "Confirm"},
    {"message": "any chance of moving to next monday", "intent": "Reschedule"},
    {"message": "no thanks, we'll skip this one", "intent": "Cancel"},
    {"message": "great, see you then!", "intent": "Confirm"},
    {"message": "is it possible after 5 days?", "intent": "Reschedule"},
    {"message": "kl subah nahi ho payega, weekend pe kar sakte?", "intent": "Reschedule"},
    {"message": "yep all good", "intent": "Confirm"},
    {"message": "we need to stop this service", "intent": "Cancel"},  # no "cancel" keyword
    {"message": "postponing to next week please", "intent": "Reschedule"},
    {"message": "theek h chalega", "intent": "Confirm"},
    {"message": "not today, some other day", "intent": "Reschedule"},  # vague, no weekday
    {"message": "she's not well, we'll call to rebook", "intent": "Reschedule"},  # no reschedule keyword
    {"message": "haanji sab sahi hai", "intent": "Confirm"},
    {"message": "can we push it out a bit? maybe next tuesday", "intent": "Reschedule"},
    {"message": "cant do it, sorry", "intent": "Cancel"},
]


def run_rule_based_eval():
    results = []
    for case in HELD_OUT_SET:
        pred = extract_intent(case["message"])
        results.append({
            "message": case["message"],
            "true_intent": case["intent"],
            "pred_intent": pred["intent"],
            "correct": pred["intent"] == case["intent"],
        })
    accuracy = sum(r["correct"] for r in results) / len(results)
    return results, accuracy


def run_llm_eval():
    """
    Calls the Anthropic API to extract intent for the same held-out set.
    Only runs if ANTHROPIC_API_KEY is set in the environment - this
    sandbox does not have one wired in (same disclosed limitation as
    communication_intelligence.py's docstring). Returns None if unavailable,
    rather than fabricating or estimating a result.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None

    import anthropic  # local import: only needed on this path
    client = anthropic.Anthropic(api_key=api_key)

    system = (
        "Classify the patient message into exactly one intent: "
        "Confirm, Reschedule, Cancel, or Unclear. "
        "Messages may be English, Hindi/Hinglish, or a mix, and may contain "
        "typos or informal phrasing. Respond with only the single word."
    )

    results = []
    for case in HELD_OUT_SET:
        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=10,
            system=system,
            messages=[{"role": "user", "content": case["message"]}],
        )
        pred_intent = resp.content[0].text.strip()
        results.append({
            "message": case["message"],
            "true_intent": case["intent"],
            "pred_intent": pred_intent,
            "correct": pred_intent == case["intent"],
        })
    accuracy = sum(r["correct"] for r in results) / len(results)
    return results, accuracy


if __name__ == "__main__":
    rule_results, rule_accuracy = run_rule_based_eval()
    print(f"Rule-based extractor: {rule_accuracy:.1%} accuracy on {len(HELD_OUT_SET)} held-out messages "
          f"(vs. the 100% self-agreement number on the training CSV - this is the real generalization test)")
    print("\nMisclassified:")
    for r in rule_results:
        if not r["correct"]:
            print(f"  \"{r['message']}\" -> predicted {r['pred_intent']}, actually {r['true_intent']}")

    llm_out = run_llm_eval()
    output = {
        "held_out_set_size": len(HELD_OUT_SET),
        "rule_based": {
            "accuracy": round(rule_accuracy, 3),
            "misclassified": [r for r in rule_results if not r["correct"]],
        },
        "llm": None,
    }
    if llm_out:
        llm_results, llm_accuracy = llm_out
        print(f"\nLLM (claude-sonnet-4-6): {llm_accuracy:.1%} accuracy on the same held-out set")
        output["llm"] = {
            "accuracy": round(llm_accuracy, 3),
            "misclassified": [r for r in llm_results if not r["correct"]],
        }
    else:
        print("\nLLM comparison skipped: no ANTHROPIC_API_KEY in this environment. "
              "Set the key and re-run to get the actual head-to-head result - "
              "this script does not simulate or assume one.")

    with open("llm_vs_baseline_results.json", "w") as f:
        json.dump(output, f, indent=2)
    print("\nwrote model/llm_vs_baseline_results.json")
