"""Single source of truth for the structured-extraction prompt used by every LLM provider."""

EXTRACTION_PROMPT = (
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
    '"Provider/patient running late"|null}\n'
    "cancel_current is true whenever the CURRENT appointment is being "
    'dropped -- a plain cancellation, or a compound message like "cancel '
    'today\'s, I\'ll come tomorrow" that also requests a new day (which '
    "should be classified intent=Reschedule, cancel_current=true, not "
    "intent=Cancel). It is false for a plain move-only reschedule with "
    "no explicit cancel language."
)


def strip_json_fence(text: str) -> str:
    """Models sometimes wrap JSON in a ```json fence despite instructions; remove it."""
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.strip("`").strip()
        if text.lower().startswith("json"):
            text = text[4:]
    return text.strip()
