#!/usr/bin/env python3
"""
One-command reproduction of the full CareOps pipeline, in dependency order,
runnable from anywhere (this file locates everything relative to its own
location, not the caller's working directory):

    python run.py            # from the repo root
    python /path/to/run.py   # from anywhere else

Every model/*.py script also resolves its own data/output paths from
__file__ rather than the working directory, so `python model/xyz.py` works
too, from any directory -- this script is a convenience wrapper around that,
not a workaround for scripts that only worked from inside model/.

Stages, in order:
  1. disruption_model.py         -> trains + prints the leaky-vs-fixed risk model comparison
  2. fairness_subgroup_analysis.py -> subgroup precision/recall/FPR/calibration, first-time vs returning patients
  3. disruption_type_model.py     -> Stage 2 model: No-Show vs Cancelled, among actual disruptions
  4. communication_intelligence.py -> writes model/communications_enriched.csv
  5. llm_direct_eval.py           -> writes model/llm_vs_baseline_results.json
                                     (rule-based side always runs; LLM side uses
                                     Claude's direct blind extraction by default --
                                     see model/llm_direct_eval.py's docstring for
                                     why, and llm_vs_baseline_eval.py if you have
                                     an ANTHROPIC_API_KEY and want the real metered
                                     API path with actual cost/latency instead)
  6. hybrid_extraction.py        -> writes model/hybrid_eval_results.json
                                     (scores the rule-first hybrid architecture itself:
                                     rule-based accepted unconditionally when confident,
                                     LLM fallback only on abstention, escalate-to-human
                                     when neither is confident -- see its docstring)
  7. capacity_recovery.py        -> prints the worked Recovery Score example
  8. agent_state_machine.py      -> demos all four reschedule-lifecycle paths
  9. economics_simulation.py     -> writes model/economics_summary.json
 10. intervention_outcome_simulation.py -> writes model/intervention_outcomes.json
                                     (per-case simulated outcome log; bottom-up vs. top-down economics)
 11. generate_dashboard_data.py  -> writes model/dashboard_data.json AND
                                     rewrites dashboard/index.html's DATA in place
                                     (uses hybrid_extraction.extract_intent_hybrid, not the
                                     bare rule-based extractor, for the patient-signal path)

Pass --no-install to skip the pip step (use whatever environment is already active).
"""
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
MODEL_DIR = BASE_DIR / "model"

STAGES = [
    "disruption_model.py",
    "fairness_subgroup_analysis.py",
    "disruption_type_model.py",
    "communication_intelligence.py",
    "llm_direct_eval.py",
    "hybrid_extraction.py",
    "capacity_recovery.py",
    "agent_state_machine.py",
    "economics_simulation.py",
    "intervention_outcome_simulation.py",
    "generate_dashboard_data.py",
]


def run(cmd, **kwargs):
    print(f"\n$ {' '.join(cmd)}")
    result = subprocess.run(cmd, **kwargs)
    if result.returncode != 0:
        sys.exit(result.returncode)


def main():
    no_install = "--no-install" in sys.argv

    if not no_install:
        print("== installing dependencies (pandas, numpy, scikit-learn) ==")
        run([sys.executable, "-m", "pip", "install", "-q", "-r", str(BASE_DIR / "requirements.txt")])

    for stage in STAGES:
        print(f"\n== {stage} ==")
        # cwd=MODEL_DIR only so a script's OWN relative reads (if any remain)
        # still work; every script also resolves paths via __file__, so this
        # is belt-and-suspenders, not the thing making it work.
        run([sys.executable, stage], cwd=str(MODEL_DIR))

    print("\n== done ==")
    print("dashboard/index.html now reflects this run's output — open it directly in a browser.")


if __name__ == "__main__":
    main()
