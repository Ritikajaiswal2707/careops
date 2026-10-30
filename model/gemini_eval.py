"""
Metered LLM evaluation on the 103-message held-out set, using the Gemini API.

Why this exists
---------------
The headline LLM number elsewhere in this repo comes from blind predictions
written without a metered API call (see my_llm_predictions.py), so it has no
real cost or latency attached. This script closes that gap with a genuine,
reproducible API run that anyone can repeat on Gemini's free tier.

What it records (for every run)
-------------------------------
- model name, run timestamp (UTC), prompt version
- the same accuracy metrics as llm_vs_baseline_eval._score(): intent accuracy,
  macro F1, temporal / reason / cancel_current accuracy, abstention, JSON validity
- per-call latency (mean, p50, p95) measured around the HTTP request
- input / output token counts reported by the API (usageMetadata)
- cost: Rs.0 actually spent on the free tier. A paid-tier estimate is only
  produced if you pass real per-million-token prices via env vars
  (GEMINI_INPUT_USD_PER_M, GEMINI_OUTPUT_USD_PER_M, USD_INR); otherwise it is
  reported as null. Nothing is estimated from memory.
- every prediction and every misclassification, for error analysis

Usage
-----
    export GEMINI_API_KEY=...            # never commit this
    export GEMINI_MODEL=<model id>       # optional; recorded in the output
    python model/gemini_eval.py --limit 5        # smoke test
    python model/gemini_eval.py                  # full 103-message run

Free-tier limits are per-minute; the script spaces calls (--delay) and backs
off on HTTP 429 instead of failing the run.
"""
import argparse
import datetime as dt
import json
import os
import statistics
import sys
import time

import requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from llm_vs_baseline_eval import HELD_OUT_SET, _score  # noqa: E402

PROMPT_VERSION = "v1-parity-with-anthropic-eval"
DEFAULT_OUTPUT = os.path.join(BASE_DIR, "..", "data", "evaluation", "gemini_llm_eval.json")

