"""
Bake recorded visit-report examples into the dashboard, from a saved real model run.

The public demo has external LLM calls switched off, so its "Visit reports" tab
shows recorded outcomes instead of live ones. They come straight from the saved
run file, with the CURRENT safety layer re-applied offline, and are labelled as
recorded on the page. Nothing is typed in by hand.

    python model/generate_visit_report_examples.py
"""
import json
import os
import re
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from visit_report import SAFETY_VERSION, VITAL_FIELDS, apply_safety  # noqa: E402

RUN = os.path.join(BASE_DIR, "..", "data", "evaluation", "visit_report_openai_gpt-oss-120b_v1_eval.json")
SUITE = os.path.join(BASE_DIR, "..", "data", "evaluation", "visit_report_eval_v1.json")
DASHBOARD = os.path.join(BASE_DIR, "..", "dashboard", "index.html")

# One example per behaviour worth showing, with the point it makes.
EXAMPLES = [
    ("VR01", "Routine visit: every vital verified, family update sent."),
    ("VR07", "No vitals mentioned: the model invented none."),
    ("VR14", "Spoken Hindi numbers: the model misread 'sattanve' (97) as 100; grounding held it for review."),
    ("VR20", "Two readings: the model kept the normal 88; the reading scan caught the earlier low 62."),
    ("VR22", "A fall mentioned: escalated on the keyword, even though the vitals are normal."),
]

LABELS = {"bp_systolic": "BP sys", "bp_diastolic": "BP dia", "blood_sugar_mg_dl": "Sugar",
          "spo2_pct": "SpO2", "pulse_bpm": "Pulse", "temperature_f": "Temp"}


def build():
    with open(RUN, encoding="utf-8") as f:
        run = json.load(f)
    with open(SUITE, encoding="utf-8") as f:
        suite = {c["id"]: c for c in json.load(f)["cases"]}
    by_id = {c["id"]: c for c in run["cases"]}
    out = []
    for case_id, point in EXAMPLES:
        raw = by_id[case_id]["raw"] or {"vitals": {}}
        transcript = suite[case_id]["transcript"]
        safe = apply_safety(transcript, raw)
        out.append({
            "id": case_id,
            "point": point,
            "transcript": transcript,
            "model_vitals": {LABELS[f]: raw["vitals"].get(f) for f in VITAL_FIELDS if raw["vitals"].get(f) is not None},
            "verified_vitals": {LABELS[f]: v for f, v in safe["vitals"].items() if v is not None},
            "unverified": {LABELS[f]: v for f, v in safe["unverified_vitals"].items()},
            "needs_review": safe["needs_coordinator_review"],
            "reasons": safe["review_reasons"],
            "family_summary": safe["family_summary"],
            "draft_family_summary": safe["draft_family_summary"],
        })
    return {"model": run["model"], "recorded_at": run["run_at_utc"], "safety_version": SAFETY_VERSION,
            "examples": out}


def write(data, path=DASHBOARD):
    with open(path, encoding="utf-8") as f:
        html = f.read()
    line = "const VR_EXAMPLES = " + json.dumps(data, ensure_ascii=False) + ";"
    new, n = re.subn(r"^const VR_EXAMPLES = .*;$", lambda m: line, html, count=1, flags=re.M)
    if n != 1:
        raise SystemExit("VR_EXAMPLES marker not found in dashboard/index.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(new)


if __name__ == "__main__":
    data = build()
    write(data)
    print(f"wrote {len(data['examples'])} recorded examples ({data['model']}, safety {data['safety_version']})")
