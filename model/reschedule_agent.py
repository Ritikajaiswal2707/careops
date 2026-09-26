"""
Module 4: Reschedule agent.

Takes a patient message → extracted intent (communication_intelligence) →
checks real availability/capacity for a matching slot (extending
capacity_recovery's logic to an arbitrary future date, not just "today") →
proposes a specific new booking.

This is the "agentic" step the critique described: understand → check
constraints → propose → (would send back to patient to confirm). There is no
live chat here to actually get a "yes" back, and no write to appointments.csv
— the proposal is the deliverable, and executing it is a one-line change once
a real booking system exists to write to.
"""
import pandas as pd
from datetime import timedelta
from capacity_recovery import build_candidates
from communication_intelligence import extract_intent

DATA_DIR = "../data"
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def next_weekday_on_or_after(date, weekday_name: str):
    target = WEEKDAYS.index(weekday_name)
    days_ahead = (target - date.weekday()) % 7
    days_ahead = days_ahead or 7  # always move forward, never same day
    return date + timedelta(days=days_ahead)


def propose_reschedule(appointment_id: str, message: str):
    appts = pd.read_csv(f"{DATA_DIR}/appointments.csv")
    patients = pd.read_csv(f"{DATA_DIR}/patients.csv")
    availability = pd.read_csv(f"{DATA_DIR}/availability.csv")

    appt = appts[appts["appointment_id"] == appointment_id].iloc[0]
    patient = patients[patients["patient_id"] == appt["patient_id"]].iloc[0]
    orig_date = pd.to_datetime(appt["date"])

    signal = extract_intent(message)
    trace = [f"Patient ({appt['patient_id']}, {patient['area']}): \"{message}\"",
             f"Extracted: intent={signal['intent']}, preferred_day={signal['preferred_day']}, "
             f"urgency={signal['urgency']}, reason={signal['reason']}"]

    if signal["intent"] != "Reschedule":
        trace.append("Not a reschedule request — routed back to standard action logic.")
        return {"trace": trace, "proposal": None}

    # candidate dates: the requested weekday if given, else the next 3 days
    if signal["preferred_day"]:
        candidate_dates = [next_weekday_on_or_after(orig_date, signal["preferred_day"])]
    else:
        candidate_dates = [orig_date + timedelta(days=d) for d in (1, 2, 3)]

    for cand_date in candidate_dates:
        date_str = str(cand_date.date())
        ctx = build_candidates(date_str)
        cand = ctx["cand"]
        has_availability_data = cand["available_today"].any() or (availability["date"] == date_str).any()
        pool = cand[
            (cand["area"] == patient["area"]) &
            (cand["available_today"] == True) &
            (cand["remaining_capacity"] > 0)
        ]
        if not pool.empty:
            best = pool.sort_values("remaining_capacity", ascending=False).iloc[0]
            trace.append(f"Checked availability.csv for {date_str}: "
                         f"{len(pool)} provider(s) in {patient['area']} available with spare capacity.")
            proposal = {
                "new_date": date_str,
                "provider_id": best["provider_id"],
                "area": best["area"],
                "remaining_capacity": int(best["remaining_capacity"]),
            }
            trace.append(f"Proposed: move to {date_str} with {best['provider_id']} "
                        f"({int(best['remaining_capacity'])} slots free that day).")
            trace.append("Awaiting patient confirmation — not written to appointments.csv "
                         "(no live booking system to write to in this environment).")
            return {"trace": trace, "proposal": proposal}
        elif not has_availability_data:
            trace.append(f"Checked {date_str}: no availability.csv data exists for this date "
                        f"(outside the dataset's Jun 1 - Aug 29 range) — cannot confirm, not the same as 'unavailable'.")
        else:
            trace.append(f"Checked {date_str}: no provider in {patient['area']} available with spare capacity.")

    trace.append("No confirmable slot found in the search window — needs manual coordinator follow-up.")
    return {"trace": trace, "proposal": None}


if __name__ == "__main__":
    cases = [
        ("APT009761", "Kal thoda late ho jayega, Saturday kar sakte ho?"),
        ("APT009737", "Doctor visit hai usi din, reschedule possible?"),
    ]
    for appt_id, msg in cases:
        print(f"\n=== {appt_id} ===")
        result = propose_reschedule(appt_id, msg)
        for line in result["trace"]:
            print(" -", line)
