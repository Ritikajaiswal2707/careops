"""
Module 2: Communication intelligence.

communications.csv already ships with an `extracted_intent` label
(Confirm/Reschedule/Cancel/No Response), but nothing in the original repo
used it, and it's only a single label — not enough to act on. A coordinator
seeing "Reschedule" still has to open the raw message to find out to when,
why, and how urgently.

This module extracts a richer structure from the raw message text itself:
    { intent, cancel_current, preferred_day, urgency, reason }

cancel_current exists because a single Cancel/Reschedule label can't
represent a compound request -- "cancel today's, I'll come tomorrow" is
asking to drop the current slot AND book a new one in the same breath.
Forcing that into one label is what produced two real misses in the P0
evaluation (see model/communication_eval eval notes / README); the fix
was to add this second boolean rather than add more single-choice labels.

It's a rule/keyword-based extractor, not a live LLM call (this environment
has no API key wired into the container) — but it operates on the raw text,
generalizes to messages it hasn't seen, and is validated against the CSV's
own `extracted_intent` label as a sanity check below.
"""
import os
import re
import pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "..", "data")

DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

CANCEL_WORDS = [
    "cancel", "cant come", "can't come", "not possible", "nahi aa", "not needed",
    "drop the visit", "drop this visit", "no longer need it", "don't send the nurse",
    "do not send the nurse", "stop sending the nurse", "no need for the nurse",
    "discontinue the home visit", "discontinue the visit", "call off", "won't need the nurse",
    "will not need the nurse", "nurse not needed anymore", "no need to send anyone",
    "withdraw the booking", "withdraw this booking", "no need to send anyone for this appointment",
    "no longer required", "don't need to send anyone", "do not need to send anyone",
    "skip the visit", "skip this visit", "skip the nurse visit", "remove this booking", "remove the booking",
    "booking is no longer needed", "appointment is no longer needed", "please withdraw",
    "we need to cancel", "need to cancel the visit", "cancel the booking", "cancel this booking",
    "don't send anyone", "do not send anyone", "don't need the nurse anymore", "do not need the nurse anymore", "nurse visit isn't needed", "nurse visit is not needed",
]
RESCHEDULE_WORDS = ["reschedule", "late ho", "possible?", "kar sakte", "shift", "postpone",
                    "different day", "different time", "different slot", "move to", "move it", "move my", "move the",
                    "set it for", "schedule for", "book for", "make it later", "move it earlier", "move it back", "another day", "another slot",
                    "rearrange", "another time", "another date", "change the timing", "move the visit",
                    "move the appointment", "push the appointment", "push my appointment", "push my mother's appointment",
                    "push my mother's appointment", "push my", "later in the day", "a little later",
                    "in the evening instead", "evening instead", "next week", "agle hafte",
                    "try karte hain", "nahi ho payega", "weekend",
                    "change the visit to", "change my visit to", "change the appointment to",
                    "change my appointment to", "change the date", "change my date",
                    "move the date", "shift the date", "shift the visit", "shift the appointment",
                    "postpone it", "postpone the visit", "postpone the appointment", "push it to",
                    "move it to", "move this to", "swap the slot", "switch the slot",
                    "change the slot", "different appointment time", "later this week",
                    "earlier in the day", "in the afternoon instead", "in the morning instead",
                    "can we change", "could we change", "can we move", "could we move",
                    "can we reschedule", "could we reschedule", "can we shift", "could we shift"]
CONFIRM_WORDS = ["confirm", "theek hai", "yes that works", "ok confirmed", "sounds good",
                 "see you then", "i will be there", "i'll be there", "will attend",
                 "that works for us", "all good for the scheduled visit", "yep, all good",
                 "okay, that works", "ok, that works", "keep the appointment as planned",
                 "confirmed, we'll be home", "haan, sunday theek hai", "original time is fine",
                 "available rahenge", "hum available rahenge", "we'll be available", "we will be available",
                 "hum ghar par milenge", "scheduled time suits us", "time suits us", "we are available", "we will be home", "we'll be home",
                 "we can be home", "we can make that time", "that time is okay",
                 "that time is okay for us", "we can attend as scheduled",
                 "we'll be there", "we will be there", "we will attend the visit",
                 "yes, please keep it", "please keep the appointment", "keep it as scheduled",
                 "works for me", "that works for me", "works for us", "we are good for that time",
                 "we can make it", "we'll make it", "we will make it", "we are okay with that",
                 "yes that is fine", "yes, that is fine", "appointment is fine",
                 "the appointment is fine", "visit is fine", "confirmed for that time",
                 "yes, confirmed", "yes confirmed"]
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
    if offset_match is None:
        offset_match = re.search(r"(\d+)\s+days?\s+from now", m)
    offset_days = int(offset_match.group(1)) if offset_match else None
    if offset_days is None:
        number_words = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
                        "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
        word_offset = re.search(r"after\s+(one|two|three|four|five|six|seven|eight|nine|ten)\s+days?", m)
        if word_offset is None:
            word_offset = re.search(r"(one|two|three|four|five|six|seven|eight|nine|ten)\s+days?\s+from now", m)
        if word_offset:
            offset_days = number_words[word_offset.group(1)]

    relative = None
    if "tomorrow" in m or re.search(r"\bkal\b", m):
        relative = "tomorrow"
    elif "weekend" in m:
        relative = "weekend"

    day = next((d.capitalize() for d in DAYS if d in m), None)
    next_week = bool(re.search(r"\bnext\s+week\b", m) or re.search(r"\bagle\s+hafte\b", m)) or (
        day is not None and re.search(rf"\bnext\s+{day.lower()}\b", m) is not None
    )

    return {"day": day, "next_week": next_week, "relative": relative, "offset_days": offset_days}


