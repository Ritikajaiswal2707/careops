"""
Gemini free-tier fallback for the hybrid extractor's LLM step.

Same request/response contract as the Anthropic path this sits alongside in
hybrid_extraction.default_llm_call(): given a raw patient message, return a
dict matching extract_intent_hybrid's expected schema, or None if no usable
result could be produced (no key, network error, bad JSON). None is treated
exactly like an LLM abstention by extract_intent_hybrid() -- it escalates to
a human, it never guesses.

Plain REST call (requests) rather than the google-genai SDK, so a live
deployment doesn't need an extra SDK dependency just for one JSON-extraction
call per message.
"""
import json
import os

import requests

GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"

# Identical extraction contract to hybrid_extraction.default_llm_call()'s
# Anthropic prompt, so the two paths stay comparable and
# hybrid_extraction._valid_schema() validates either one's output the same way.
SYSTEM_PROMPT = (
    "Extract structured information from a home-healthcare patient message "
    "(English, Hindi, Hinglish, or a mix, possibly with typos). Respond with "
    "ONLY a JSON object, no other text, matching exactly:\n"
    '{"intent": "Confirm"|"Reschedule"|"Cancel"|"Unclear"|"No Response", '
    '"cancel_current": true|false, '
    '"preferred_day": "Monday".."Sunday" or null, '
    '"next_week": true|false, '
    '"relative_day": "tomorrow"|"weekend"|null, '
    '"offset_days": integer or null, '
    '"reason": "Conflicting doctor visit"|"Work conflict"|'
    '"Provider/patient running late"|null}'
)


def gemini_llm_call(message: str, timeout: int = 15):
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return None

    payload = {
        "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{"role": "user", "parts": [{"text": message or "(empty message)"}]}],
        "generationConfig": {"temperature": 0, "maxOutputTokens": 200},
    }
    try:
        resp = requests.post(GEMINI_URL, params={"key": api_key}, json=payload, timeout=timeout)
        resp.raise_for_status()
        text = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        # Gemini sometimes wraps JSON in a ```json fence despite the
        # "ONLY a JSON object" instruction -- strip it defensively.
        if text.startswith("```"):
            text = text.strip("`")
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()
        return json.loads(text)
    except (requests.RequestException, KeyError, IndexError, ValueError):
        return None


if __name__ == "__main__":
    import sys

    msg = sys.argv[1] if len(sys.argv) > 1 else "Tomorrow evening won't work, can we do Saturday morning?"
    print(gemini_llm_call(msg))
