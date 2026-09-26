"""
Module 6: Capacity recovery.

For appointments the risk/cascade layers flag as needing reassignment, this
finds an actual candidate provider — not just "reassign if available" as a
suggested action with nothing behind it.

Constraints used:
  - same city/area as the patient (providers.csv has no lat/long, only area,
    so this is the finest-grained location match the data supports)
  - marked available that date in availability.csv
  - has remaining daily capacity (today's assigned load < daily_capacity)
  - not the provider already on the appointment

Note on specialization: providers.csv has a `specialization` field, but
checking it against how providers are actually assigned to service_types
in appointments.csv shows almost no relationship — every service type pulls
from all five specializations in roughly the same proportions (see notebook
check). So specialization is used here as a soft tie-breaker, not a hard
filter — treating it as a hard filter would reject valid candidates based on
a constraint the data doesn't actually enforce.
"""
import pandas as pd

DATA_DIR = "../data"


def build_candidates(target_date: str):
    providers = pd.read_csv(f"{DATA_DIR}/providers.csv")
    availability = pd.read_csv(f"{DATA_DIR}/availability.csv")
    appts = pd.read_csv(f"{DATA_DIR}/appointments.csv")
    patients = pd.read_csv(f"{DATA_DIR}/patients.csv")

    avail_today = availability[availability["date"] == target_date].set_index("provider_id")["available"]

    today_appts = appts[appts["date"] == target_date]
    load_today = today_appts.groupby("provider_id").size()

    cand = providers.copy()
    cand["available_today"] = cand["provider_id"].map(avail_today).fillna(False)
    cand["assigned_today"] = cand["provider_id"].map(load_today).fillna(0).astype(int)
    cand["remaining_capacity"] = cand["daily_capacity"] - cand["assigned_today"]
    return cand, appts, patients


def recommend(appointment_id: str, target_date: str, cand=None, appts=None, patients=None, service_type=None):
    if cand is None:
        cand, appts, patients = build_candidates(target_date)

    appt_row = appts[appts["appointment_id"] == appointment_id].iloc[0]
    patient = patients[patients["patient_id"] == appt_row["patient_id"]].iloc[0]
    current_provider = appt_row["provider_id"]

    pool = cand[
        (cand["area"] == patient["area"]) &
        (cand["available_today"] == True) &
        (cand["remaining_capacity"] > 0) &
        (cand["provider_id"] != current_provider)
    ].copy()

    if pool.empty:
        return None

    # soft preference: same specialization as whoever currently holds this
    # service type most often (not a hard filter — see module docstring)
    current_spec = cand.loc[cand["provider_id"] == current_provider, "specialization"]
    current_spec = current_spec.iloc[0] if not current_spec.empty else None
    pool["spec_match"] = (pool["specialization"] == current_spec).astype(int)

    pool = pool.sort_values(["spec_match", "remaining_capacity"], ascending=[False, False])
    best = pool.iloc[0]
    return {
        "provider_id": best["provider_id"],
        "employment_type": best["employment_type"],
        "area": best["area"],
        "remaining_capacity": int(best["remaining_capacity"]),
        "specialization_match": bool(best["spec_match"]),
    }


if __name__ == "__main__":
    TODAY = "2026-08-29"
    cand, appts, patients = build_candidates(TODAY)
    print(f"Providers available on {TODAY} with spare capacity:")
    print(cand[(cand["available_today"]) & (cand["remaining_capacity"] > 0)]
          [["provider_id", "area", "specialization", "remaining_capacity"]].to_string(index=False))
