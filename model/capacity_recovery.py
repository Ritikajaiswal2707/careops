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

v3 change (this pass): two scheduling simplifications flagged as gaps, fixed
here rather than left as documented limitations:

  1. Same-provider rescheduling. recommend() unconditionally excluded the
     appointment's currently-assigned provider from the candidate pool -- a
     correct rule when recovering *today's* visit (that provider is the one
     running late), but wrong for a reschedule to a *different* date, where
     "same provider, new date" is usually the best outcome for the patient
     and was never even considered. recommend() now only excludes the
     current provider when target_date matches the appointment's original
     date; a reschedule to any other date lets the current provider compete
     like any other candidate (their own continuity/proximity usually wins,
     since they already know the patient).

  2. Slot-level capacity across recommendations in the same run. Every call
     to recommend() scored candidates off a snapshot of remaining_capacity
     and per-slot load taken once, at build_candidates() time -- so nothing
     stopped two different flagged appointments in the same run from both
     being recommended the same provider for the same time slot on the same
     day, silently oversubscribing them past what the dashboard itself was
     showing as "N slots free." commit_recommendation() now exists to
     decrement a candidate's remaining_capacity and per-slot load in the
     shared ctx immediately after a recommendation is accepted, so the next
     recommend() call in the same run sees the update.
     generate_dashboard_data.py calls it after every accepted
     reassignment/recovery.

Two data limitations, carried over honestly from v1 and still true here:
  - providers.csv has no lat/long, only `area` (city). There's no ground-truth
    provider location to compute real distance from, so "proximity" here uses
    each provider's OWN historical patient locations (mean lat/long of
    patients they've actually served in appointments.csv) as an inferred
    operating centroid. That's a real, data-derived location — not the
    patient's own city centroid — but it's an approximation, not a GPS fact.
  - checking `specialization` against how providers are actually assigned to
    service_types in appointments.csv shows close to no relationship (~20-23%
    for every specialization, regardless of service_type). So this mapping
    is imposed explicitly, in SERVICE_COMPATIBILITY below, as a HARD
    eligibility filter -- "can this candidate deliver the requested
    service?" -- rather than inferred from the data. The service_fit weight
    in the score only breaks ties among already-eligible candidates
    (primary vs. an acceptable secondary specialization).

