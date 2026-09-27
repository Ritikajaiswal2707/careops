"""
Module 8: simulated intervention/outcome loop.

The loop the rest of this repo builds up to (Predict -> Recommend -> Propose
-> a real, enforced state machine) still stopped one step short of closing:
economics_simulation.py's "recovered_visits" was a single top-down multiply
(true_positives * an assumed success rate), never an actual per-case outcome.
Nothing in the repo ever drove a flagged appointment all the way through
agent_state_machine.RescheduleCase using the REAL ranked candidates from
capacity_recovery.recommend() and recorded what happened. This module does
that:

    risk model flags appointment -> capacity_recovery ranks real candidates
    -> RescheduleCase drives PROPOSED -> a simulated patient response (accept
    / decline) -> on decline, retry the next-ranked candidate or ESCALATE
    -> on accept, BOOKED -> PROVIDER_NOTIFIED -> COMPLETED -> outcome logged

exactly the "Intervention -> Patient accepted -> Appointment recovered ->
Outcome logged" loop the case study still needed, using this project's own
real state machine and real Recovery Score ranking rather than inventing a
new simulated mechanism for the occasion.

What is and is NOT new here, stated plainly:
  - NOT new: the intervention_success_rate assumption itself. It's the exact
    same placeholder economics_simulation.py already discloses (0.35, not
    measured, see that file's ASSUMPTIONS block) -- kept in sync here, not
    re-derived, so the two files can't quietly drift onto different numbers.
  - NEW: applying that assumption at the level of one simulated patient
    response per proposed candidate, not one multiply against an aggregate
    count. That surfaces two effects the flat multiply structurally cannot:
      1. Retries. A patient who declines the first-ranked provider still
         gets the second- and third-ranked candidate (top_n=3, same as
         reschedule_agent.py) before the case is escalated. Each attempt is
         an independent draw, so the OVERALL chance a true disruption gets
         recovered is higher than the flat per-contact rate, exactly because
         there are multiple chances -- and each attempt also costs another
         coordinator contact, which the flat "8 min x flagged appointments"
         estimate never charged for.
      2. Same-day slot contention. Appointments are processed in risk-rank
         order within each date, sharing one capacity_recovery.build_candidates()
         context per date and calling commit_recommendation() after every
         actual booking -- so two flagged appointments on the same day can no
         longer both be told the same provider/slot has room (the same fix
         generate_dashboard_data.py already applies for its own run, now also
         applied across a full evaluation period instead of one simulated day).

What is still a modeling choice, not a measurement, and should be read as one:
  - A flagged appointment that was actually NOT a disruption (a false
    positive) is logged as a single confirmation contact with no reschedule
    search at all -- there is nothing to recover, since the patient was
    always going to complete the visit. This keeps the coordinator-time
    accounting honest (false positives still cost a contact) without
    running a reschedule negotiation that has no real question behind it.
  - Every retry reuses the SAME per-attempt success rate. A real system
    would likely see rank-dependent acceptance (the first-proposed slot is
    probably more likely to be accepted than a third fallback) -- this
    script does not assume that, because there's no measured basis for a
    rank-dependent curve either.
  - The random draws are seeded (RANDOM_SEED) for a reproducible run, not
    because the underlying accept/decline behavior is deterministic.

Answers the product question the top-down multiply couldn't: does modeling
the ACTUAL negotiation (retries, exhaustion, shared capacity) move the
economics meaningfully vs. the simpler estimate -- and in which direction?

The actual result, running this against the August test period: bottom-up
recovered visits come in FAR BELOW the top-down multiply (16 vs. 74), not
above it. The reason isn't the accept/decline draw at all -- it's that
recommend() returns zero eligible candidates for 164 of the 212 true
disruptions among flagged appointments (77%) before a single patient
response is even simulated. The top-down formula multiplies success rate
against true_positives and implicitly assumes a recoverable slot always
exists to accept or decline; this run shows that assumption is the one
actually driving the gap, not the placeholder success rate. That's a
capacity-data finding, not a patient-behavior one -- see README's "Known
limitations" note on slot-level capacity being daily/slot-split rather than
provider+date+time-level, which is the more likely fix than tuning
INTERVENTION_SUCCESS_RATE.
"""
import json
import os
from collections import Counter

import numpy as np
import pandas as pd

