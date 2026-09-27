"""
Module 1b: subgroup fairness check on the risk model.

The README used to claim "the model over-indexes on first-time-patient
status" — a claim made from the raw logistic coefficient alone. Two problems
with that: (1) after the leakage fix, previous_no_shows_to_date is actually
the larger coefficient, not new_patient_to_date, so the claim is now simply
false; and (2) raw coefficients from features on different scales (a 0/1
flag vs. a count vs. a 0-1 rate vs. km) aren't comparable to begin with — a
bigger number doesn't mean a bigger real-world effect.

This script replaces the coefficient-reading with an actual subgroup check:
at the operational top-20%-risk threshold, does a first-time patient get
flagged at a different rate than a returning patient does, relative to how
often each group actually gets disrupted? Precision, recall, false-positive
rate, and a calibration comparison (mean predicted risk vs. actual
disruption rate), split by new_patient_to_date, on the same August test set.
"""
import numpy as np
from sklearn.metrics import precision_score, recall_score
from disruption_model import test_df, y_proba, y_test

CUTOFF = np.quantile(y_proba, 0.8)  # same top-20% operational threshold used elsewhere
flagged = y_proba >= CUTOFF

results = {}
for label, mask in [
    ("First-time patients (new_patient_to_date=1)", test_df["new_patient_to_date"] == 1),
    ("Returning patients (new_patient_to_date=0)", test_df["new_patient_to_date"] == 0),
]:
    y_sub = y_test[mask]
    flag_sub = flagged[mask]
    proba_sub = y_proba[mask]

    n = int(mask.sum())
    actual_rate = float(y_sub.mean())
    flag_rate = float(flag_sub.mean())
    precision = precision_score(y_sub, flag_sub, zero_division=0)
    recall = recall_score(y_sub, flag_sub, zero_division=0)
    # false-positive rate: of the NOT-actually-disrupted, what share got flagged anyway
    not_disrupted = y_sub == 0
    fpr = float(flag_sub[not_disrupted].mean()) if not_disrupted.sum() else float("nan")
    mean_predicted = float(proba_sub.mean())

    results[label] = {
        "n": n,
        "actual_disruption_rate": round(actual_rate, 3),
        "flagged_rate": round(flag_rate, 3),
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "false_positive_rate": round(fpr, 3),
        "mean_predicted_risk": round(mean_predicted, 3),
        "calibration_gap": round(mean_predicted - actual_rate, 3),  # + = overconfident for this group
    }

if __name__ == "__main__":
    print(f"Subgroup fairness check at the top-20% operational threshold (cutoff={round(CUTOFF,3)}):\n")
    for label, r in results.items():
        print(f"{label}  (n={r['n']})")
        print(f"  actual disruption rate   {r['actual_disruption_rate']:.1%}")
        print(f"  flagged rate             {r['flagged_rate']:.1%}")
        print(f"  precision                {r['precision']:.1%}")
        print(f"  recall                   {r['recall']:.1%}")
        print(f"  false-positive rate      {r['false_positive_rate']:.1%}")
        print(f"  mean predicted risk      {r['mean_predicted_risk']:.1%}  (calibration gap: {r['calibration_gap']:+.1%})")
        print()

    fp_gap = results["First-time patients (new_patient_to_date=1)"]["false_positive_rate"] - \
             results["Returning patients (new_patient_to_date=0)"]["false_positive_rate"]
    print(f"First-time vs. returning false-positive-rate gap: {fp_gap:+.1%} "
          f"({'first-time patients are flagged more often when nothing goes wrong' if fp_gap > 0 else 'no meaningful gap in this direction'})")
