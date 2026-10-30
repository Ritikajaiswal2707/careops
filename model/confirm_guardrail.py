"""
Deterministic safety check on Confirm predictions (defence in depth).

Why
---
A false confirmation is the most dangerous extraction error: the coordinator
believes a visit is on when the family has not agreed to it. Prompt v3 cut
these but did not eliminate them -- on the clean holdout, news about the
provider's delay and a weekday-change request were still read as Confirm.
A prompt is not a safety guarantee, so this layer sits after the model.

What it does
------------
It can only ever turn Confirm into "escalate to a human". It never creates a
confirmation or changes any other label, so its worst case is extra review
work, not an unsafe action. A Confirm is vetoed when the message also contains:
  1. a third party + a delay (someone else is late: says nothing about the family's agreement)
  2. change language (a weekday, "instead", "shift", "postpone", next week ...)
  3. negation ("nahi", "not", "can't" ...) -- "ok but not today" is not a confirmation
  4. nothing but gratitude ("thanks", a folded-hands emoji) -- thanking is not agreeing

Honesty note
------------
Rule 1 and 2 were motivated by errors seen on intent_holdout_v2 (one provider-delay
message, one weekday-change message). Results on that set after adding the guardrail
are therefore optimistic; a fresh set is needed to measure it cleanly. The word
lists are deliberately generic categories, not copies of holdout messages.
"""
import re

THIRD_PARTY = (
    r"sister|nurse|provider|driver|doctor|caregiver|attendant|didi|bhaiya|staff|"
    r"companion|helper|aunty|uncle ji|"
    r"नर्स|डॉक्टर|ड्राइवर"
)
DELAY = r"late|delay|delayed|behind|stuck|traffic|der|deri|der se|लेट|देर"
CHANGE = (
    r"monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
    r"somvar|mangalvar|budhvar|guruvar|shukravar|shanivar|ravivar|"
    r"instead|shift|postpone|reschedule|another day|other day|some other|next week|"
    r"agle hafte|dusre din|kisi aur din|rakh lo|rakh do|baad mein|parso|"
    r"सोमवार|मंगलवार|बुधवार|गुरुवार|शुक्रवार|शनिवार|रविवार|अगले हफ्ते|दूसरे दिन"
)
NEGATION = r"nahi|nahin|nhi|not|can't|cant|cannot|won't|wont|unable|mat|नहीं"
GRATITUDE = r"thank you|thanks|thank|thx|ty|so much|very much|a lot|shukriya|dhanyavaad|dhanyawad|धन्यवाद|शुक्रिया"


def _has(pattern, text):
    return re.search(rf"(?<![\w]){'(?:' + pattern + ')'}(?![\w])", text) is not None


def check(message: str, intent: str):
    """Return (final_intent, reason_or_None). Only ever downgrades Confirm to Unclear."""
    if intent != "Confirm":
        return intent, None
    text = (message or "").lower()
    had_gratitude = re.search(rf"(?:{GRATITUDE})|🙏", text) is not None
    leftover = re.sub(rf"(?:{GRATITUDE})|🙏", " ", text)
    # Only gratitude (plus punctuation) -- a bare thumbs-up has no gratitude and stays Confirm.
    if had_gratitude and not re.sub(r"[\W_]+", "", leftover):
        return "Unclear", "gratitude_only"
    if _has(THIRD_PARTY, text) and _has(DELAY, text):
        return "Unclear", "third_party_delay"
    if _has(CHANGE, text):
        return "Unclear", "change_language"
    if _has(NEGATION, text):
        return "Unclear", "negation"
    return intent, None
