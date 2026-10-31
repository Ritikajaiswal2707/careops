"""
Voice visit reports: caregiver voice note -> transcript -> structured report -> family update.

Pipeline
--------
1. transcribe()       speech to text with an OpenAI-compatible Whisper endpoint
                      (Groq's free whisper-large-v3 by default)
2. structure()        an LLM turns the transcript into JSON: vitals, medicines,
                      observations, concerns and a plain-language family summary
3. apply_safety()     deterministic checks that run AFTER the model and can only
                      make the report more cautious:
                        - grounding: a vital value must appear as a number in the
                          transcript; anything else is moved to `unverified_vitals`
                          and the report goes to a coordinator
                        - red flags: configurable thresholds and keywords force a
                          coordinator review regardless of what the model says;
                          every reading in the note is scanned, not only the one
                          value the model reported
                        - the family summary is released only when no review is needed

The red-flag thresholds are illustrative routing rules for a portfolio demo, not
clinical guidance. They only decide whether a human looks at the report first.
"""
from __future__ import annotations

import json
import os
import re

import requests

import openai_compat_llm
from llm_prompt import strip_json_fence

# 1.0: grounding + red flags on the reported values. 1.1: also scans every reading in the note.
SAFETY_VERSION = "1.1"

VITAL_FIELDS = ["bp_systolic", "bp_diastolic", "blood_sugar_mg_dl", "spo2_pct", "pulse_bpm", "temperature_f"]

REPORT_PROMPT = (
    "You turn a home-care visit note (English, Hindi, Hinglish or a mix, possibly "
    "transcribed from speech) into a structured report. Respond with ONLY a JSON "
    "object, no other text, matching exactly:\n"
    '{"vitals": {"bp_systolic": int|null, "bp_diastolic": int|null, '
    '"blood_sugar_mg_dl": int|null, "spo2_pct": int|null, "pulse_bpm": int|null, '
    '"temperature_f": number|null}, '
    '"medications": [string], "observations": [string], "concerns": [string], '
    '"family_summary": string}\n'
    "Rules:\n"
    "- Record a vital ONLY if the note states its value. If a vital is not "
    "mentioned, use null. Never estimate, infer or fill in a 'normal' value.\n"
    "- Convert spoken numbers to digits (for example 'ek sau bees' is 120).\n"
    "- concerns: anything the caregiver flags as worrying, in their words.\n"
    "- family_summary: 2-3 short, warm sentences for the patient's family, in "
    "simple English. Describe what was observed and done. Do not diagnose, do not "
    "give medical advice, and do not mention any number that is not in the note."
)

# Illustrative escalation thresholds (not clinical guidance): outside these, a
# coordinator reviews the report before anything reaches the family.
RED_FLAG_RULES = {
    "spo2_pct": lambda v: v < 92,
    "bp_systolic": lambda v: v < 90 or v >= 180,
    "bp_diastolic": lambda v: v >= 120,
    "blood_sugar_mg_dl": lambda v: v < 70 or v > 300,
    "pulse_bpm": lambda v: v < 50 or v > 120,
    "temperature_f": lambda v: v >= 102.2,
}
# Every reading mentioned in the note is scanned, not only the one value the
# model chose to report: "sugar 62 ... 15 min baad 88" must escalate on 62 even
# if the model reports the later, normal 88. A number counts as a reading of a
# vital if it follows that vital's keyword (before the next vital keyword) and
# lies in a physiologically plausible range, which excludes things like "15 min".
READING_KEYWORDS = {
    "blood_sugar_mg_dl": (r"sugar|glucose|shugar|शुगर", (20, 700)),
    "spo2_pct": (r"spo2|oxygen|o2|saturation|ऑक्सीजन", (50, 100)),
    "pulse_bpm": (r"pulse|heart rate|nabz|नब्ज़|पल्स", (20, 250)),
    "temperature_f": (r"temperature|temp|bukhar|fever|बुखार|तापमान", (90, 110)),
    "bp": (r"bp|blood pressure|बीपी", None),
}

