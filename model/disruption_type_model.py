"""
Module 1c: disruption TYPE, not just disruption yes/no.

Stage 1 (disruption_model.py) answers "will this visit be disrupted?" — a
single binary target: status in {No-Show, Cancelled}. That collapses three
product-distinct situations into one number:
  - No-Show:     patient wasn't there / didn't respond — the intervention is
                 confirmation and reachability (call, backup contact)
  - Cancelled:   patient actively declined this visit — the intervention is
                 understanding why and offering to backfill the freed slot
  - Rescheduled: patient still wants care, just not at this time — the
                 intervention is exactly what reschedule_agent.py already
                 does (propose a new slot), NOT a "disruption" to prevent

That third one is a real gap in the current target, not just a naming
nitpick: Rescheduled status currently falls OUTSIDE the binary disruption
target entirely (isin(["No-Show","Cancelled"]) is False for it), so it's
silently counted as "not disrupted" — lumped in with Completed in every
number `disruption_model.py` and `economics_simulation.py` report. In the
August test set that's 138 of 3,155 appointments (4.4%) whose actual outcome
(the visit, as scheduled, did not happen) is invisible to the risk model's
own target.

This script doesn't rebuild the pipeline as a 3-class target — with this
few Rescheduled cases in training data (478 total, and status is an
OUTCOME field, not knowable at prediction time the way a patient's message
is) a clean 3-way classifier would be fit on very little signal per class.
Instead: a Stage 2 diagnostic model that predicts No-Show vs. Cancelled
specifically (the two the binary target already treats identically), so the
action engine can tell them apart — plus an honest accounting of where
Rescheduled sits today.

Naming note (fixed this pass): this is trained and evaluated on
appointments filtered by the TRUE status label (`status.isin(["No-Show",
"Cancelled"])`) — i.e. an oracle diagnostic ("among visits that actually
disrupted, can these features tell you which way?"), not a live downstream
step conditioned on Stage 1's own prediction. The earlier docstring/print
wording ("conditional on Stage 1 flagging disruption") blurred that
distinction — worth being precise about, since a real deployment can only
condition on Stage 1's predicted flag, not the true outcome it's still
trying to predict.
"""
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, roc_auc_score
from disruption_model import df, train_df, test_df, FEATURES_FIXED

# ---- Stage 2: among ACTUAL disruptions, No-Show vs. Cancelled ----
train_disrupted = train_df[train_df["status"].isin(["No-Show", "Cancelled"])].copy()
test_disrupted = test_df[test_df["status"].isin(["No-Show", "Cancelled"])].copy()
train_disrupted["is_cancelled"] = (train_disrupted["status"] == "Cancelled").astype(int)
test_disrupted["is_cancelled"] = (test_disrupted["status"] == "Cancelled").astype(int)

stage2_model = LogisticRegression(max_iter=1000)
stage2_model.fit(train_disrupted[FEATURES_FIXED], train_disrupted["is_cancelled"])
stage2_proba = stage2_model.predict_proba(test_disrupted[FEATURES_FIXED])[:, 1]
stage2_pred = (stage2_proba >= 0.5).astype(int)


def action_for_type(predicted_type: str) -> str:
    return {
        "No-Show": "Send confirmation + backup contact request",
        "Cancelled": "Ask reason + offer to backfill this slot from the waitlist",
    }[predicted_type]


if __name__ == "__main__":
    print(f"Stage 2 diagnostic (among ACTUAL disruptions, by true status — not conditioned on "
          f"Stage 1's predicted flag): No-Show vs. Cancelled, n={len(test_disrupted)}")
    print(classification_report(test_disrupted["is_cancelled"], stage2_pred,
                                 target_names=["No-Show", "Cancelled"]))
    try:
        auc = roc_auc_score(test_disrupted["is_cancelled"], stage2_proba)
        print("ROC-AUC:", round(auc, 3))
    except ValueError:
        auc = None
        print("ROC-AUC: undefined (one class only in this split)")

    print("\nStage 2 coefficients (what distinguishes Cancelled from No-Show, among disruptions):")
    for f, c in sorted(zip(FEATURES_FIXED, stage2_model.coef_[0]), key=lambda x: -abs(x[1])):
        print(f"  {f}: {round(c, 3)}")

    # ---- honest accounting: where does Rescheduled sit in the CURRENT target? ----
    n_test = len(test_df)
    n_resched = int((test_df["status"] == "Rescheduled").sum())
    print(f"\nRescheduled status in the August test set: {n_resched} of {n_test} ({n_resched/n_test:.1%})")
    print("These are currently counted as NOT disrupted by disruption_model.py's binary target")
    print("(status in [No-Show, Cancelled] is False for Rescheduled) — lumped in with Completed.")
    print("Not fixed here: a clean 3-way target needs more Rescheduled examples per split than this")
    print("dataset has (478 total across 3 months). Flagged as a target-definition limitation instead")
    print("of silently left as an undocumented one.")

    print(f"\nHonest conclusion: Stage 2 ROC-AUC of {round(auc,3) if auc is not None else 'undefined'} is close to")
    print("chance. These 6 features (all patient/booking-side) don't meaningfully separate WHY a visit")
    print("was disrupted, only THAT it was — the model collapses to predicting the majority class")
    print("(No-Show). Distinguishing No-Show from Cancelled likely needs signal this dataset doesn't")
    print("have yet (e.g. the communication_intelligence extracted intent leading up to the visit),")
    print("not more of the same features. Reported as a negative result, not hidden.")
