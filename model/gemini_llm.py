"""
Gemini fallback for CareOps hybrid communication extraction.

Uses Gemini's REST generateContent endpoint with structured JSON output.

Environment variables:
    GEMINI_API_KEY
    GEMINI_MODEL (optional)

Default model:
    gemini-3.5-flash
"""

import json
import os
import sys
from typing import Any, Optional

import requests


# ---------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------

GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")

GEMINI_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/"
    f"models/{GEMINI_MODEL}:generateContent"
)


# ---------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------

SYSTEM_PROMPT = """
You extract structured information from home-healthcare patient messages.

Messages may be written in English, Hindi, Hinglish, mixed language, or
contain spelling mistakes.

Your job is to identify the ACTION the patient actually wants.

Rules:

1. Confirm means the patient is confirming the current appointment.

2. Cancel means the patient wants to cancel the current appointment and does
   not request another appointment.

3. Reschedule means the patient wants to move the appointment to another
   date/time.

4. If the patient says something like:
   "cancel today and book Saturday"
   classify as Reschedule with cancel_current=true.

5. preferred_day MUST represent the NEW REQUESTED DAY.
   Do not put a day here merely because the patient mentioned that day.

6. If the patient says:
   "Tomorrow won't work, Saturday morning possible?"
   preferred_day = "Saturday".

7. next_week=true only when the requested new date is in the following
   calendar week.

8. relative_day may be:
   "tomorrow"
   "weekend"
   or "" when not applicable.

9. offset_days should be a non-negative integer only when the patient
   explicitly asks for a relative offset such as:
   "in 3 days".
   Otherwise use -1.

10. reason must be exactly one of:
    "Conflicting doctor visit"
    "Work conflict"
    "Provider/patient running late"
    or "" when not applicable.

11. If the request is genuinely ambiguous, use intent="Unclear".

Return ONLY the JSON object.
""".strip()


# ---------------------------------------------------------------------
# Gemini structured-output schema
# ---------------------------------------------------------------------
#
# We intentionally use only simple protobuf Schema types here.
# Nullable JSON-schema arrays such as ["string", "null"] are not used.
# Non-applicable values are represented with sentinels and normalized
# back to Python None after the API response.
# ---------------------------------------------------------------------

RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "intent": {
            "type": "STRING",
            "enum": [
                "Confirm",
                "Reschedule",
                "Cancel",
                "Unclear",
                "No Response",
            ],
        },
        "cancel_current": {
            "type": "BOOLEAN",
        },
        "preferred_day": {
            "type": "STRING",
            "description": (
                "Requested new weekday. Use Monday-Sunday, or empty string "
                "when no new weekday was requested."
            ),
        },
        "next_week": {
            "type": "BOOLEAN",
        },
        "relative_day": {
            "type": "STRING",
            "description": (
                'Use "tomorrow" or "weekend", or empty string when not '
                "applicable."
            ),
        },
        "offset_days": {
            "type": "INTEGER",
            "description": (
                "Use a non-negative integer for an explicit relative "
                "offset such as 'in 3 days'. Use -1 otherwise."
            ),
        },
        "reason": {
            "type": "STRING",
            "description": (
                "Use exactly one allowed reason or empty string when "
                "not applicable."
            ),
        },
    },
    "required": [
        "intent",
        "cancel_current",
        "preferred_day",
        "next_week",
        "relative_day",
        "offset_days",
        "reason",
    ],
}


# ---------------------------------------------------------------------
# Validation / normalization
# ---------------------------------------------------------------------

VALID_INTENTS = {
    "Confirm",
    "Reschedule",
    "Cancel",
    "Unclear",
    "No Response",
}

VALID_DAYS = {
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
}

VALID_RELATIVE_DAYS = {
    "tomorrow",
    "weekend",
}

VALID_REASONS = {
    "Conflicting doctor visit",
    "Work conflict",
    "Provider/patient running late",
}