RED_FLAG_WORDS = (
    r"chest pain|seene mein dard|seene me dard|breathless|saans (?:lene mein|me|mein) (?:dikkat|taklif|problem)|"
    r"saans phool|fell|fall|gir gay[ae]|gir gai|behosh|unconscious|fainted|confus|bleeding|khoon|"
    r"chakkar|dizzy|seizure|daura|vomit(?:ing)? blood|slurred|"
    r"सीने में दर्द|सांस|गिर गए|गिर गई|बेहोश|चक्कर"
)


# --------------------------------------------------------------------------- #
def transcribe(audio_path, timeout=60, post=requests.post):
    """Speech to text via an OpenAI-compatible /audio/transcriptions endpoint.
    Uses LLM_PROVIDER/LLM_BASE_URL + LLM_API_KEY; STT_MODEL defaults to whisper-large-v3.
    Returns (text_or_None, error_or_None). Never logs the key or the audio."""
    cfg = openai_compat_llm.config_base()
    if cfg is None:
        return None, "speech-to-text is not configured"
    base_url, api_key = cfg
    model = os.environ.get("STT_MODEL", "whisper-large-v3")
    try:
        with open(audio_path, "rb") as f:
            resp = post(
                f"{base_url}/audio/transcriptions",
                headers={"Authorization": f"Bearer {api_key}"},
                files={"file": (os.path.basename(audio_path), f)},
                data={"model": model, "temperature": "0", "response_format": "json"},
                timeout=timeout,
            )
    except (OSError, requests.RequestException) as exc:
        return None, f"transcription failed ({type(exc).__name__})"
    if resp.status_code != 200:
        return None, f"transcription failed (HTTP {resp.status_code})"
    try:
        text = (resp.json().get("text") or "").strip()
    except ValueError:
        return None, "transcription response was not JSON"
    return (text, None) if text else (None, "empty transcript")


def structure(transcript, base_url, api_key, model, post=requests.post, timeout=30):
    """LLM structuring. Returns (report_dict_or_None, error_or_None, usage)."""
    try:
        resp = openai_compat_llm.chat_extract(transcript, base_url, api_key, model, timeout=timeout,
                                              post=post, system=REPORT_PROMPT)
    except requests.RequestException as exc:
        return None, type(exc).__name__, {}
    if resp.status_code != 200:
        return None, f"HTTP {resp.status_code}", {}
    body = resp.json()
    usage = body.get("usage") or {}
    try:
        report = json.loads(strip_json_fence(body["choices"][0]["message"]["content"]))
    except (KeyError, IndexError, TypeError, ValueError):
        return None, "invalid_json", usage
    if not isinstance(report, dict) or not isinstance(report.get("vitals"), dict):
        return None, "invalid_schema", usage
    return report, None, usage


# --------------------------------------------------------------------------- #
def _numbers_in(text):
    return {float(n) for n in re.findall(r"\d+(?:\.\d+)?", text or "")}


def _as_number(v):
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str) and re.fullmatch(r"\s*\d+(?:\.\d+)?\s*", v):
        return float(v)
    return None


def scan_readings(transcript):
    """All plausible readings per vital stated as digits anywhere in the note."""
    text = (transcript or "").lower()
    marks = sorted((m.start(), m.end(), field) for field, (pat, _) in READING_KEYWORDS.items()
                   for m in re.finditer(rf"(?<![a-z])(?:{pat})(?![a-z])", text))
    readings = {}
    for i, (_, end, field) in enumerate(marks):
        window = text[end: marks[i + 1][0] if i + 1 < len(marks) else len(text)]
        if field == "bp":
            for sys_, dia in re.findall(r"(\d{2,3})\s*(?:/|by|on)\s*(\d{2,3})", window):
                if 50 <= int(sys_) <= 260 and 30 <= int(dia) <= 160:
                    readings.setdefault("bp_systolic", []).append(float(sys_))
                    readings.setdefault("bp_diastolic", []).append(float(dia))
            continue
        low, high = READING_KEYWORDS[field][1]
        for n in re.findall(r"\d+(?:\.\d+)?", window):
            if low <= float(n) <= high:
                readings.setdefault(field, []).append(float(n))
    return readings


