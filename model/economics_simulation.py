"""
Module 7: Economics — modeled impact of using the risk model to prioritize
coordinator outreach, evaluated on the August test period (unseen by the
model, from the time-based split in disruption_model.py).

IMPORTANT: everything below the ASSUMPTIONS block is a simulation, not a
measured result. There is no real intervention in this data — nobody was
actually called or messaged and their outcome logged. The numbers show what
the model's own precision/recall would imply IF the assumed intervention
success rate holds. Two of the assumed inputs (success rate, revenue per
visit) are illustrative placeholders, not sourced figures, and are labeled
as such everywhere they're used.
"""
import json
from disruption_model import df, X_test, y_test, model, features

# ---- ASSUMPTIONS (edit these to match real operating numbers when known) ----
TOP_K_PCT = 0.20                    # coordinator bandwidth: top 20% by risk get outreach
INTERVENTION_SUCCESS_RATE = 0.35    # ASSUMED: fraction of true disruptions converted to completed by outreach
COORDINATOR_MIN_PER_CONTACT = 8     # ASSUMED: minutes of coordinator time per outreach
REVENUE_PER_COMPLETED_VISIT = 800   # ASSUMED, placeholder currency units — not a sourced figure

proba = model.predict_proba(X_test[features])[:, 1]
n = len(y_test)
n_flag = int(round(n * TOP_K_PCT))

order = proba.argsort()[::-1]
flagged_idx = order[:n_flag]
y_arr = y_test.values

true_positives = int(y_arr[flagged_idx].sum())
total_disruptions = int(y_arr.sum())
baseline_completed = n - total_disruptions

recovered_visits = round(true_positives * INTERVENTION_SUCCESS_RATE)
after_completed = baseline_completed + recovered_visits
after_disrupted = total_disruptions - recovered_visits

coordinator_hours = round(n_flag * COORDINATOR_MIN_PER_CONTACT / 60, 1)
contribution_recovered = recovered_visits * REVENUE_PER_COMPLETED_VISIT

result = {
    "evaluation_period": "August (test split, unseen by model)",
    "total_appointments": n,
    "assumptions": {
        "top_k_pct_flagged": TOP_K_PCT,
        "intervention_success_rate": INTERVENTION_SUCCESS_RATE,
        "coordinator_min_per_contact": COORDINATOR_MIN_PER_CONTACT,
        "revenue_per_completed_visit": REVENUE_PER_COMPLETED_VISIT,
        "note": "success_rate and revenue_per_completed_visit are illustrative placeholders, not measured or sourced",
    },
    "before": {
        "completed": baseline_completed,
        "disrupted": total_disruptions,
        "completion_rate_pct": round(baseline_completed / n * 100, 1),
    },
    "modeled_after_intervention": {
        "appointments_flagged_for_outreach": n_flag,
        "true_disruptions_among_flagged": true_positives,
        "recovered_visits": recovered_visits,
        "completed": after_completed,
        "disrupted": after_disrupted,
        "completion_rate_pct": round(after_completed / n * 100, 1),
    },
    "cost_and_return_modeled": {
        "coordinator_hours_spent": coordinator_hours,
        "estimated_contribution_recovered": contribution_recovered,
    },
}

with open("economics_summary.json", "w") as f:
    json.dump(result, f, indent=2)

print(json.dumps(result, indent=2))
