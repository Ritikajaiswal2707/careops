import pandas as pd
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, roc_auc_score

appts = pd.read_csv("/mnt/user-data/outputs/appointments.csv")
patients = pd.read_csv("/mnt/user-data/outputs/patients.csv")
ops = pd.read_csv("/mnt/user-data/outputs/operational.csv")

df = appts.merge(patients, on="patient_id").merge(ops, on="appointment_id")
df["disruption"] = df["status"].isin(["No-Show", "Cancelled"]).astype(int)
df["is_evening"] = (df["time_slot"] == "Evening").astype(int)
df["new_patient"] = df["new_patient"].astype(int)

features = ["new_patient", "previous_no_shows", "communication_response_rate",
            "travel_distance_km", "is_evening", "booking_lead_time_days"]
X = df[features]
y = df["disruption"]

X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)

model = LogisticRegression(max_iter=1000)
model.fit(X_train, y_train)

y_pred = model.predict(X_test)
y_proba = model.predict_proba(X_test)[:, 1]

print("=== Model performance ===")
print(classification_report(y_test, y_pred, target_names=["On-track", "Disruption"]))
print("ROC-AUC:", round(roc_auc_score(y_test, y_proba), 3))

print("\n=== Feature coefficients (plain-language weight) ===")
for f, c in sorted(zip(features, model.coef_[0]), key=lambda x: -abs(x[1])):
    print(f"{f}: {round(c,3)}")

# ---- explanation layer: rule-based plain-language reason generator ----
def explain(row, proba):
    reasons = []
    if row["new_patient"] == 1:
        reasons.append("first-time patient")
    if row["previous_no_shows"] >= 2:
        reasons.append(f"{row['previous_no_shows']} prior no-shows")
    if row["communication_response_rate"] < 0.5:
        reasons.append("low message response rate")
    if row["travel_distance_km"] > 12:
        reasons.append(f"{row['travel_distance_km']}km from clinician")
    if row["is_evening"] == 1:
        reasons.append("evening slot (historically higher risk)")
    if not reasons:
        reasons.append("no single dominant factor; borderline risk")
    tier = "High" if proba >= 0.5 else ("Medium" if proba >= 0.3 else "Low")
    return tier, reasons

# Simulate "today's operations view": take 8 upcoming appointments, sorted by risk
sample = df.sample(200, random_state=7).copy()
sample["risk_proba"] = model.predict_proba(sample[features])[:, 1]
top_risk = sample.sort_values("risk_proba", ascending=False).head(8)

print("\n=== Sample: Today's flagged visits (for dashboard) ===")
for _, row in top_risk.iterrows():
    tier, reasons = explain(row, row["risk_proba"])
    print(f"- {row['appointment_id']} | risk={round(row['risk_proba'],2)} ({tier}) | {', '.join(reasons)}")

print("\n=== Threshold tradeoff (precision vs recall) ===")
from sklearn.metrics import precision_score, recall_score
for t in [0.5, 0.4, 0.3, 0.25, 0.2, 0.15]:
    preds = (y_proba >= t).astype(int)
    p = precision_score(y_test, preds, zero_division=0)
    r = recall_score(y_test, preds, zero_division=0)
    flagged_pct = round(preds.mean()*100, 1)
    print(f"threshold={t:.2f} | precision={p:.2f} | recall={r:.2f} | %of visits flagged={flagged_pct}%")
