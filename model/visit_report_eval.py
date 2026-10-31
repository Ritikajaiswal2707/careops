"""
Metered evaluation of visit-report structuring, before and after the safety layer.

    $env:LLM_PROVIDER="groq"; $env:LLM_API_KEY="..."; $env:LLM_MODEL="openai/gpt-oss-120b"
    python model/visit_report_eval.py --limit 3     # smoke test, nothing written
    python model/visit_report_eval.py               # full run

Metrics (raw model output vs after apply_safety):
  vital_field_accuracy      exact match over every vital field of every note
  invented_vitals           a value where the note gave none (gold null) -- the key safety metric
  wrong_values_released     a released (verified) value that differs from gold
  review_recall             notes a coordinator should see first that were flagged (must be 100%)
  review_rate_on_routine    routine notes sent to review anyway (the cost of caution)
  family_summary_released   summaries released to families, and any containing a number not in the note
"""
import argparse
import datetime as dt
import json
import os
import re
import statistics
import sys
import time

import requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

import openai_compat_llm  # noqa: E402
from visit_report import VITAL_FIELDS, apply_safety, structure  # noqa: E402

SUITE = os.path.join(BASE_DIR, "..", "data", "evaluation", "visit_report_eval_v1.json")


def load_cases():
    with open(SUITE, encoding="utf-8") as f:
        return json.load(f)["cases"]


def _num(v):
    if isinstance(v, bool) or v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _vital_stats(cases, vitals_list):
    correct = invented = wrong = 0
    total = 0
    for case, vitals in zip(cases, vitals_list):
        for f in VITAL_FIELDS:
            total += 1
            gold, got = _num(case["gold_vitals"][f]), _num((vitals or {}).get(f))
            correct += gold == got
            invented += gold is None and got is not None
            wrong += gold is not None and got is not None and gold != got
    return {"vital_field_accuracy": round(correct / total, 3), "invented_vitals": invented,
            "wrong_values": wrong}


def score(cases, raw_reports, safe_reports):
    raw = _vital_stats(cases, [(r or {}).get("vitals") for r in raw_reports])
    safe = _vital_stats(cases, [s["vitals"] for s in safe_reports])
    need = [s for c, s in zip(cases, safe_reports) if c["gold_needs_review"]]
    routine = [s for c, s in zip(cases, safe_reports) if not c["gold_needs_review"]]
    released = [(c, s) for c, s in zip(cases, safe_reports) if s["family_summary"]]
    leaky = [c["id"] for c, s in released
             if {float(n) for n in re.findall(r"\d+(?:\.\d+)?", s["family_summary"])}
             - {float(n) for n in re.findall(r"\d+(?:\.\d+)?", c["transcript"])}]
    return {
        "n": len(cases),
        "json_valid": sum(r is not None for r in raw_reports),
        "raw": raw,
        "after_safety": {
            **{k: v for k, v in safe.items() if k != "wrong_values"},
            "wrong_values_released": safe["wrong_values"],
            "review_recall": round(sum(s["needs_coordinator_review"] for s in need) / len(need), 3) if need else None,
            "missed_reviews": [c["id"] for c, s in zip(cases, safe_reports)
                               if c["gold_needs_review"] and not s["needs_coordinator_review"]],
            "review_rate_on_routine": (round(sum(s["needs_coordinator_review"] for s in routine) / len(routine), 3)
                                       if routine else None),
            "family_summaries_released": len(released),
            "released_summaries_with_unstated_numbers": leaky,
        },
    }


def run(api_key, model, base_url, limit=None, delay=3.0, post=requests.post, sleep=time.sleep):
    cases = load_cases()
    cases = cases[:limit] if limit else cases
    raw_reports, safe_reports, latencies, errors = [], [], [], []
    for i, case in enumerate(cases):
        report, err = None, None
        for attempt in range(4):
            t0 = time.perf_counter()
            report, err, _ = structure(case["transcript"], base_url, api_key, model, post=post)
            latencies.append(time.perf_counter() - t0)
            if err not in ("HTTP 429", "HTTP 503") and not (err or "").endswith("Error"):
                break
            sleep(5 * (attempt + 1))
        if err:
            errors.append({"case": case["id"], "error": err})
        raw_reports.append(report)
        safe = apply_safety(case["transcript"], report) if report else apply_safety(case["transcript"], {"vitals": {}})
        if report is None:  # a failed report must still fail closed
            safe["needs_coordinator_review"], safe["family_summary"] = True, None
        safe_reports.append(safe)
        print(f"  [{i + 1}/{len(cases)}] {case['id']} review={safe['needs_coordinator_review']!s:<5} "
              f"unverified={sorted(safe['unverified_vitals'])}" + (f"  ({err})" if err else ""))
        if delay and i < len(cases) - 1:
            sleep(delay)
    metrics = score(cases, raw_reports, safe_reports)
    metrics["p50_latency_ms"] = round(statistics.median(latencies) * 1000, 1) if latencies else None
    metrics["errors"] = len(errors)
    return {
        "model": model, "suite": "visit_report_eval_v1",
        "run_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "n_cases": len(cases), "full_set": limit is None, "metrics": metrics, "errors": errors,
        "cases": [{"id": c["id"], "category": c["category"], "gold_vitals": c["gold_vitals"],
                   "gold_needs_review": c["gold_needs_review"], "raw": r, "safe": s}
                  for c, r, s in zip(cases, raw_reports, safe_reports)],
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="Visit report evaluation")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--delay", type=float, default=3.0)
    args = ap.parse_args(argv)
    cfg = openai_compat_llm.config()
    if cfg is None:
        print("Set LLM_PROVIDER (groq/openrouter) or LLM_BASE_URL, plus LLM_API_KEY and LLM_MODEL.\n"
              "Nothing is simulated: without a key this script does not produce a result.")
        return 2
    base_url, api_key, model = cfg
    result = run(api_key, model, base_url, limit=args.limit, delay=args.delay)
    m = result["metrics"]
    print(f"\n{model} on {result['n_cases']} visit notes:")
    print(f"  JSON valid              {m['json_valid']}/{m['n']}   errors {m['errors']}")
    print(f"  vital accuracy          raw {m['raw']['vital_field_accuracy']:.1%}   after safety "
          f"{m['after_safety']['vital_field_accuracy']:.1%}")
    print(f"  invented vitals         raw {m['raw']['invented_vitals']}   after safety "
          f"{m['after_safety']['invented_vitals']}")
    print(f"  wrong values            raw {m['raw']['wrong_values']}   released {m['after_safety']['wrong_values_released']}")
    a = m["after_safety"]
    print(f"  review recall           {a['review_recall']}   missed {a['missed_reviews']}")
    print(f"  routine sent to review  {a['review_rate_on_routine']}")
    print(f"  summaries released      {a['family_summaries_released']}   with unstated numbers "
          f"{a['released_summaries_with_unstated_numbers']}")
    if not result["full_set"]:
        print("\nPartial run (--limit): not written.")
        return 0
    out = os.path.join(BASE_DIR, "..", "data", "evaluation",
                       f"visit_report_{model.replace('/', '_')}_v1_eval.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"\nwrote {os.path.relpath(out)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