from disruption_model import test_df, y_test, y_proba, features
from capacity_recovery import build_candidates, recommend, commit_recommendation
from agent_state_machine import RescheduleCase

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ---- kept in sync with economics_simulation.py's ASSUMPTIONS block --------
TOP_K_PCT = 0.20
INTERVENTION_SUCCESS_RATE = 0.35
COORDINATOR_MIN_PER_CONTACT = 8
REVENUE_PER_COMPLETED_VISIT = 800
COORDINATOR_HOURLY_COST = 300
MAX_CANDIDATES_PER_CASE = 3  # same top_n reschedule_agent.py searches
RANDOM_SEED = 42

rng = np.random.default_rng(RANDOM_SEED)

# ---- same flagged set economics_simulation.py's base case uses ------------
n = len(y_test)
y_arr = y_test.values
order = y_proba.argsort()[::-1]
n_flag = int(round(n * TOP_K_PCT))
flagged_idx = order[:n_flag]

# test_df, X_test/y_test and y_proba all come from the same row order (no
# reordering happens between test_df's construction and model.predict_proba
# in disruption_model.py), so positional .iloc alignment is valid here.
flagged_rows = test_df.iloc[flagged_idx].copy()
flagged_rows["risk_rank"] = range(len(flagged_rows))  # 0 = highest risk, preserved from `order`

# Process date-by-date, but within a date keep highest-risk-first — the order
# a real coordinator with limited bandwidth would actually work the list —
# so slot contention is resolved in favor of the higher-priority case, not
# whichever row happened to come first in the dataframe.
flagged_rows = flagged_rows.sort_values(["date", "risk_rank"])

ctx_cache = {}
cases = []

for _, row in flagged_rows.iterrows():
    appt_id = row["appointment_id"]
    date_str = str(row["date"].date())
    true_label = int(row["disruption"])

    if date_str not in ctx_cache:
        ctx_cache[date_str] = build_candidates(date_str)
    ctx = ctx_cache[date_str]

    if true_label == 0:
        # False positive: nothing to recover, but the coordinator still
        # spends a contact confirming the visit is actually fine.
        cases.append({
            "appointment_id": appt_id,
            "date": date_str,
            "true_label": 0,
            "simulated_outcome": "CONFIRMED_NO_ACTION_NEEDED",
            "attempts": 1,
            "coordinator_minutes": COORDINATOR_MIN_PER_CONTACT,
            "recovered": False,
        })
        continue

    ranked = recommend(appt_id, date_str, ctx, service_type=row["service_type"], top_n=MAX_CANDIDATES_PER_CASE)

    if not ranked:
        cases.append({
            "appointment_id": appt_id,
            "date": date_str,
            "true_label": 1,
            "simulated_outcome": "ESCALATED_NO_CANDIDATE",
            "attempts": 1,
            "coordinator_minutes": COORDINATOR_MIN_PER_CONTACT,
            "recovered": False,
            "candidates_considered": 0,
        })
        continue

    case = RescheduleCase(appt_id, ranked)
    attempts = 0
    recovered = False
    booked_provider = None

    while True:
        candidate = case.propose_next()
        if candidate is None:
            break  # SEARCH_ALTERNATIVE -> ESCALATED: candidates exhausted
        attempts += 1
        accepted = rng.random() < INTERVENTION_SUCCESS_RATE
        if accepted:
            case.patient_confirms()
            case.book()
            case.notify_provider()
            case.complete()
            commit_recommendation(ctx, candidate["provider_id"], row["time_slot"])
            recovered = True
            booked_provider = candidate["provider_id"]
            break
        else:
            case.patient_declines()  # -> DECLINED -> SEARCH_ALTERNATIVE, next candidate on the next loop

    cases.append({
        "appointment_id": appt_id,
        "date": date_str,
        "true_label": 1,
        "simulated_outcome": case.state.value,
        "attempts": attempts,
        "coordinator_minutes": attempts * COORDINATOR_MIN_PER_CONTACT,
        "recovered": recovered,
        "candidates_considered": len(ranked),
        "booked_provider": booked_provider,
        "history": case.history_trace(),
    })

# ---- aggregate the bottom-up, per-case simulated result -------------------
n_true_positive = sum(1 for c in cases if c["true_label"] == 1)
n_false_positive = sum(1 for c in cases if c["true_label"] == 0)
recovered_visits_sim = sum(1 for c in cases if c["recovered"])
escalated_sim = sum(1 for c in cases if c["true_label"] == 1 and not c["recovered"])
total_coordinator_minutes_sim = sum(c["coordinator_minutes"] for c in cases)
coordinator_hours_sim = round(total_coordinator_minutes_sim / 60, 1)
contribution_recovered_sim = recovered_visits_sim * REVENUE_PER_COMPLETED_VISIT
coordinator_cost_sim = round(coordinator_hours_sim * COORDINATOR_HOURLY_COST, 0)
net_value_sim = round(contribution_recovered_sim - coordinator_cost_sim, 0)

