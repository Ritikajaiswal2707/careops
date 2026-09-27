#!/usr/bin/env bash
# One-command reproduction of the full CareOps pipeline, in the order each
# stage actually depends on the last. A fresh clone + this script is meant to
# be the entire setup story — no manual step-through of model/ required.
#
#   ./run.sh
#
# What it does, in order:
#   1. installs pinned deps (skip with --no-install if already set up)
#   2. disruption_model.py        -> trains + prints the leaky-vs-fixed risk model comparison
#   3. fairness_subgroup_analysis.py -> subgroup precision/recall/FPR/calibration, first-time vs returning
#   4. disruption_type_model.py   -> Stage 2 model: No-Show vs Cancelled, among actual disruptions
#   5. communication_intelligence.py -> writes model/communications_enriched.csv
#   6. llm_direct_eval.py         -> writes model/llm_vs_baseline_results.json
#                                     (rule-based side always runs; LLM side is
#                                     Claude's direct blind extraction by default --
#                                     see model/llm_direct_eval.py's docstring, or
#                                     use model/llm_vs_baseline_eval.py directly if
#                                     you have an ANTHROPIC_API_KEY and want the
#                                     real metered API path with cost/latency)
#   7. hybrid_extraction.py       -> writes model/hybrid_eval_results.json
#                                     (scores the rule-first hybrid architecture: rule-based
#                                     accepted when confident, LLM fallback only on
#                                     abstention, escalate-to-human when neither is confident)
#   8. capacity_recovery.py       -> prints the worked Recovery Score example
#   9. agent_state_machine.py     -> demos all four reschedule-lifecycle paths
#  10. economics_simulation.py    -> writes model/economics_summary.json
#  11. intervention_outcome_simulation.py -> writes model/intervention_outcomes.json
#                                     (per-case simulated outcome log; bottom-up vs. top-down economics)
#  12. generate_dashboard_data.py -> writes model/dashboard_data.json AND
#                                     rewrites dashboard/index.html's DATA in place
#                                     (uses hybrid_extraction.extract_intent_hybrid, not the
#                                     bare rule-based extractor, for the patient-signal path)
#
# Exit code is non-zero if any stage fails (set -e) so a broken pipeline
# can't silently produce a stale dashboard.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

if [[ "${1:-}" != "--no-install" ]]; then
  echo "== installing dependencies (pandas, numpy, scikit-learn) =="
  pip install -q -r requirements.txt
fi

cd model

run() {
  echo ""
  echo "== $1 =="
  python3 "$1"
}

run disruption_model.py
run fairness_subgroup_analysis.py
run disruption_type_model.py
run communication_intelligence.py
run llm_direct_eval.py
run hybrid_extraction.py
run capacity_recovery.py
run agent_state_machine.py
run economics_simulation.py
run intervention_outcome_simulation.py
run generate_dashboard_data.py

echo ""
echo "== done =="
echo "dashboard/index.html now reflects this run's output — open it directly in a browser."
