"""
Module 2: Communication intelligence.

communications.csv already ships with an `extracted_intent` label
(Confirm/Reschedule/Cancel/No Response), but nothing in the original repo
used it, and it's only a single label — not enough to act on. A coordinator
seeing "Reschedule" still has to open the raw message to find out to when,
why, and how urgently.

This module extracts a richer structure from the raw message text itself:
    { intent, preferred_day, urgency, reason }

It's a rule/keyword-based extractor, not a live LLM call (this environment
has no API key wired into the container) — but it operates on the raw text,
generalizes to messages it hasn't seen, and is validated against the CSV's
own `extracted_intent` label as a sanity check below.
"""
import re
import pandas as pd

DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

CANCEL_WORDS = ["cancel", "cant come", "can't come", "not possible", "nahi aa", "not needed"]
RESCHEDULE_WORDS = ["reschedule", "late ho", "possible?", "kar sakte", "shift", "postpone",
                    "different day", "different time", "move to", "next week"]
CONFIRM_WORDS = ["confirm", "theek hai", "yes that works", "ok confirmed", "sounds good", "see you then"]
URGENT_WORDS = ["kal", "tomorrow", "today", "aaj", "abhi", "asap", "urgent"]


def extract_intent(message: str) -> dict:
    if not isinstance(message, str) or not message.strip():
        return {"intent": "No Response", "preferred_day": None, "urgency": "Low", "reason": None}

    m = message.lower()

    if any(w in m for w in CANCEL_WORDS):
        intent = "Cancel"
    elif any(w in m for w in RESCHEDULE_WORDS):
        intent = "Reschedule"
    elif any(w in m for w in CONFIRM_WORDS):
        intent = "Confirm"
    else:
        intent = "Unclear"

    preferred_day = next((d.capitalize() for d in DAYS if d in m), None)

    urgency = "High" if any(w in m for w in URGENT_WORDS) else ("Medium" if intent == "Reschedule" else "Low")

    reason = None
    if intent != "Confirm":
        if "doctor" in m:
            reason = "Conflicting doctor visit"
        elif re.search(r"\b(work|office)\b", m):
            reason = "Work conflict"
        elif "late" in m:
            reason = "Provider/patient running late"

    return {"intent": intent, "preferred_day": preferred_day, "urgency": urgency, "reason": reason}


if __name__ == "__main__":
    comms = pd.read_csv("../data/communications.csv")
    comms["message"] = comms["message"].fillna("")

    extracted = comms["message"].apply(extract_intent).apply(pd.Series)
    comms = pd.concat([comms, extracted.add_prefix("model_")], axis=1)

    # Validate against the CSV's own ground-truth label (Confirm/Reschedule/Cancel/No Response)
    labeled = comms[comms["extracted_intent"].isin(["Confirm", "Reschedule", "Cancel", "No Response"])]
    agree = (labeled["model_intent"] == labeled["extracted_intent"]).mean()
    print(f"Rule-based extractor agrees with the dataset's own intent label on {agree:.1%} of {len(labeled)} messages")
    print(labeled[labeled["model_intent"] != labeled["extracted_intent"]][["message", "extracted_intent", "model_intent"]].head(5))

    comms.to_csv("communications_enriched.csv", index=False)
    print("wrote model/communications_enriched.csv")
