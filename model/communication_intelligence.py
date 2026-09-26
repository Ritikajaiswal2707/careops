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
                    "different day", "different time", "move to", "next week", "weekend"]
CONFIRM_WORDS = ["confirm", "theek hai", "yes that works", "ok confirmed", "sounds good", "see you then"]
URGENT_WORDS = ["kal", "tomorrow", "today", "aaj", "abhi", "asap", "urgent"]


def parse_temporal(message: str) -> dict:
    """
    Pulls relative/explicit date language out of a message. Returns a
    structured description that reschedule_agent.py resolves against the
    appointment's actual date -- this module only sees the raw text, not
    which appointment it belongs to, so it can't compute a real date itself.

    Handles: an explicit weekday name ("Saturday"), "next <weekday>"
    (read as the following week's occurrence, not the nearest one),
    "next week" / "sometime next week" with no day named, "tomorrow" /
    "kal", "this weekend", and "after N days".

    This exists because the original extractor only recognized literal
    weekday names. "Can we move to next week?" matched none of them, so
    preferred_day came back None and the agent silently fell back to
    "tomorrow-ish" (orig_date + 1-3 days) -- the exact opposite of what
    the patient asked for.

    Known limitation: "next Tuesday" is genuinely ambiguous in everyday
    usage -- some people mean the very next occurrence, others mean the
    one after. This always reads "next <weekday>" as the following
    week's occurrence (the more common colloquial reading), which is a
    judgment call, not a solved problem.
    """
    if not isinstance(message, str):
        return {"day": None, "next_week": False, "relative": None, "offset_days": None}

    m = message.lower()

    offset_match = re.search(r"after (\d+)\s*days?", m)
    offset_days = int(offset_match.group(1)) if offset_match else None

    relative = None
    if "tomorrow" in m or re.search(r"\bkal\b", m):
        relative = "tomorrow"
    elif "weekend" in m:
        relative = "weekend"

    day = next((d.capitalize() for d in DAYS if d in m), None)
    next_week = bool(re.search(r"\bnext\s+week\b", m)) or (
        day is not None and re.search(rf"\bnext\s+{day.lower()}\b", m) is not None
    )

    return {"day": day, "next_week": next_week, "relative": relative, "offset_days": offset_days}


def extract_intent(message: str) -> dict:
    if not isinstance(message, str) or not message.strip():
        return {"intent": "No Response", "preferred_day": None, "urgency": "Low", "reason": None,
                "next_week": False, "relative_day": None, "offset_days": None}

    m = message.lower()

    if any(w in m for w in CANCEL_WORDS):
        intent = "Cancel"
    elif any(w in m for w in RESCHEDULE_WORDS):
        intent = "Reschedule"
    elif any(w in m for w in CONFIRM_WORDS):
        intent = "Confirm"
    else:
        intent = "Unclear"

    temporal = parse_temporal(message)

    urgency = "High" if any(w in m for w in URGENT_WORDS) else ("Medium" if intent == "Reschedule" else "Low")

    reason = None
    if intent != "Confirm":
        if "doctor" in m:
            reason = "Conflicting doctor visit"
        elif re.search(r"\b(work|office)\b", m):
            reason = "Work conflict"
        elif "late" in m:
            reason = "Provider/patient running late"

    return {
        "intent": intent,
        "preferred_day": temporal["day"],
        "urgency": urgency,
        "reason": reason,
        # Richer temporal signal reschedule_agent.py resolves into candidate
        # dates -- see parse_temporal() above.
        "next_week": temporal["next_week"],
        "relative_day": temporal["relative"],
        "offset_days": temporal["offset_days"],
    }


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