Also fixed here: recovery decisions for target_date are built only from
appointments strictly BEFORE target_date (continuity history, provider
location centroids). The original version used the full appointment history
regardless of date, which meant a recovery decision for e.g. Aug 10 could be
informed by relationships that only show up in Aug 20's data -- a real
information leak a target_date-scoped decision shouldn't have.
"""
import math
import os
import pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "..", "data")

WEIGHTS = {
    "continuity": 25,
    "proximity": 25,
    "capacity": 15,
    "schedule_fit": 15,
    "service_fit": 5,
}
UTILIZATION_PENALTY_WEIGHT = 10  # subtracted, scaled by how over/near capacity the provider already is

# Which provider specialization(s) can actually deliver a given service_type.
# This is a business rule, not something learned from the data: a crosstab of
# service_type against the specialization of the provider actually assigned
# (appointments.csv) shows every specialization at ~20-23% of every
# service_type -- i.e. the synthetic assignment history carries no real
# signal on this. So this mapping is imposed as ground truth, and used below
# as a HARD eligibility filter (a candidate that can't deliver the requested
# service is not a candidate at all), not a soft tie-breaker.
# First entry in each list = primary/preferred specialization for that
# service; any additional entries are acceptable but scored slightly lower.
SERVICE_COMPATIBILITY = {
    "Physiotherapy Session": ["Physiotherapy"],
    "Nursing Visit": ["General Nursing"],
    "Diabetic Care Visit": ["Diabetic Care"],
    "Post-Op Care": ["Post-Surgery Care"],
    "Vitals Check": ["General Nursing", "Elder Care"],
    # Not in the original spec -- added for completeness since it's a real
    # service_type in the data. Treated as a General Nursing task.
    "Wound Dressing": ["General Nursing"],
}


SLOT_ORDER = ["Morning", "Afternoon", "Evening"]


def slot_capacities(daily_capacity: int) -> dict:
    """
    Splits a provider's whole-day capacity across the three time slots so the
    three numbers actually sum back to daily_capacity.

    v3 fix: the previous version applied round(daily_capacity / 3) as a
    single per-slot number for all three slots. Checked against the data:
    daily_capacity in this dataset is only ever 4, 5, 6, 7 or 8 -- and for
    every value except 6, round(x/3) applied three times doesn't sum back to
    x. capacity=4 -> 1+1+1=3 (a real slot silently disappears, provider
    looks 25% less available than they are); capacity=5 -> 2+2+2=6 (a slot
    invented out of nowhere, risking a real over-booking the system
    wouldn't catch); same under/over pattern at 7 and 8. That's not a
    rounding nitpick -- it's 17 of the 20 providers in providers.csv having
    a slot-capacity total that doesn't match their own daily_capacity.
    Floor + distribute the remainder across SLOT_ORDER instead, so the three
    slots always sum to exactly daily_capacity.
    """
    base, remainder = divmod(int(daily_capacity), 3)
    caps = {slot: base for slot in SLOT_ORDER}
    for slot in SLOT_ORDER[:remainder]:
        caps[slot] += 1
    return caps


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
    # split is still the model (see slot_capacities() -- checked against the
    # actual per-provider time_slot mix in appointments.csv, which is
    # ~33/34/33% and flat within noise for all 20 providers, so "even" isn't
    # a shortcut here, it's what the data itself supports). What's fixed
    # (see slot_capacities()) is that the split now sums exactly to
    # daily_capacity instead of losing or inventing a slot to rounding.
    # Plain dict (not a pandas Series) so commit_recommendation() can add new
    # keys as recommendations are accepted during the run.
    slot_load_today = today_appts.groupby(["provider_id", "time_slot"]).size().to_dict()

    # Strictly-historical slice for anything that infers a relationship or
    # location: a recovery decision made for target_date must not be
    # informed by appointments that happen AFTER it (temporal leakage).
    # Date strings are ISO (YYYY-MM-DD), so lexicographic "<" is chronological.
    # today_appts (== target_date, used above for load/capacity) is fine to
    # use as-is, since today's own assignments are known at decision time --
    # it's only future dates that must stay invisible.
    history_appts = appts[appts["date"] < target_date]

    cand = providers.copy()
    cand["available_today"] = cand["provider_id"].map(avail_today).fillna(False)
    cand["assigned_today"] = cand["provider_id"].map(load_today).fillna(0).astype(int)
    cand["remaining_capacity"] = cand["daily_capacity"] - cand["assigned_today"]
    cand["utilization_today"] = (cand["assigned_today"] / cand["daily_capacity"]).clip(upper=2.0)

    centroids = _provider_centroids(history_appts, patients)
    cand = cand.merge(centroids, on="provider_id", how="left")

    return {
        "cand": cand,
        "appts": appts,
        "patients": patients,
        "slot_load_today": slot_load_today,
        "history": _patient_provider_history(history_appts),
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

    # The actual eligibility question is "can this candidate deliver the
    # requested service?", not "does this candidate share a specialization
    # label with whoever is currently assigned". Fall back to the
    # appointment's own service_type when the caller doesn't pass one.
    service_type = service_type or appt_row["service_type"]
    compatible_specs = SERVICE_COMPATIBILITY.get(service_type, [])

    # Only exclude the currently-assigned provider when this is a same-day
    # recovery (they're the one running late today). A reschedule to a
    # different date is a separate, legitimate availability check -- the
    # current provider may well be free that day and is usually the best
    # outcome for the patient, so they compete like any other candidate.
    same_day = target_date == appt_row["date"]

    base_mask = (
        (cand["area"] == patient["area"]) &
        (cand["available_today"] == True) &
        (cand["remaining_capacity"] > 0)
    )
    if same_day:
        base_mask = base_mask & (cand["provider_id"] != current_provider)
    if compatible_specs:
        pool = cand[base_mask & cand["specialization"].isin(compatible_specs)].copy()
    else:
        # service_type not in the mapping (shouldn't happen for the 6 known
        # service_types, but don't silently return zero candidates over a
        # data gap) -- fall back to no hard service-fit filter.
        pool = cand[base_mask].copy()

    if pool.empty:
        return None if top_n == 1 else []

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

        per_slot_cap = slot_capacities(row["daily_capacity"])[time_slot]
        slot_assigned = slot_load_today.get((row["provider_id"], time_slot), 0)
        slot_room = per_slot_cap - slot_assigned
        schedule_fit_score = 1.0 if slot_room > 0 else (0.4 if row["remaining_capacity"] > 0 else 0.0)

        if row["specialization"] in compatible_specs:
            # already passed the hard eligibility filter above; this only
            # breaks ties among eligible candidates (primary spec vs. an
            # acceptable secondary one, e.g. Vitals Check by Elder Care).
            service_fit_score = 1.0 if row["specialization"] == compatible_specs[0] else 0.7
        else:
            service_fit_score = 1.0  # no mapping existed for this service_type; filter was a no-op

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
        if row["provider_id"] == current_provider:
            reasons.append("this is the patient's current provider, free on this date")
        elif dist_km is not None:
            reasons.append(f"{round(dist_km, 1)} km from patient (inferred)")
        reasons.append(f"{int(row['remaining_capacity'])} slot(s) free today")
        if slot_room > 0:
            reasons.append(f"room in the same {time_slot.lower()} slot")
        if continuity and row["provider_id"] != current_provider:
            reasons.append("has treated this patient before")
        reasons.append(
            f"{row['specialization']} — {'primary' if row['specialization'] == (compatible_specs[0] if compatible_specs else None) else 'compatible'} fit for {service_type}"
        )
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
            "is_current_provider": bool(row["provider_id"] == current_provider),
            "specialization": row["specialization"],
            "service_fit": "primary" if compatible_specs and row["specialization"] == compatible_specs[0] else "compatible",
            "same_slot_available": bool(slot_room > 0),
            "utilization_today_pct": round(float(row["utilization_today"]) * 100, 0),
            "score": round(total, 1),
            "reasons": reasons,
        })

    scored.sort(key=lambda r: -r["score"])

    if top_n == 1:
        return scored[0]
    return scored[:top_n]


def commit_recommendation(ctx, provider_id: str, time_slot: str):
    """
    Marks a recommended slot as taken, in the shared ctx, immediately after
    it's accepted -- so the NEXT recommend() call in the same run (a
    different flagged appointment, a different cascade) sees this provider
    with one less remaining_capacity and one more slot_load_today entry,
    instead of scoring off the same start-of-run snapshot every time.
    Without this, two unrelated appointments in the same run could both be
    told "PR019 has room" for the same time slot -- individually correct
    against the snapshot, jointly an oversubscription the dashboard would
    never surface. Mutates ctx["cand"] and ctx["slot_load_today"] in place;
    call it once per accepted recommendation, right after using it.
    """
    cand = ctx["cand"]
    mask = cand["provider_id"] == provider_id
    cand.loc[mask, "assigned_today"] += 1
    cand.loc[mask, "remaining_capacity"] -= 1
    cand.loc[mask, "utilization_today"] = (
        cand.loc[mask, "assigned_today"] / cand.loc[mask, "daily_capacity"]
    ).clip(upper=2.0)

    key = (provider_id, time_slot)
    ctx["slot_load_today"][key] = ctx["slot_load_today"].get(key, 0) + 1


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
