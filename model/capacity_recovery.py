"""
Module 6: Capacity recovery.

v2 change (this pass): the original version filtered candidate providers down
to a pool (same area, available, spare capacity, not the current provider)
and then picked the best by a single soft tie-breaker (specialization match).
That's a filter, not a recommendation — it can't say *why* one acceptable
candidate beats another, or trade one constraint off against another.

This version scores every eligible candidate on a weighted Recovery Score
and shows the breakdown, so "Recommended: PR019" comes with a reason, not
just a rank:

  Recovery Score =
      + continuity        (has this provider treated this patient before?)
      + proximity          (distance from the provider's inferred operating
                             area to the patient, not just "same city")
      + remaining capacity (headroom today, as a fraction of daily_capacity)
      + schedule fit       (is there room in the SAME time-of-day slot, not
                             just somewhere in the provider's day?)
      + service fit        (soft, low-weight — see note below)
      - utilization penalty (providers already near their daily_capacity are
                              penalized: assigning more load to an already-full
                              day raises the odds of a knock-on delay cascade)

Two data limitations, carried over honestly from v1 and still true here:
  - providers.csv has no lat/long, only `area` (city). There's no ground-truth
    provider location to compute real distance from, so "proximity" here uses
    each provider's OWN historical patient locations (mean lat/long of
    patients they've actually served in appointments.csv) as an inferred
    operating centroid. That's a real, data-derived location — not the
    patient's own city centroid — but it's an approximation, not a GPS fact.
  - checking `specialization` against how providers are actually assigned to
    service_types in appointments.csv still shows close to no relationship
    (~22% ± 2pp for every specialization, regardless of service_type — see
    notebook check). So "service fit" stays a low-weight soft signal here,
    not something the score leans on, because the data doesn't support
    leaning on it.
"""
import math
import pandas as pd

DATA_DIR = "../data"

WEIGHTS = {
    "continuity": 25,
    "proximity": 25,
    "capacity": 15,
    "schedule_fit": 15,
    "service_fit": 5,
}
UTILIZATION_PENALTY_WEIGHT = 10  # subtracted, scaled by how over/near capacity the provider already is


def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _provider_centroids(appts, patients):
    """Each provider's inferred operating location: mean lat/long of every
    patient they've actually served, per the appointment history. This is a
    real signal derived from the data, not a stand-in for GPS coordinates
    Anthropic doesn't have."""
    m = appts.merge(patients[["patient_id", "latitude", "longitude"]], on="patient_id")
    return m.groupby("provider_id")[["latitude", "longitude"]].mean()


def _patient_provider_history(appts):
    """Set of (patient_id, provider_id) pairs seen at least once — used for
    the continuity score."""
    return set(zip(appts["patient_id"], appts["provider_id"]))


def build_candidates(target_date: str):
    providers = pd.read_csv(f"{DATA_DIR}/providers.csv")
    availability = pd.read_csv(f"{DATA_DIR}/availability.csv")
    appts = pd.read_csv(f"{DATA_DIR}/appointments.csv")
    patients = pd.read_csv(f"{DATA_DIR}/patients.csv")

    avail_today = availability[availability["date"] == target_date].set_index("provider_id")["available"]

    today_appts = appts[appts["date"] == target_date]
    load_today = today_appts.groupby("provider_id").size()
    # per-time-slot load, for the schedule-fit component. daily_capacity is a
    # whole-day figure with no stated per-slot breakdown, so an even 3-way
    # split (Morning/Afternoon/Evening) is an approximation, flagged as such.
    slot_load_today = today_appts.groupby(["provider_id", "time_slot"]).size()

    cand = providers.copy()
    cand["available_today"] = cand["provider_id"].map(avail_today).fillna(False)
    cand["assigned_today"] = cand["provider_id"].map(load_today).fillna(0).astype(int)
    cand["remaining_capacity"] = cand["daily_capacity"] - cand["assigned_today"]
    cand["utilization_today"] = (cand["assigned_today"] / cand["daily_capacity"]).clip(upper=2.0)

    centroids = _provider_centroids(appts, patients)
    cand = cand.merge(centroids, on="provider_id", how="left")

    return {
        "cand": cand,
        "appts": appts,
        "patients": patients,
        "slot_load_today": slot_load_today,
        "history": _patient_provider_history(appts),
    }