def _normalize_result(result: Any) -> Optional[dict]:
    """
    Validate Gemini output and convert sentinel values to the schema
    expected by CareOps.
    """

    if not isinstance(result, dict):
        return None

    required = {
        "intent",
        "cancel_current",
        "preferred_day",
        "next_week",
        "relative_day",
        "offset_days",
        "reason",
    }

    if not required.issubset(result.keys()):
        return None

    intent = result.get("intent")

    if intent not in VALID_INTENTS:
        return None

    preferred_day = result.get("preferred_day")

    if preferred_day == "":
        preferred_day = None
    elif preferred_day not in VALID_DAYS:
        preferred_day = None

    relative_day = result.get("relative_day")

    if relative_day == "":
        relative_day = None
    elif relative_day not in VALID_RELATIVE_DAYS:
        relative_day = None

    offset_days = result.get("offset_days")

    if offset_days == -1:
        offset_days = None
    elif not isinstance(offset_days, int) or offset_days < 0:
        offset_days = None

    reason = result.get("reason")

    if reason == "":
        reason = None
    elif reason not in VALID_REASONS:
        reason = None

    cancel_current = result.get("cancel_current")

    if not isinstance(cancel_current, bool):
        return None

    next_week = result.get("next_week")

    if not isinstance(next_week, bool):
        return None

    return {
        "intent": intent,
        "cancel_current": cancel_current,
        "preferred_day": preferred_day,
        "next_week": next_week,
        "relative_day": relative_day,
        "offset_days": offset_days,
        "reason": reason,
    }


# ---------------------------------------------------------------------
# Gemini call
# ---------------------------------------------------------------------

def gemini_llm_call(
    message: str,
    timeout: int = 20,
) -> Optional[dict]:
    """
    Call Gemini and return a normalized CareOps extraction.

    Returns None when:
      - API key is missing
      - request fails
      - API returns an error
      - Gemini returns malformed JSON
      - response fails validation
    """

    api_key = os.environ.get("GEMINI_API_KEY")

    if not api_key:
        print("GEMINI_API_KEY is not set.", file=sys.stderr)
        return None

    payload = {
        "systemInstruction": {
            "parts": [
                {
                    "text": SYSTEM_PROMPT,
                }
            ]
        },
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "text": (
                            message.strip()
                            if message
                            else "(empty message)"
                        ),
                    }
                ],
            }
        ],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": RESPONSE_SCHEMA,

            # Gemini 3.5 Flash supports minimal thinking.
            # This task is simple structured extraction, so we don't need
            # medium/high reasoning effort.
            "thinkingConfig": {
                "thinkingLevel": "minimal"
            },

            # Give the model enough room for both minimal reasoning and
            # the structured JSON response.
            "maxOutputTokens": 512,
        },
    }

    headers = {
        "x-goog-api-key": api_key,
        "Content-Type": "application/json",
    }

    try:
        response = requests.post(
            GEMINI_URL,
            headers=headers,
            json=payload,
            timeout=timeout,
        )

        if not response.ok:
            print(
                f"Gemini API error {response.status_code}: "
                f"{response.text[:3000]}",
                file=sys.stderr,
            )
            return None

        body = response.json()

        candidates = body.get("candidates", [])

        if not candidates:
            print(
                "Gemini returned no candidates.",
                file=sys.stderr,
            )
            return None

        first_candidate = candidates[0]

        finish_reason = first_candidate.get("finishReason")

        parts = (
            first_candidate
            .get("content", {})
            .get("parts", [])
        )

        if not parts:
            print(
                f"Gemini returned no content parts. "
                f"finishReason={finish_reason}",
                file=sys.stderr,
            )
            return None

        text = parts[0].get("text")

        if not text:
            print(
                f"Gemini returned empty text. "
                f"finishReason={finish_reason}",
                file=sys.stderr,
            )
            return None

        # Structured output should already be valid JSON.
        result = json.loads(text)

        return _normalize_result(result)

    except requests.RequestException as exc:
        print(
            f"Gemini request failed: {exc}",
            file=sys.stderr,
        )
        return None

    except json.JSONDecodeError as exc:
        print(
            f"Gemini returned invalid JSON: {exc}",
            file=sys.stderr,
        )
        return None

    except (TypeError, KeyError, IndexError) as exc:
        print(
            f"Gemini response parsing failed: {exc}",
            file=sys.stderr,
        )
        return None


# ---------------------------------------------------------------------
# Command-line test
# ---------------------------------------------------------------------

if __name__ == "__main__":
    message = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "Tomorrow evening won't work, can we do Saturday morning?"
    )

    result = gemini_llm_call(message)

    if result is None:
        print("None")
    else:
        print(
            json.dumps(
                result,
                ensure_ascii=False,
                indent=2,
            )
        )