attempts_among_recovered = Counter(c["attempts"] for c in cases if c["recovered"])

# ---- the top-down comparison point (economics_simulation.py's own formula,
# recomputed inline at the same TOP_K_PCT/INTERVENTION_SUCCESS_RATE so the
# two numbers are guaranteed comparable, without importing that module and
# re-triggering its own file write/prints as a side effect) -----------------
recovered_visits_topdown = round(n_true_positive * INTERVENTION_SUCCESS_RATE)
coordinator_hours_topdown = round(n_flag * COORDINATOR_MIN_PER_CONTACT / 60, 1)
contribution_recovered_topdown = recovered_visits_topdown * REVENUE_PER_COMPLETED_VISIT
coordinator_cost_topdown = round(coordinator_hours_topdown * COORDINATOR_HOURLY_COST, 0)
net_value_topdown = round(contribution_recovered_topdown - coordinator_cost_topdown, 0)

result = {
    "evaluation_period": "August (test split, unseen by model)",
    "assumptions": {
        "top_k_pct_flagged": TOP_K_PCT,
        "intervention_success_rate_per_attempt": INTERVENTION_SUCCESS_RATE,
        "coordinator_min_per_contact": COORDINATOR_MIN_PER_CONTACT,
        "revenue_per_completed_visit": REVENUE_PER_COMPLETED_VISIT,
        "coordinator_hourly_cost": COORDINATOR_HOURLY_COST,
        "max_candidates_per_case": MAX_CANDIDATES_PER_CASE,
        "random_seed": RANDOM_SEED,
        "note": "intervention_success_rate is the SAME placeholder economics_simulation.py uses, "
                "applied per attempt here instead of once as an aggregate multiply -- not a new "
                "or independently-tuned number.",
    },
    "n_flagged": len(cases),
    "n_true_positive_among_flagged": n_true_positive,
    "n_false_positive_among_flagged": n_false_positive,
    "bottom_up_simulated": {
        "recovered_visits": recovered_visits_sim,
        "escalated_no_recovery": escalated_sim,
        "coordinator_hours": coordinator_hours_sim,
        "contribution_recovered": contribution_recovered_sim,
        "coordinator_cost": coordinator_cost_sim,
        "net_value": net_value_sim,
        "attempts_to_success_distribution": dict(sorted(attempts_among_recovered.items())),
    },
    "top_down_baseline": {
        "recovered_visits": recovered_visits_topdown,
        "coordinator_hours": coordinator_hours_topdown,
        "contribution_recovered": contribution_recovered_topdown,
        "coordinator_cost": coordinator_cost_topdown,
        "net_value": net_value_topdown,
    },
    "delta_simulated_minus_topdown": {
        "recovered_visits": recovered_visits_sim - recovered_visits_topdown,
        "coordinator_hours": round(coordinator_hours_sim - coordinator_hours_topdown, 1),
        "net_value": net_value_sim - net_value_topdown,
    },
    "cases": cases,
}

with open(os.path.join(BASE_DIR, "intervention_outcomes.json"), "w") as f:
    json.dump(result, f, indent=2, default=str)

if __name__ == "__main__":
    print(f"flagged: {len(cases)} ({n_true_positive} true disruptions, {n_false_positive} false positives)")
    print("\n== bottom-up (simulated per-case outcomes) vs. top-down (flat multiply) ==")
    print(f"{'':28}{'bottom-up':>12}{'top-down':>12}{'delta':>10}")
    print(f"{'recovered visits':28}{recovered_visits_sim:>12}{recovered_visits_topdown:>12}"
          f"{recovered_visits_sim - recovered_visits_topdown:>+10}")
    print(f"{'coordinator hours':28}{coordinator_hours_sim:>12}{coordinator_hours_topdown:>12}"
          f"{round(coordinator_hours_sim - coordinator_hours_topdown, 1):>+10}")
    print(f"{'net value (modeled)':28}{net_value_sim:>12,.0f}{net_value_topdown:>12,.0f}"
          f"{net_value_sim - net_value_topdown:>+10,.0f}")
    print(f"\nescalated (candidates exhausted or none eligible), no recovery: {escalated_sim} "
          f"of {n_true_positive} true disruptions among flagged")
    print(f"attempts-to-success distribution among recovered cases: {dict(sorted(attempts_among_recovered.items()))}")
    print("\nwrote model/intervention_outcomes.json")
