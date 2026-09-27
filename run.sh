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
#   3. communication_intelligence.py -> writes model/communications_enriched.csv
#   4. llm_vs_baseline_eval.py    -> writes model/llm_vs_baseline_results.json
#                                     (LLM half runs only if ANTHROPIC_API_KEY is set)
#   5. capacity_recovery.py       -> prints the worked Recovery Score example
#   6. agent_state_machine.py     -> demos all four reschedule-lifecycle paths
#   7. economics_simulation.py    -> writes model/economics_summary.json
#   8. generate_dashboard_data.py -> writes model/dashboard_data.json AND
#                                     rewrites dashboard/index.html's DATA in place
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
run communication_intelligence.py
run llm_vs_baseline_eval.py
run capacity_recovery.py
run agent_state_machine.py
run economics_simulation.py
run generate_dashboard_data.py

echo ""
echo "== done =="
echo "dashboard/index.html now reflects this run's output — open it directly in a browser."
