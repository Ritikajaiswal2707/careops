"""
Module 4: Reschedule agent.

Takes a patient message → extracted intent (communication_intelligence) →
ranks real candidates for a matching slot on an arbitrary future date using
capacity_recovery.recommend() — the SAME weighted Recovery Score used for
same-day capacity recovery, not a separate simplistic heuristic — → proposes
a specific new booking.

This is the "agentic" step the critique described: understand → check
constraints → propose → (would send back to patient to confirm). Proposing
now drives a real agent_state_machine.RescheduleCase (PENDING -> PROPOSED),
not just a printed line — see agent_state_machine.py for the full lifecycle
and its enforced transitions. There is no live chat here to actually get a
"yes" back, so a real call from this module honestly stops at PROPOSED; no
write to appointments.csv either — the proposal is the deliverable, and
executing it is a one-line change once a real booking system exists to
write to.
"""
import pandas as pd
from datetime import timedelta
from capacity_recovery import build_candidates, recommend
from communication_intelligence import extract_intent
from agent_state_machine import RescheduleCase

DATA_DIR = "../data"
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def next_weekday_on_or_after(date, weekday_name: str):
    target = WEEKDAYS.index(weekday_name)
    days_ahead = (target - date.weekday()) % 7
    days_ahead = days_ahead or 7  # always move forward, never same day
    return date + timedelta(days=days_ahead)


def resolve_candidate_dates(orig_date, signal: dict):
    """
    Turns the extracted temporal signal (communication_intelligence.parse_temporal)
    into an ordered list of candidate dates to check availability against.

    Replaces the old logic, which only understood a literal weekday name
    and otherwise silently defaulted to "the next 1-3 days" -- so a
    message like "Can we move to next week?" (no weekday named) was
    misread as "tomorrow-ish" and produced a next-day proposal, the
    opposite of what was asked.

    An explicit day name is checked before "tomorrow"/"weekend", because
    a message can legitimately contain both without the relative word
    being about the reschedule target at all -- e.g. "Kal thoda late ho
    jayega, Saturday kar sakte ho?" ("I'll be a bit late tomorrow, can
    we do Saturday?") uses "kal" (tomorrow) to describe today's delay,
    not the day being requested. The named day, when present, is the
    stronger and unambiguous signal.
    """
    if signal.get("offset_days"):
        return [orig_date + timedelta(days=signal["offset_days"])]

    if signal.get("preferred_day"):
        target = next_weekday_on_or_after(orig_date, signal["preferred_day"])
        if signal.get("next_week"):
            target += timedelta(days=7)  # "next <weekday>" -> the following week's occurrence
        return [target]

    if signal.get("relative_day") == "tomorrow":
        return [orig_date + timedelta(days=1)]

    if signal.get("relative_day") == "weekend":
        sat = next_weekday_on_or_after(orig_date, "Saturday")
        return [sat, sat + timedelta(days=1)]  # Saturday, then Sunday

    if signal.get("next_week"):
        # "next week" / "sometime next week" with no day named -- offer a
        # spread of weekdays in the following calendar week rather than
        # guessing a single day.
        this_monday = orig_date - timedelta(days=orig_date.weekday())
        next_monday = this_monday + timedelta(days=7)
        return [next_monday + timedelta(days=d) for d in (0, 2, 4)]  # Mon, Wed, Fri

    # No usable temporal signal at all -- fall back to the next few days.
    return [orig_date + timedelta(days=d) for d in (1, 2, 3)]


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
             f"next_week={signal['next_week']}, relative_day={signal['relative_day']}, "
             f"offset_days={signal['offset_days']}, urgency={signal['urgency']}, reason={signal['reason']}"]

    if signal["intent"] != "Reschedule":
        trace.append("Not a reschedule request — routed back to standard action logic.")
        return {"trace": trace, "proposal": None}

    candidate_dates = resolve_candidate_dates(orig_date, signal)

    for cand_date in candidate_dates:
        date_str = str(cand_date.date())
        ctx = build_candidates(date_str)
        cand = ctx["cand"]
        has_availability_data = cand["available_today"].any() or (availability["date"] == date_str).any()

        # Same decision engine as same-day capacity recovery — ranked by the
        # weighted Recovery Score (continuity, proximity, capacity, schedule
        # fit, service fit), not a separate "pick whoever has the most spare
        # capacity" heuristic. Known simplification carried over from that
        # engine: it always excludes the appointment's currently-assigned
        # provider from the candidate pool, so it won't propose "same
        # provider, new date" even when that would in fact be available and
        # is usually the best outcome for the patient — recovering that case
        # would mean checking the original provider's own availability on
        # date_str before falling back to this ranking.
        ranked = recommend(appointment_id, date_str, ctx, service_type=appt["service_type"], top_n=3)

        if ranked:
            case = RescheduleCase(appointment_id, ranked)
            best = case.propose_next()  # PENDING -> PROPOSED, real state-machine transition
            trace.append(f"Checked {date_str} via the unified Recovery Score engine: "
                         f"{len(ranked)} eligible candidate(s) in {patient['area']}.")
            proposal = {
                "new_date": date_str,
                "provider_id": best["provider_id"],
                "area": best["area"],
                "remaining_capacity": best["remaining_capacity"],
                "recovery_score": best["score"],
                "reasons": best["reasons"],
                "state": case.state.value,
            }
            trace.append(f"Proposed: move to {date_str} with {best['provider_id']} "
                        f"(Recovery Score {best['score']}: " + "; ".join(best["reasons"]) + ").")
            trace.append(f"State: {' -> '.join(case.history_trace())}. Case is now PROPOSED and stops "
                         "here honestly — there is no live reply channel in this environment to actually "
                         "receive PATIENT_CONFIRMED or DECLINED; advancing further needs a real channel to "
                         "get the patient's answer from, not something to simulate as if it were live.")
            return {"trace": trace, "proposal": proposal}
        elif not has_availability_data:
            trace.append(f"Checked {date_str}: no availability.csv data exists for this date "
                        f"(outside the dataset's Jun 1 - Aug 29 range) — cannot confirm, not the same as 'unavailable'.")
        else:
            trace.append(f"Checked {date_str} via the unified Recovery Score engine: "
                        f"no eligible candidate found in {patient['area']}.")

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
