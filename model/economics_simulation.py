"""
Module 7: Economics — modeled impact of using the risk model to prioritize
coordinator outreach, evaluated on the August test period (unseen by the
model, from the time-based split in disruption_model.py).

IMPORTANT: everything below the ASSUMPTIONS block is a simulation, not a
measured result. There is no real intervention in this data — nobody was
actually called or messaged and their outcome logged. The numbers show what
the model's own precision/recall would imply IF the assumed intervention
success rate holds. Three of the assumed inputs (success rate, revenue per
visit, coordinator hourly cost) are illustrative placeholders, not sourced
figures, and are labeled as such everywhere they're used.

v2 addition (this pass): a sensitivity sweep. The single base-case number
this script used to print invites exactly the wrong reading -- "the model
is worth ~59,200" -- when two of its four inputs are placeholders, not
measurements. Below, the base case is now one point on two 1-D sweeps
(intervention success rate, and coordinator bandwidth/top_k_pct), plus a
breakeven calculation: the minimum real-world success rate at which the
modeled coordinator-hours cost is actually paid back. That breakeven number
is the one honest headline here -- it's a threshold the (unvalidated)
EXPERIMENT_DESIGN.md RCT could go test, not a claimed return.
"""
import json
import os
from disruption_model import df, X_test, y_test, model, features

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ---- ASSUMPTIONS (edit these to match real operating numbers when known) ----
TOP_K_PCT = 0.20                    # coordinator bandwidth: top 20% by risk get outreach
INTERVENTION_SUCCESS_RATE = 0.35    # ASSUMED: fraction of true disruptions converted to completed by outreach
COORDINATOR_MIN_PER_CONTACT = 8     # ASSUMED: minutes of coordinator time per outreach
REVENUE_PER_COMPLETED_VISIT = 800   # ASSUMED, placeholder currency units — not a sourced figure
COORDINATOR_HOURLY_COST = 300       # ASSUMED, placeholder currency units — fully loaded cost per coordinator-hour

proba = model.predict_proba(X_test[features])[:, 1]
n = len(y_test)
y_arr = y_test.values
order = proba.argsort()[::-1]
total_disruptions = int(y_arr.sum())
baseline_completed = n - total_disruptions


def simulate(top_k_pct: float, success_rate: float) -> dict:
    """One point in the sensitivity space: what the modeled economics look
    like at a given coordinator bandwidth and a given (unmeasured)
    intervention success rate. Pure function of the two assumptions the
    reviewer flagged as placeholders -- everything else (true_positives,
    coordinator time per contact, revenue per visit, cost per hour) comes
    from the actual test-split predictions or the ASSUMPTIONS block above.
    """
    n_flag = int(round(n * top_k_pct))
    flagged_idx = order[:n_flag]
    true_positives = int(y_arr[flagged_idx].sum())

    recovered_visits = round(true_positives * success_rate)
    after_completed = baseline_completed + recovered_visits
    coordinator_hours = round(n_flag * COORDINATOR_MIN_PER_CONTACT / 60, 1)
    contribution_recovered = recovered_visits * REVENUE_PER_COMPLETED_VISIT
    coordinator_cost = round(coordinator_hours * COORDINATOR_HOURLY_COST, 0)
    net_value = round(contribution_recovered - coordinator_cost, 0)

    return {
        "top_k_pct_flagged": top_k_pct,
        "intervention_success_rate": success_rate,
        "appointments_flagged_for_outreach": n_flag,
        "true_disruptions_among_flagged": true_positives,
        "recovered_visits": recovered_visits,
        "completed": after_completed,
        "disrupted": total_disruptions - recovered_visits,
        "completion_rate_pct": round(after_completed / n * 100, 1),
        "coordinator_hours_spent": coordinator_hours,
        "estimated_contribution_recovered": contribution_recovered,
        "coordinator_cost_modeled": coordinator_cost,
        "net_value_modeled": net_value,
    }


base = simulate(TOP_K_PCT, INTERVENTION_SUCCESS_RATE)

