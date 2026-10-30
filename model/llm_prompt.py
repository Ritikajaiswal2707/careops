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


# v2 adds label DEFINITIONS only. It was written after the v1 error analysis
# showed the model inventing its own meaning for "No Response" and treating
# short acknowledgements as unclear. It deliberately contains no messages
# copied from either evaluation set.
LABEL_DEFINITIONS = (
    "\nLabel definitions (follow them exactly):\n"
    "- Confirm: the sender agrees the visit should go ahead as planned. Short "
    "acknowledgements count, as does a message that mentions a small delay but "
    "says they will still be there.\n"
    "- Reschedule: the sender wants the visit moved or rebooked for another time, "
    "even if no new day is given yet.\n"
    "- Cancel: the sender wants the current visit not to happen and does not ask "
    "for a new one.\n"
    "- Unclear: a real message whose intent about this visit cannot be determined "
    "-- for example a question, a complaint, a request for information, or a "
    "non-committal reply.\n"
    "- No Response: ONLY when the message is empty or has no content. Never use "
    "it for a message that contains words.\n"
    "When unsure between Unclear and any action label, choose Unclear: a human "
    "will review it."
)

PROMPTS = {
    "v1": EXTRACTION_PROMPT,
    "v2": EXTRACTION_PROMPT + LABEL_DEFINITIONS,
}


def strip_json_fence(text: str) -> str:
    """Models sometimes wrap JSON in a ```json fence despite instructions; remove it."""
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.strip("`").strip()
        if text.lower().startswith("json"):
            text = text[4:]
    return text.strip()
