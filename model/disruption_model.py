"""
CareOps disruption model.

v3 change (this pass): fixed a temporal-leakage bug in the risk features.

The original version pulled `previous_no_shows` and `communication_response_rate`
straight from patients.csv, where they are static, patient-level, end-of-dataset
summaries. That means an appointment in June was scored using a "previous
no-shows" count that actually includes no-shows that happened in July and
August — information that would not exist yet at prediction time. Same problem
for `new_patient` (a fixed True/False per patient, not "is this literally their
first visit").

Fix: for every appointment, recompute these as rolling values using only
appointments/communications for that patient strictly BEFORE that appointment's
date. This is what "features known at scoring time" actually requires for a
model meant to run on future appointments.

Both versions are fit and reported below — leaky vs. fixed — on the same
time-based split, so the impact of the bug is visible rather than silently
swapped out.
"""
import pandas as pd
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, roc_auc_score, precision_score, recall_score

DATA_DIR = "../data"

appts = pd.read_csv(f"{DATA_DIR}/appointments.csv")
patients = pd.read_csv(f"{DATA_DIR}/patients.csv")
ops = pd.read_csv(f"{DATA_DIR}/operational.csv")
comms = pd.read_csv(f"{DATA_DIR}/communications.csv")

df = appts.merge(patients, on="patient_id").merge(ops, on="appointment_id")
df["date"] = pd.to_datetime(df["date"])
df["disruption"] = df["status"].isin(["No-Show", "Cancelled"]).astype(int)
df["is_evening"] = (df["time_slot"] == "Evening").astype(int)
df["new_patient"] = df["new_patient"].astype(int)  # kept: original static leaky version, for comparison

# ---- sort chronologically per patient so "prior" is well-defined ----
df = df.sort_values(["patient_id", "date", "appointment_id"]).reset_index(drop=True)

# ---- rolling, leakage-free replacements ----
df["is_no_show"] = (df["status"] == "No-Show").astype(int)
df["previous_no_shows_to_date"] = (
    df.groupby("patient_id")["is_no_show"].cumsum() - df["is_no_show"]
)

df["appt_seq"] = df.groupby("patient_id").cumcount()
df["new_patient_to_date"] = (df["appt_seq"] == 0).astype(int)

comms["timestamp"] = pd.to_datetime(comms["timestamp"])
comms["responded"] = (comms["extracted_intent"] != "No Response").astype(int)
comms = comms.sort_values(["patient_id", "timestamp"])
comms["cum_responded"] = comms.groupby("patient_id")["responded"].cumsum()
comms["cum_total"] = comms.groupby("patient_id").cumcount() + 1

df = pd.merge_asof(
    df.sort_values("date"),
    comms[["patient_id", "timestamp", "cum_responded", "cum_total"]].sort_values("timestamp"),
    left_on="date", right_on="timestamp", by="patient_id",
    direction="backward", allow_exact_matches=False,  # strictly BEFORE the appointment date
)
df["response_rate_to_date_raw"] = df["cum_responded"] / df["cum_total"]
df = df.sort_values(["patient_id", "date", "appointment_id"]).reset_index(drop=True)

# ---- time-based split: train on June+July, test on August ----
train_df = df[df["date"] < "2026-08-01"].copy()
test_df = df[df["date"] >= "2026-08-01"].copy()

# Impute "no prior communication yet" using the TRAIN set's own mean only —
# using the full dataset's mean here would leak August's distribution into
# features scored on August.
fallback_response_rate = train_df["response_rate_to_date_raw"].mean()
for _df in (train_df, test_df, df):
    _df["response_rate_to_date"] = _df["response_rate_to_date_raw"].fillna(fallback_response_rate)

FEATURES_LEAKY = ["new_patient", "previous_no_shows", "communication_response_rate",
                  "travel_distance_km", "is_evening", "booking_lead_time_days"]

FEATURES_FIXED = ["new_patient_to_date", "previous_no_shows_to_date", "response_rate_to_date",
                  "travel_distance_km", "is_evening", "booking_lead_time_days"]


def fit_and_score(feature_list):
    X_train, y_train = train_df[feature_list], train_df["disruption"]
    X_test, y_test = test_df[feature_list], test_df["disruption"]
    m = LogisticRegression(max_iter=1000)
    m.fit(X_train, y_train)
    proba = m.predict_proba(X_test)[:, 1]
    return m, proba, y_test


leaky_model, leaky_proba, y_test = fit_and_score(FEATURES_LEAKY)
fixed_model, fixed_proba, _ = fit_and_score(FEATURES_FIXED)

# ---- downstream code (generate_dashboard_data.py) uses the FIXED model ----
model = fixed_model
features = FEATURES_FIXED
X_train, y_train = train_df[features], train_df["disruption"]
X_test, y_test = test_df[features], test_df["disruption"]
y_pred = model.predict(X_test)
y_proba = fixed_proba


def _report(name, m, proba, feature_list):
    preds = (proba >= 0.5).astype(int)
    print(f"\n=== {name} (features: {feature_list}) ===")
    print(classification_report(y_test, preds, target_names=["On-track", "Disruption"]))
    print("ROC-AUC:", round(roc_auc_score(y_test, proba), 3))
    print("Coefficients:")
    for f, c in sorted(zip(feature_list, m.coef_[0]), key=lambda x: -abs(x[1])):
        print(f"  {f}: {round(c, 3)}")


if __name__ == "__main__":
    print("=== Time-based split ===")
    print(f"train: {len(train_df)} appts (Jun-Jul) | test: {len(test_df)} appts (Aug)")
    print(f"(response_rate_to_date fallback used for {int(train_df['response_rate_to_date_raw'].isna().sum() + test_df['response_rate_to_date_raw'].isna().sum())} "
          f"appointments with no prior patient communication — filled with train-set mean = {round(fallback_response_rate,3)})")

    _report("LEAKY (original — static patient-level features)", leaky_model, leaky_proba, FEATURES_LEAKY)
    _report("FIXED (rolling, as-of-appointment-date features)", fixed_model, fixed_proba, FEATURES_FIXED)

    print("\n=== Threshold tradeoff, FIXED model (precision vs recall) ===")
    for t in [0.5, 0.4, 0.3, 0.25, 0.2, 0.15]:
        preds = (y_proba >= t).astype(int)
        p = precision_score(y_test, preds, zero_division=0)
        r = recall_score(y_test, preds, zero_division=0)
        flagged_pct = round(preds.mean() * 100, 1)
        print(f"threshold={t:.2f} | precision={p:.2f} | recall={r:.2f} | %flagged={flagged_pct}%")

    print("\n=== Top 20% risk band, FIXED model ===")
    cutoff = np.quantile(y_proba, 0.8)
    top20 = y_proba >= cutoff
    p20 = precision_score(y_test, top20, zero_division=0)
    r20 = recall_score(y_test, top20, zero_division=0)
    print(f"cutoff={round(cutoff,3)} | precision={round(p20,3)} | recall={round(r20,3)} | %flagged={round(top20.mean()*100,1)}%")