def extract_intent(message: str) -> dict:
    if not isinstance(message, str) or not message.strip():
        return {"intent": "No Response", "cancel_current": False, "preferred_day": None, "urgency": "Low",
                "reason": None, "next_week": False, "relative_day": None, "offset_days": None}

    m = message.lower().strip()

    # A negated cancellation is not a cancellation. If the user says not to
    # cancel yet or says they will confirm later, abstain rather than taking
    # an irreversible interpretation from the word "cancel" alone.
    negated_cancel_patterns = (
        r"\b(?:don't|do not|dont)\s+(?:cancel|drop)\b",
        r"\bnot\s+(?:cancel|cancelling|canceled|cancelled)\b",
        r"\bnot\s+(?:asking|trying|looking)\s+to\s+(?:cancel|drop)\b",
        r"\bwithout\s+cancelling\b",
    )
    deferred_confirmation_patterns = (
        r"\b(?:i|we)\s+(?:will|\x27ll|ll)\s+confirm\s+(?:later|soon)\b",
        r"\bconfirm\s+later\b",
        r"\bwill\s+let\s+you\s+know\b",
        r"\b(?:i|we)\s+(?:cannot|can't|cant)\s+confirm\b",
        r"\bnot\s+able\s+to\s+confirm\b",
        r"\bnot\s+confirmed\s+yet\b",
    )
    if any(re.search(pattern, m) for pattern in negated_cancel_patterns + deferred_confirmation_patterns):
        return {"intent": "Unclear", "cancel_current": False, "preferred_day": None,
                "urgency": "Low", "reason": None, "next_week": False,
                "relative_day": None, "offset_days": None}

    has_cancel = any(w in m for w in CANCEL_WORDS)
    has_reschedule_word = any(w in m for w in RESCHEDULE_WORDS)

    temporal = parse_temporal(message)
    has_temporal_signal = (
        temporal["day"] is not None
        or temporal["relative"] is not None
        or temporal["offset_days"] is not None
    )

    # Compound requests ("aaj cancel, kal aa jaunga" / "cancel karo aur
    # Wednesday ko fix kar do") say "cancel" but are asking to move the
    # appointment to a new day, not to drop it with nothing booked in its
    # place. A single Cancel/Reschedule label can't represent "cancel THIS
    # one and book a new one" -- forcing it into one bucket is what
    # produced the taxonomy gap the eval found (see communication_eval.json
    # cases 50 and 81). cancel_current disambiguates: true whenever the
    # current slot is being dropped, independent of whether a new one is
    # being requested in the same message.
    if has_cancel and (has_reschedule_word or has_temporal_signal):
        intent = "Reschedule"
        cancel_current = True
    elif has_cancel:
        intent = "Cancel"
        cancel_current = True
    elif has_reschedule_word:
        intent = "Reschedule"
        cancel_current = False
    elif any(w in m for w in CONFIRM_WORDS):
        intent = "Confirm"
        cancel_current = False
    else:
        intent = "Unclear"
        cancel_current = False

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
        # True whenever the current appointment is being dropped -- for a
        # plain Cancel, or for a compound "cancel + rebook" message that
        # still classifies as Reschedule. False for a plain move-only
        # Reschedule, where the old slot is implicitly replaced rather than
        # explicitly cancelled.
        "cancel_current": cancel_current,
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
    comms = pd.read_csv(os.path.join(DATA_DIR, "communications.csv"))
    comms["message"] = comms["message"].fillna("")

    extracted = comms["message"].apply(extract_intent).apply(pd.Series)
    comms = pd.concat([comms, extracted.add_prefix("model_")], axis=1)

    # Validate against the CSV's own ground-truth label (Confirm/Reschedule/Cancel/No Response)
    labeled = comms[comms["extracted_intent"].isin(["Confirm", "Reschedule", "Cancel", "No Response"])]
    agree = (labeled["model_intent"] == labeled["extracted_intent"]).mean()
    print(f"Rule-based extractor agrees with the dataset's own intent label on {agree:.1%} of {len(labeled)} messages")
    print(labeled[labeled["model_intent"] != labeled["extracted_intent"]][["message", "extracted_intent", "model_intent"]].head(5))

    out_path = os.path.join(BASE_DIR, "communications_enriched.csv")
    comms.to_csv(out_path, index=False)
    print(f"wrote {out_path}")