def apply_safety(transcript, report):
    """Deterministic post-checks. Only ever makes the report more cautious."""
    spoken = _numbers_in(transcript)
    vitals_in = report.get("vitals") or {}
    verified, unverified = {}, {}
    for field in VITAL_FIELDS:
        value = _as_number(vitals_in.get(field))
        if value is None:
            verified[field] = None
            continue
        if value in spoken:
            verified[field] = int(value) if value.is_integer() and field != "temperature_f" else value
        else:
            # Could be a spoken number the model converted, or an invented value.
            # Either way a human checks it before anyone relies on it.
            verified[field] = None
            unverified[field] = value

    red_flags = []
    for field, value in {**{k: v for k, v in verified.items() if v is not None}, **unverified}.items():
        if RED_FLAG_RULES[field](float(value)):
            red_flags.append(f"{field}={value}")
    # Readings the model did not report (e.g. an earlier low value) still escalate.
    for field, values in scan_readings(transcript).items():
        for value in values:
            flag = f"{field}={value}"
            if RED_FLAG_RULES[field](value) and flag not in red_flags and f"{field}={int(value)}" not in red_flags:
                red_flags.append(f"note mentions {flag}")
    words = sorted({m.group(0) for m in re.finditer(RED_FLAG_WORDS, (transcript or "").lower())})
    red_flags += [f"keyword:{w}" for w in words]

    needs_review = bool(unverified or red_flags)
    review_reasons = []
    if unverified:
        review_reasons.append("vital value not found as a number in the note: " + ", ".join(sorted(unverified)))
    if red_flags:
        review_reasons.append("red flag: " + ", ".join(red_flags))

    return {
        "vitals": verified,
        "unverified_vitals": unverified,
        "medications": [str(x) for x in report.get("medications") or []],
        "observations": [str(x) for x in report.get("observations") or []],
        "concerns": [str(x) for x in report.get("concerns") or []],
        "red_flags": red_flags,
        "needs_coordinator_review": needs_review,
        "review_reasons": review_reasons,
        # The family update is held whenever a human needs to look first.
        "family_summary": None if needs_review else str(report.get("family_summary") or "").strip() or None,
        "draft_family_summary": str(report.get("family_summary") or "").strip() or None,
    }


def build_report(transcript, post=requests.post):
    """Transcript -> safe report. Without LLM config, or with external LLM calls disabled,
    returns a report that simply asks for coordinator review (fails closed)."""
    if os.getenv("CAREOPS_DISABLE_EXTERNAL_LLM", "false").strip().lower() in {"1", "true", "yes", "on"}:
        return _fail_closed(transcript, "external LLM calls are disabled in this deployment")
    cfg = openai_compat_llm.config()
    if cfg is None:
        return _fail_closed(transcript, "LLM is not configured")
    base_url, api_key, model = cfg
    report, err, _ = structure(transcript, base_url, api_key, model, post=post)
    if report is None:
        return _fail_closed(transcript, f"report could not be generated ({err})")
    return {**apply_safety(transcript, report), "transcript": transcript, "model": model}


def _fail_closed(transcript, reason):
    words = sorted({m.group(0) for m in re.finditer(RED_FLAG_WORDS, (transcript or "").lower())})
    return {
        "vitals": {f: None for f in VITAL_FIELDS}, "unverified_vitals": {}, "medications": [],
        "observations": [], "concerns": [], "red_flags": [f"keyword:{w}" for w in words],
        "needs_coordinator_review": True, "review_reasons": [reason],
        "family_summary": None, "draft_family_summary": None, "transcript": transcript, "model": None,
    }
