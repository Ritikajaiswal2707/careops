"""
Metered LLM evaluation on the 103-message held-out set.

Providers (all usable for free without a credit card at the time of writing;
check each provider's current limits):
  --provider gemini   GEMINI_API_KEY + GEMINI_MODEL
  --provider openai   any OpenAI-compatible endpoint, e.g. Groq or OpenRouter:
                      LLM_PROVIDER=groq|openrouter (or LLM_BASE_URL), LLM_API_KEY, LLM_MODEL

Why this exists
---------------
The headline LLM number elsewhere in this repo comes from blind predictions
written without a metered API call (see my_llm_predictions.py), so it has no
real cost or latency attached. This script closes that gap with a genuine,
reproducible API run that anyone can repeat on a free tier.

What it records (for every run)
-------------------------------
- model name, run timestamp (UTC), prompt version
- the same accuracy metrics as llm_vs_baseline_eval._score(): intent accuracy,
  macro F1, temporal / reason / cancel_current accuracy, abstention, JSON validity
- per-call latency (mean, p50, p95) measured around the HTTP request
- input / output token counts reported by the API (usageMetadata)
- cost: Rs.0 actually spent on the free tier. A paid-tier estimate is only
  produced if you pass real per-million-token prices via env vars
  (LLM_INPUT_USD_PER_M, LLM_OUTPUT_USD_PER_M, USD_INR); otherwise it is
  reported as null. Nothing is estimated from memory.
- every prediction and every misclassification, for error analysis

Usage
-----
    # Groq example (keys never go in the repo)
    export LLM_PROVIDER=groq LLM_API_KEY=... LLM_MODEL=<model id from the console>
    python model/metered_llm_eval.py --provider openai --limit 5   # smoke test
    python model/metered_llm_eval.py --provider openai             # full run

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

import openai_compat_llm  # noqa: E402
from llm_prompt import PROMPTS, strip_json_fence as _strip_fence  # noqa: E402

HOLDOUT_PATHS = {
    "holdout": os.path.join(BASE_DIR, "..", "data", "evaluation", "agent_holdout_v1.json"),
    # Fresh set frozen before prompt v3 was run; holdout v1 informed v2/v3 design.
    "holdout2": os.path.join(BASE_DIR, "..", "data", "evaluation", "intent_holdout_v2.json"),
}
INTENT_LABELS = ["Confirm", "Reschedule", "Cancel", "Unclear", "No Response"]
DEFAULT_OUTPUT_DIR = os.path.join(BASE_DIR, "..", "data", "evaluation")


def _endpoint(model):
    return f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def call_gemini(message, api_key, model, timeout=30, max_retries=5, post=requests.post, system=PROMPTS["v1"]):
    """One extraction call. Returns (parsed_or_None, json_valid, latency_s, in_tok, out_tok, error)."""
    payload = {
        "system_instruction": {"parts": [{"text": system}]},
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
            # Network blips (SSL resets, timeouts) are infrastructure, not model,
            # failures: retry them instead of scoring them as a wrong answer.
            if attempt < max_retries:
                time.sleep(backoff)
                backoff = min(backoff * 2, 60)
                continue
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


def call_openai_compat(message, api_key, model, base_url, timeout=30, max_retries=5, post=requests.post,
                       system=PROMPTS["v1"]):
    """Same return shape as call_gemini, for Groq / OpenRouter / any OpenAI-compatible endpoint."""
    backoff = 5.0
    for attempt in range(max_retries + 1):
        t0 = time.perf_counter()
        try:
            resp = openai_compat_llm.chat_extract(message, base_url, api_key, model, timeout=timeout, post=post,
                                                 system=system)
        except requests.RequestException as exc:
            # Network blips (SSL resets, timeouts) are infrastructure, not model,
            # failures: retry them instead of scoring them as a wrong answer.
            if attempt < max_retries:
                time.sleep(backoff)
                backoff = min(backoff * 2, 60)
                continue
            return None, False, time.perf_counter() - t0, None, None, type(exc).__name__
        latency = time.perf_counter() - t0
        if resp.status_code in (429, 503) and attempt < max_retries:
            time.sleep(backoff)
            backoff = min(backoff * 2, 60)
            continue
        if resp.status_code != 200:
            return None, False, latency, None, None, f"HTTP {resp.status_code}"
        parsed, in_tok, out_tok = openai_compat_llm.parse_response(resp.json())
        if parsed is None:
            return None, False, latency, in_tok, out_tok, "invalid_json"
        return parsed, True, latency, in_tok, out_tok, None
    return None, False, 0.0, None, None, "retries_exhausted"


def _pct(values, q):
    if not values:
        return None
    values = sorted(values)
    idx = min(len(values) - 1, max(0, round(q * (len(values) - 1))))
    return values[idx]


def load_suite(suite):
    """heldout: the 103-message extraction set (full gold structure).
    holdout: frozen 30-case end-to-end holdout (intent only); its errors informed prompt v3.
    holdout2: fresh 39-case intent holdout frozen before prompt v3 was run -- the clean test."""
    if suite == "heldout":
        return HELD_OUT_SET
    with open(HOLDOUT_PATHS[suite], encoding="utf-8") as f:
        return [{"message": c["message"], "intent": c["expected_intent"], "id": c["id"]}
                for c in json.load(f)["cases"]]


def safety_counts(predictions):
    """The two errors that matter most operationally."""
    return {
        "false_confirmations": sum(1 for p in predictions
                                   if p["pred_intent"] == "Confirm" and p["true_intent"] != "Confirm"),
        "false_cancellations": sum(1 for p in predictions
                                   if p["pred_intent"] == "Cancel" and p["true_intent"] != "Cancel"),
        "real_message_marked_no_response": sum(1 for p in predictions
                                               if p["pred_intent"] == "No Response"
                                               and (p["message"] or "").strip()),
    }


def _intent_only_score(predictions):
    from llm_vs_baseline_eval import _per_class_f1
    pairs = [(p["true_intent"], p["pred_intent"]) for p in predictions]
    labels = sorted({t for t, _ in pairs} | {q for _, q in pairs})
    by_class, macro = _per_class_f1(pairs, labels)
    n = len(pairs)
    jv = [p["json_valid"] for p in predictions]
    return {
        "n": n,
        "intent_accuracy": round(sum(t == q for t, q in pairs) / n, 3),
        "intent_macro_f1": macro,
        "intent_f1_by_class": by_class,
        "temporal_extraction_accuracy": None,
        "reason_extraction_accuracy": None,
        "cancel_current_accuracy": None,
        "abstention_rate": round(sum(q == "Unclear" for _, q in pairs) / n, 3),
        "json_validity_rate": round(sum(jv) / len(jv), 3),
    }


def run(api_key, model, limit=None, delay=4.0, post=requests.post, sleep=time.sleep,
        provider="gemini", base_url=None, prompt="v1", suite="heldout"):
    system = PROMPTS[prompt]
    all_cases = load_suite(suite)
    cases = all_cases[:limit] if limit else all_cases
    predictions, latencies, errors = [], [], []
    in_total = out_total = 0
    token_counts_complete = True

    for i, case in enumerate(cases):
        if provider == "gemini":
            res = call_gemini(case["message"], api_key, model, post=post, system=system)
        else:
            res = call_openai_compat(case["message"], api_key, model, base_url, post=post, system=system)
        parsed, json_valid, latency, in_tok, out_tok, err = res
        latencies.append(latency)
        if err:
            errors.append({"case": i, "error": err})
        if in_tok is None or out_tok is None:
            token_counts_complete = False
        else:
            in_total += in_tok
            out_total += out_tok
        parsed = parsed or {}
        if suite != "heldout":
            predictions.append({
                "case": case.get("id", i),
                "message": case["message"],
                "true_intent": case["intent"],
                "pred_intent": parsed.get("intent", "PARSE_ERROR"),
                "json_valid": json_valid,
            })
            print(f"  [{i + 1}/{len(cases)}] {predictions[-1]['pred_intent']:<12} {latency * 1000:7.0f} ms"
                  + (f"  ({err})" if err else ""))
            if delay and i < len(cases) - 1:
                sleep(delay)
            continue
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

    metrics = _score(predictions) if suite == "heldout" else _intent_only_score(predictions)
    metrics.update(safety_counts(predictions))
    metrics["avg_latency_ms"] = round(statistics.mean(latencies) * 1000, 1) if latencies else None
    metrics["p50_latency_ms"] = round(_pct(latencies, 0.5) * 1000, 1) if latencies else None
    metrics["p95_latency_ms"] = round(_pct(latencies, 0.95) * 1000, 1) if latencies else None
    metrics["input_tokens_total"] = in_total if token_counts_complete else None
    metrics["output_tokens_total"] = out_total if token_counts_complete else None
    metrics["errors"] = len(errors)
    infra_cases = {e["case"] for e in errors if e["error"] != "invalid_json"}
    scored = [p for p in predictions if p["case"] not in infra_cases]
    metrics["infra_errors"] = len(infra_cases)
    metrics["intent_accuracy_excluding_infra_errors"] = (
        round(sum(p["true_intent"] == p["pred_intent"] for p in scored) / len(scored), 3) if scored else None)
    metrics["actual_spend_inr"] = 0.0  # free tier; no billing account attached
    metrics["paid_tier_cost_per_message_inr"] = _paid_estimate(in_total, out_total, len(cases), token_counts_complete)

    return {
        "provider": provider if provider == "gemini" else (os.environ.get("LLM_PROVIDER") or base_url),
        "model": model,
        "prompt_version": prompt,
        "suite": suite,
        "run_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "n_cases": len(cases),
        "full_set": limit is None or limit >= len(all_cases),
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
        in_price = float(os.environ["LLM_INPUT_USD_PER_M"])
        out_price = float(os.environ["LLM_OUTPUT_USD_PER_M"])
        usd_inr = float(os.environ["USD_INR"])
    except (KeyError, ValueError):
        return None
    if not complete or n == 0:
        return None
    usd = (in_total * in_price + out_total * out_price) / 1_000_000
    return round(usd * usd_inr / n, 5)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Metered LLM evaluation on the held-out set")
    ap.add_argument("--provider", choices=["gemini", "openai"], default="openai",
                    help="gemini, or openai for any OpenAI-compatible endpoint (Groq, OpenRouter)")
    ap.add_argument("--prompt", choices=sorted(PROMPTS), default="v1", help="prompt version")
    ap.add_argument("--suite", choices=["heldout", "holdout", "holdout2"], default="heldout",
                    help="heldout: 103 messages; holdout: frozen 30-case set; holdout2: fresh 39-case set (clean test)")
    ap.add_argument("--limit", type=int, default=None, help="only run the first N cases (smoke test)")
    ap.add_argument("--delay", type=float, default=4.0, help="seconds between calls (free-tier spacing)")
    ap.add_argument("--output", default=None)
    args = ap.parse_args(argv)

    base_url = None
    if args.provider == "gemini":
        api_key, model = os.environ.get("GEMINI_API_KEY"), os.environ.get("GEMINI_MODEL")
        missing = "GEMINI_API_KEY and GEMINI_MODEL"
    else:
        cfg = openai_compat_llm.config()
        base_url, api_key, model = cfg if cfg else (None, None, None)
        missing = "LLM_PROVIDER (groq/openrouter) or LLM_BASE_URL, plus LLM_API_KEY and LLM_MODEL"
    if not api_key or not model:
        print(f"Set {missing} and re-run.\n"
              "Nothing is simulated: without a key this script does not produce a result.")
        return 2

    label = args.provider if args.provider == "gemini" else (os.environ.get("LLM_PROVIDER") or "openai_compat")
    model_slug = model.replace("/", "_")
    output = args.output or os.path.join(
        DEFAULT_OUTPUT_DIR, f"{label}_{model_slug}_{args.suite}_{args.prompt}_eval.json")

    result = run(api_key, model, limit=args.limit, delay=args.delay, provider=args.provider, base_url=base_url,
                 prompt=args.prompt, suite=args.suite)
    m = result["metrics"]
    print(f"\n{model} | prompt {args.prompt} | suite {args.suite} | {result['n_cases']} messages:")
    print(f"  intent accuracy   {m['intent_accuracy']:.1%}  (macro F1 {m['intent_macro_f1']})")
    print(f"  temporal accuracy {m['temporal_extraction_accuracy']}")
    print(f"  reason accuracy   {m['reason_extraction_accuracy']}")
    print(f"  false confirms    {m['false_confirmations']}   false cancels {m['false_cancellations']}"
          f"   real msg -> No Response {m['real_message_marked_no_response']}")
    print(f"  cancel_current    {m['cancel_current_accuracy']}")
    print(f"  JSON validity     {m['json_validity_rate']}")
    print(f"  latency p50/p95   {m['p50_latency_ms']} / {m['p95_latency_ms']} ms")
    print(f"  tokens in/out     {m['input_tokens_total']} / {m['output_tokens_total']}")
    print(f"  errors            {m['errors']}  (infrastructure: {m['infra_errors']}; "
          f"accuracy excluding them {m['intent_accuracy_excluding_infra_errors']})")

    if not result["full_set"]:
        print("\nPartial run (--limit): not written, so a smoke test never overwrites the real result.")
        return 0
    with open(output, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False, default=str)
    print(f"\nwrote {os.path.relpath(output)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