# Same extraction contract as llm_vs_baseline_eval.run_llm_eval(), including
# the cancel_current guidance, so results are directly comparable.
SYSTEM_PROMPT = (
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


def _endpoint(model):
    return f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def _strip_fence(text):
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`").strip()
        if text.lower().startswith("json"):
            text = text[4:]
    return text.strip()


def call_gemini(message, api_key, model, timeout=30, max_retries=5, post=requests.post):
    """One extraction call. Returns (parsed_or_None, json_valid, latency_s, in_tok, out_tok, error)."""
    payload = {
        "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{"role": "user", "parts": [{"text": message or "(empty message)"}]}],
        # Generous output budget: some models spend tokens on internal reasoning
        # before the JSON, and a truncated answer would be scored as invalid JSON.
        "generationConfig": {"temperature": 0, "maxOutputTokens": 1024},
    }
    backoff = 5.0
    for attempt in range(max_retries + 1):
        t0 = time.perf_counter()
        try:
            resp = post(_endpoint(model), headers={"x-goog-api-key": api_key}, json=payload, timeout=timeout)
        except requests.RequestException as exc:
            return None, False, time.perf_counter() - t0, None, None, type(exc).__name__
        latency = time.perf_counter() - t0
        if resp.status_code in (429, 503) and attempt < max_retries:
            time.sleep(backoff)
            backoff = min(backoff * 2, 60)
            continue
        if resp.status_code != 200:
            return None, False, latency, None, None, f"HTTP {resp.status_code}"
        body = resp.json()
        usage = body.get("usageMetadata", {})
        in_tok = usage.get("promptTokenCount")
        out_tok = usage.get("candidatesTokenCount")
        try:
            text = body["candidates"][0]["content"]["parts"][0]["text"]
            parsed = json.loads(_strip_fence(text))
            if not isinstance(parsed, dict):
                raise ValueError("not an object")
            return parsed, True, latency, in_tok, out_tok, None
        except (KeyError, IndexError, TypeError, ValueError):
            return None, False, latency, in_tok, out_tok, "invalid_json"
    return None, False, 0.0, None, None, "retries_exhausted"


def _pct(values, q):
    if not values:
        return None
    values = sorted(values)
    idx = min(len(values) - 1, max(0, round(q * (len(values) - 1))))
    return values[idx]


def run(api_key, model, limit=None, delay=4.0, post=requests.post, sleep=time.sleep):
    cases = HELD_OUT_SET[:limit] if limit else HELD_OUT_SET
    predictions, latencies, errors = [], [], []
    in_total = out_total = 0
    token_counts_complete = True

    for i, case in enumerate(cases):
        parsed, json_valid, latency, in_tok, out_tok, err = call_gemini(case["message"], api_key, model, post=post)
        latencies.append(latency)
        if err:
            errors.append({"case": i, "error": err})
        if in_tok is None or out_tok is None:
            token_counts_complete = False
        else:
            in_total += in_tok
            out_total += out_tok
        parsed = parsed or {}
        predictions.append({
            "case": i,
            "message": case["message"],
            "true_intent": case["intent"],
            "pred_intent": parsed.get("intent", "PARSE_ERROR"),
            "true_cancel_current": case["cancel_current"],
            "pred_cancel_current": parsed.get("cancel_current") if json_valid else None,
            "true_temporal": (case["preferred_day"], case["next_week"], case["relative_day"], case["offset_days"]),
            "pred_temporal": (parsed.get("preferred_day"), parsed.get("next_week", False),
                              parsed.get("relative_day"), parsed.get("offset_days")),
            "true_reason": case["reason"],
            "pred_reason": parsed.get("reason"),
            "json_valid": json_valid,
        })
        print(f"  [{i + 1}/{len(cases)}] {predictions[-1]['pred_intent']:<12} {latency * 1000:7.0f} ms"
              + (f"  ({err})" if err else ""))
        if delay and i < len(cases) - 1:
            sleep(delay)

    metrics = _score(predictions)
    metrics["avg_latency_ms"] = round(statistics.mean(latencies) * 1000, 1) if latencies else None
    metrics["p50_latency_ms"] = round(_pct(latencies, 0.5) * 1000, 1) if latencies else None
    metrics["p95_latency_ms"] = round(_pct(latencies, 0.95) * 1000, 1) if latencies else None
    metrics["input_tokens_total"] = in_total if token_counts_complete else None
    metrics["output_tokens_total"] = out_total if token_counts_complete else None
    metrics["errors"] = len(errors)
    metrics["actual_spend_inr"] = 0.0  # free tier; no billing account attached
    metrics["paid_tier_cost_per_message_inr"] = _paid_estimate(in_total, out_total, len(cases), token_counts_complete)

    return {
        "provider": "gemini",
        "model": model,
        "prompt_version": PROMPT_VERSION,
        "run_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "n_cases": len(cases),
        "full_set": limit is None or limit >= len(HELD_OUT_SET),
        "metrics": metrics,
        "errors": errors,
        "misclassified": [p for p in predictions if p["true_intent"] != p["pred_intent"]],
        "predictions": predictions,
        "notes": (
            "Synthetic, author-labelled held-out set. Latency includes network time from the "
            "machine that ran this script. Paid-tier cost is only computed from prices supplied "
            "via environment variables at run time."
        ),
    }


def _paid_estimate(in_total, out_total, n, complete):
    try:
        in_price = float(os.environ["GEMINI_INPUT_USD_PER_M"])
        out_price = float(os.environ["GEMINI_OUTPUT_USD_PER_M"])
        usd_inr = float(os.environ["USD_INR"])
    except (KeyError, ValueError):
        return None
    if not complete or n == 0:
        return None
    usd = (in_total * in_price + out_total * out_price) / 1_000_000
    return round(usd * usd_inr / n, 5)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--limit", type=int, default=None, help="only run the first N cases (smoke test)")
    ap.add_argument("--delay", type=float, default=4.0, help="seconds between calls (free-tier spacing)")
    ap.add_argument("--output", default=DEFAULT_OUTPUT)
    args = ap.parse_args(argv)

    api_key = os.environ.get("GEMINI_API_KEY")
    model = os.environ.get("GEMINI_MODEL")
    if not api_key or not model:
        print("Set GEMINI_API_KEY and GEMINI_MODEL (a model id from Google AI Studio) and re-run.\n"
              "Nothing is simulated: without a key this script does not produce a result.")
        return 2

    result = run(api_key, model, limit=args.limit, delay=args.delay)
    m = result["metrics"]
    print(f"\n{model} on {result['n_cases']} held-out messages:")
    print(f"  intent accuracy   {m['intent_accuracy']:.1%}  (macro F1 {m['intent_macro_f1']})")
    print(f"  temporal accuracy {m['temporal_extraction_accuracy']:.1%}")
    print(f"  reason accuracy   {m['reason_extraction_accuracy']:.1%}")
    print(f"  cancel_current    {m['cancel_current_accuracy']}")
    print(f"  JSON validity     {m['json_validity_rate']}")
    print(f"  latency p50/p95   {m['p50_latency_ms']} / {m['p95_latency_ms']} ms")
    print(f"  tokens in/out     {m['input_tokens_total']} / {m['output_tokens_total']}")
    print(f"  errors            {m['errors']}")

    if not result["full_set"]:
        print("\nPartial run (--limit): not written, so a smoke test never overwrites the real result.")
        return 0
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False, default=str)
    print(f"\nwrote {os.path.relpath(args.output)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