# Breakeven success rate at the base top_k: the real-world intervention
# success rate at which contribution_recovered exactly covers
# coordinator_cost, holding top_k_pct (and therefore true_positives and
# coordinator_hours) fixed. Both sides of the equation are linear in
# success_rate, so this is a closed-form divide, not a search.
_n_flag_base = int(round(n * TOP_K_PCT))
_tp_base = int(y_arr[order[:_n_flag_base]].sum())
_coordinator_cost_base = round(_n_flag_base * COORDINATOR_MIN_PER_CONTACT / 60, 1) * COORDINATOR_HOURLY_COST
breakeven_success_rate = (
    round(_coordinator_cost_base / (_tp_base * REVENUE_PER_COMPLETED_VISIT), 3)
    if _tp_base > 0 else None
)

success_rate_sweep = [simulate(TOP_K_PCT, sr) for sr in [0.15, 0.25, 0.35, 0.45, 0.55]]
top_k_sweep = [simulate(tk, INTERVENTION_SUCCESS_RATE) for tk in [0.10, 0.15, 0.20, 0.25, 0.30]]

result = {
    "evaluation_period": "August (test split, unseen by model)",
    "total_appointments": n,
    "assumptions": {
        "top_k_pct_flagged": TOP_K_PCT,
        "intervention_success_rate": INTERVENTION_SUCCESS_RATE,
        "coordinator_min_per_contact": COORDINATOR_MIN_PER_CONTACT,
        "revenue_per_completed_visit": REVENUE_PER_COMPLETED_VISIT,
        "coordinator_hourly_cost": COORDINATOR_HOURLY_COST,
        "note": "success_rate, revenue_per_completed_visit, and coordinator_hourly_cost are "
                "illustrative placeholders, not measured or sourced",
    },
    "before": {
        "completed": baseline_completed,
        "disrupted": total_disruptions,
        "completion_rate_pct": round(baseline_completed / n * 100, 1),
    },
    "modeled_after_intervention": base,
    "breakeven_intervention_success_rate_at_base_top_k": breakeven_success_rate,
    "sensitivity": {
        "note": "Two 1-D sweeps, each holding the other assumption at its base-case value above. "
                "Neither sweep is a claim about which point is real -- the point is that "
                "net_value_modeled swings from negative to strongly positive within a plausible "
                "range of the one number nobody has actually measured yet (intervention_success_rate).",
        "by_intervention_success_rate": success_rate_sweep,
        "by_coordinator_bandwidth_top_k_pct": top_k_sweep,
    },
}

with open(os.path.join(BASE_DIR, "economics_summary.json"), "w") as f:
    json.dump(result, f, indent=2)

print(json.dumps({k: v for k, v in result.items() if k != "sensitivity"}, indent=2))
print(f"\nbreakeven intervention success rate (at top_k={TOP_K_PCT}): "
      f"{breakeven_success_rate:.1%}" if breakeven_success_rate is not None else "\nbreakeven: n/a")
print(f"(assumed success rate above breakeven: {INTERVENTION_SUCCESS_RATE:.0%} vs "
      f"{breakeven_success_rate:.1%} needed to cover modeled coordinator cost)")

print("\nSensitivity — by intervention success rate (top_k fixed at base):")
print(f"{'success_rate':>13} {'recovered':>10} {'net_value':>11}")
for r in success_rate_sweep:
    print(f"{r['intervention_success_rate']:>13.0%} {r['recovered_visits']:>10} {r['net_value_modeled']:>11,.0f}")

print("\nSensitivity — by coordinator bandwidth (success rate fixed at base):")
print(f"{'top_k_pct':>10} {'flagged':>8} {'recovered':>10} {'net_value':>11}")
for r in top_k_sweep:
    print(f"{r['top_k_pct_flagged']:>10.0%} {r['appointments_flagged_for_outreach']:>8} "
          f"{r['recovered_visits']:>10} {r['net_value_modeled']:>11,.0f}")

print("\nwrote model/economics_summary.json")
