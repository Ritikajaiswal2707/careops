"""
CareOps disruption model.

Change from the original prototype:
- Time-based train/test split (train on June-July, test on August) instead of
  a random 80/20 split, since this model is meant to predict FUTURE appointments.
- Reports metrics against that split so the numbers reflect a realistic
  deployment scenario rather than a shuffled one.
"""
import pandas as pd
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, roc_auc_score, precision_score, recall_score

DATA_DIR = "../data"

appts = pd.read_csv(f"{DATA_DIR}/appointments.csv")
patients = pd.read_csv(f"{DATA_DIR}/patients.csv")
ops = pd.read_csv(f"{DATA_DIR}/operational.csv")

df = appts.merge(patients, on="patient_id").merge(ops, on="appointment_id")
df["date"] = pd.to_datetime(df["date"])
df["disruption"] = df["status"].isin(["No-Show", "Cancelled"]).astype(int)
df["is_evening"] = (df["time_slot"] == "Evening").astype(int)
df["new_patient"] = df["new_patient"].astype(int)

features = ["new_patient", "previous_no_shows", "communication_response_rate",
            "travel_distance_km", "is_evening", "booking_lead_time_days"]

# ---- time-based split: train on June+July, test on August ----
train_df = df[df["date"] < "2026-08-01"]
test_df = df[df["date"] >= "2026-08-01"]

X_train, y_train = train_df[features], train_df["disruption"]
X_test, y_test = test_df[features], test_df["disruption"]

model = LogisticRegression(max_iter=1000)
model.fit(X_train, y_train)

y_pred = model.predict(X_test)
y_proba = model.predict_proba(X_test)[:, 1]

if __name__ == "__main__":
    print("=== Time-based split ===")
    print(f"train: {len(train_df)} appts (Jun-Jul) | test: {len(test_df)} appts (Aug)")

    print("\n=== Model performance (test = August, unseen) ===")
    print(classification_report(y_test, y_pred, target_names=["On-track", "Disruption"]))
    print("ROC-AUC:", round(roc_auc_score(y_test, y_proba), 3))

    print("\n=== Feature coefficients (plain-language weight) ===")
    for f, c in sorted(zip(features, model.coef_[0]), key=lambda x: -abs(x[1])):
        print(f"{f}: {round(c,3)}")

    print("\n=== Threshold tradeoff (precision vs recall) ===")
    for t in [0.5, 0.4, 0.3, 0.25, 0.2, 0.15]:
        preds = (y_proba >= t).astype(int)
        p = precision_score(y_test, preds, zero_division=0)
        r = recall_score(y_test, preds, zero_division=0)
        flagged_pct = round(preds.mean()*100, 1)
        print(f"threshold={t:.2f} | precision={p:.2f} | recall={r:.2f} | %flagged={flagged_pct}%")
