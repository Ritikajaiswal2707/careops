"""
Rebuild the metered-LLM results table from saved run files, with and without the
Confirm guardrail. Offline: no API calls, so anyone can reproduce the table.

    python model/summarize_llm_evals.py
writes data/evaluation/llm_results_summary.json and prints a markdown table.
"""
import glob
import json
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from confirm_guardrail import check  # noqa: E402

EVAL_DIR = os.path.join(BASE_DIR, "..", "data", "evaluation")
SUITE_ORDER = {"heldout": 0, "holdout": 1, "holdout2": 2}


def _stats(predictions, preds):
    n = len(predictions)
    return {
        "intent_accuracy": round(sum(p["true_intent"] == q for p, q in zip(predictions, preds)) / n, 3),
        "false_confirmations": sum(q == "Confirm" and p["true_intent"] != "Confirm" for p, q in zip(predictions, preds)),
        "false_cancellations": sum(q == "Cancel" and p["true_intent"] != "Cancel" for p, q in zip(predictions, preds)),
    }


def summarize(paths):
    rows = []
    for path in paths:
        with open(path, encoding="utf-8") as f:
            run = json.load(f)
        if "predictions" not in run or "model" not in run:
            continue
        preds = run["predictions"]
        raw = [p["pred_intent"] for p in preds]
        guarded = [check(p["message"], p["pred_intent"]) for p in preds]
        after = [g for g, _ in guarded]
        rows.append({
            "file": os.path.basename(path),
            "model": run["model"],
            # The first run predates prompt versioning; its prompt is identical to v1.
            "prompt": "v1" if run.get("prompt_version", "v1").startswith("v1") else run["prompt_version"],
            "suite": run.get("suite", "heldout"),
            "n": len(preds),
            "p50_latency_ms": run["metrics"].get("p50_latency_ms"),
            "raw": _stats(preds, raw),
            "with_guardrail": {**_stats(preds, after),
                               "sent_to_human_by_guardrail": sum(1 for _, r in guarded if r),
                               "true_confirms_sent_to_human": sum(1 for p, (_, r) in zip(preds, guarded)
                                                                  if r and p["true_intent"] == "Confirm")},
        })
    rows.sort(key=lambda r: (SUITE_ORDER.get(r["suite"], 9), r["model"], r["prompt"]))
    return rows


def markdown(rows):
    out = ["| Suite | Model | Prompt | n | Accuracy | False confirms | + guardrail: accuracy | False confirms | Extra human reviews |",
           "|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        a, g = r["raw"], r["with_guardrail"]
        out.append(f"| {r['suite']} | {r['model'].split('/')[-1]} | {r['prompt']} | {r['n']} | "
                   f"{a['intent_accuracy']:.1%} | {a['false_confirmations']} | "
                   f"{g['intent_accuracy']:.1%} | {g['false_confirmations']} | {g['true_confirms_sent_to_human']} |")
    return "\n".join(out)


if __name__ == "__main__":
    rows = summarize(sorted(glob.glob(os.path.join(EVAL_DIR, "*_eval.json"))))
    with open(os.path.join(EVAL_DIR, "llm_results_summary.json"), "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2)
    print(markdown(rows))