def recommend(appointment_id: str, target_date: str, ctx=None, service_type=None, top_n=1):
    """Returns the top-scoring candidate (top_n=1, backward-compatible dict)
    or a ranked list of candidates with score breakdowns (top_n>1)."""
    if ctx is None:
        ctx = build_candidates(target_date)
    cand, appts, patients = ctx["cand"], ctx["appts"], ctx["patients"]
    slot_load_today, history = ctx["slot_load_today"], ctx["history"]

    appt_row = appts[appts["appointment_id"] == appointment_id].iloc[0]
    patient = patients[patients["patient_id"] == appt_row["patient_id"]].iloc[0]
    current_provider = appt_row["provider_id"]
    time_slot = appt_row["time_slot"]

    pool = cand[
        (cand["area"] == patient["area"]) &
        (cand["available_today"] == True) &
        (cand["remaining_capacity"] > 0) &
        (cand["provider_id"] != current_provider)
    ].copy()

    if pool.empty:
        return None if top_n == 1 else []

    current_spec_series = cand.loc[cand["provider_id"] == current_provider, "specialization"]
    current_spec = current_spec_series.iloc[0] if not current_spec_series.empty else None

    # distance from the currently-assigned provider, for an honest "vs today" comparison
    current_row = cand[cand["provider_id"] == current_provider]
    current_dist = None
    if not current_row.empty and pd.notna(current_row.iloc[0]["latitude"]):
        current_dist = haversine_km(
            patient["latitude"], patient["longitude"],
            current_row.iloc[0]["latitude"], current_row.iloc[0]["longitude"],
        )

    scored = []
    for _, row in pool.iterrows():
        continuity = (patient["patient_id"], row["provider_id"]) in history
        continuity_score = 1.0 if continuity else 0.0

        if pd.notna(row["latitude"]):
            dist_km = haversine_km(patient["latitude"], patient["longitude"], row["latitude"], row["longitude"])
            proximity_score = max(0.0, 1 - dist_km / 25)  # 0 pts at 25km+, linear to 25km
        else:
            dist_km, proximity_score = None, 0.3  # no history to infer a centroid from — neutral, not zero

        capacity_score = min(1.0, row["remaining_capacity"] / max(row["daily_capacity"], 1))

        per_slot_cap = max(1, round(row["daily_capacity"] / 3))
        slot_assigned = slot_load_today.get((row["provider_id"], time_slot), 0)
        slot_room = per_slot_cap - slot_assigned
        schedule_fit_score = 1.0 if slot_room > 0 else (0.4 if row["remaining_capacity"] > 0 else 0.0)

        service_fit_score = 1.0 if row["specialization"] == current_spec else 0.4  # soft — see module docstring

        utilization_penalty = max(0.0, row["utilization_today"] - 0.7) / 0.3  # ramps up past 70% utilized

        total = (
            WEIGHTS["continuity"] * continuity_score
            + WEIGHTS["proximity"] * proximity_score
            + WEIGHTS["capacity"] * capacity_score
            + WEIGHTS["schedule_fit"] * schedule_fit_score
            + WEIGHTS["service_fit"] * service_fit_score
            - UTILIZATION_PENALTY_WEIGHT * utilization_penalty
        )

        reasons = []
        if dist_km is not None:
            reasons.append(f"{round(dist_km, 1)} km from patient (inferred)")
        reasons.append(f"{int(row['remaining_capacity'])} slot(s) free today")
        if slot_room > 0:
            reasons.append(f"room in the same {time_slot.lower()} slot")
        if continuity:
            reasons.append("has treated this patient before")
        if row["specialization"] == current_spec:
            reasons.append("same specialization as current provider")
        if utilization_penalty > 0:
            reasons.append(f"already {int(row['utilization_today']*100)}% booked today")

        scored.append({
            "provider_id": row["provider_id"],
            "employment_type": row["employment_type"],
            "area": row["area"],
            "remaining_capacity": int(row["remaining_capacity"]),
            "distance_km": round(dist_km, 1) if dist_km is not None else None,
            "distance_vs_current_km": (
                round(dist_km - current_dist, 1) if dist_km is not None and current_dist is not None else None
            ),
            "continuity": continuity,
            "specialization_match": bool(row["specialization"] == current_spec),
            "same_slot_available": bool(slot_room > 0),
            "utilization_today_pct": round(float(row["utilization_today"]) * 100, 0),
            "score": round(total, 1),
            "reasons": reasons,
        })

    scored.sort(key=lambda r: -r["score"])

    if top_n == 1:
        return scored[0]
    return scored[:top_n]


if __name__ == "__main__":
    TODAY = "2026-08-29"
    ctx = build_candidates(TODAY)
    cand = ctx["cand"]
    print(f"Providers available on {TODAY} with spare capacity:")
    print(cand[(cand["available_today"]) & (cand["remaining_capacity"] > 0)]
          [["provider_id", "area", "specialization", "remaining_capacity", "utilization_today"]].to_string(index=False))

    # worked example: score every eligible candidate for a real flagged appointment.
    # Not every appointment has an eligible candidate pool (small city/day
    # combinations run out of spare capacity) — search for one that does, so
    # this always prints a meaningful comparison rather than "none found".
    appts = ctx["appts"]
    todays_appts = appts[appts["date"] == TODAY]["appointment_id"].tolist()
    sample, ranked = None, []
    for aid in todays_appts:
        ranked = recommend(aid, TODAY, ctx, top_n=5)
        if len(ranked) >= 2:  # prefer an example that shows an actual trade-off between candidates
            sample = aid
            break
    if sample is None:
        for aid in todays_appts:
            ranked = recommend(aid, TODAY, ctx, top_n=5)
            if ranked:
                sample = aid
                break
    print(f"\nRanked recovery candidates for {sample}:")
    if not ranked:
        print("  (no eligible candidates found for any appointment today)")
    for r in ranked:
        print(f"  {r['provider_id']}  score={r['score']:<6} " + " | ".join(r["reasons"]))
