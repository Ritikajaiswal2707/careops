"""Bounded, tool-using recovery agent for the CareOps synthetic demo.

The agent orchestrates validated data lookup, message interpretation, recovery
search and a human-approved recommendation. It does not book appointments or
send messages. All bundled records are synthetic.
"""
from __future__ import annotations

import os
from typing import Callable

import pandas as pd

from agent_state_machine import RescheduleCase
from capacity_recovery import (
    InvalidDateError,
    UnknownAppointmentError,
    build_candidates,
    recommend,
)
from hybrid_extraction import extract_intent_hybrid, default_llm_call
from reschedule_agent import resolve_candidate_dates

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "..", "data")
AGENT_VERSION = "0.1.0"


def _load_data():
    return {
        "appointments": pd.read_csv(os.path.join(DATA_DIR, "appointments.csv")),
        "patients": pd.read_csv(os.path.join(DATA_DIR, "patients.csv")),
        "availability": pd.read_csv(os.path.join(DATA_DIR, "availability.csv")),
    }


def lookup_appointment(appointment_id: str, data: dict | None = None) -> dict:
    """Tool: validate the appointment and return minimal synthetic context."""
    data = data or _load_data()
    matches = data["appointments"][data["appointments"]["appointment_id"] == appointment_id]
    if matches.empty:
        raise UnknownAppointmentError("appointment_id not found in synthetic appointments")
    appt = matches.iloc[0]
    patients = data["patients"][data["patients"]["patient_id"] == appt["patient_id"]]
    if patients.empty:
        raise UnknownAppointmentError("appointment's patient is missing from synthetic patient data")
    patient = patients.iloc[0]
    return {
        "appointment_id": str(appt["appointment_id"]),
        "patient_id": str(appt["patient_id"]),
        "original_date": str(appt["date"]),
        "time_slot": str(appt["time_slot"]),
        "service_type": str(appt["service_type"]),
        "area": str(patient["area"]),
    }


def interpret_disruption(message: str, llm_call: Callable | None = default_llm_call) -> dict:
    """Tool: extract a structured intent; abstain/escalate rather than guess."""
    return extract_intent_hybrid(message, llm_call=llm_call)


def search_recovery_options(
    appointment_id: str,
    appointment_context: dict,
    signal: dict,
    data: dict | None = None,
    *,
    candidate_builder: Callable = build_candidates,
    recommender: Callable = recommend,
) -> dict:
    """Tool: rank feasible candidates on requested dates using hard constraints."""
    data = data or _load_data()
    original_date = pd.to_datetime(appointment_context["original_date"])
    candidate_dates = resolve_candidate_dates(original_date, signal)
    checked_dates = []

    for candidate_date in candidate_dates:
        date_str = str(candidate_date.date())
        ctx = candidate_builder(date_str)
        availability_has_date = (data["availability"]["date"] == date_str).any()
        has_available_provider = bool(ctx["cand"]["available_today"].any())
        ranked = recommender(
            appointment_id,
            date_str,
            ctx,
            service_type=appointment_context["service_type"],
            top_n=3,
        ) or []
        checked_dates.append({
            "date": date_str,
            "availability_data_present": bool(availability_has_date or has_available_provider),
            "eligible_candidate_count": len(ranked),
        })
        if ranked:
            case = RescheduleCase(appointment_id, ranked)
            best = case.propose_next()
            return {
                "checked_dates": checked_dates,
                "candidates": ranked,
                "proposal": {
                    "appointment_id": appointment_id,
                    "new_date": date_str,
                    "provider_id": best["provider_id"],
                    "area": best["area"],
                    "remaining_capacity": best["remaining_capacity"],
                    "recovery_score": best["score"],
                    "reasons": best["reasons"],
                    "state": case.state.value,
                    "approval_required": True,
                },
            }

    return {"checked_dates": checked_dates, "candidates": [], "proposal": None}


def run_recovery_agent(
    appointment_id: str,
    message: str,
    *,
    llm_call: Callable | None = default_llm_call,
    data: dict | None = None,
    candidate_builder: Callable = build_candidates,
    recommender: Callable = recommend,
) -> dict:
    """Run a bounded multi-step workflow and return auditable tool traces."""
    data = data or _load_data()
    tool_trace = []

    def record(name: str, status: str, detail: str):
        tool_trace.append({"tool": name, "status": status, "detail": detail})

    try:
        context = lookup_appointment(appointment_id, data)
        record("lookup_appointment", "success", "Appointment and patient context validated against synthetic records.")
    except UnknownAppointmentError:
        record("lookup_appointment", "error", "Appointment or linked patient not found.")
        raise

    signal = interpret_disruption(message, llm_call=llm_call)
    record("interpret_disruption", "success" if not signal.get("escalate_to_human") else "escalation",
           f"Intent={signal.get('intent')}; source={signal.get('source')}.")

    base = {
        "agent_version": AGENT_VERSION,
        "appointment_id": appointment_id,
        "simulated": True,
        "tool_trace": tool_trace,
        "intent": signal.get("intent"),
        "intent_source": signal.get("source"),
        "escalate_to_human": bool(signal.get("escalate_to_human")),
        "proposal": None,
    }

    if signal.get("escalate_to_human"):
        base.update({"status": "needs_human_review", "reason": "Message intent could not be safely determined."})
        return base

    if signal.get("intent") != "Reschedule":
        base.update({"status": "unsupported_intent", "reason": "This agent currently handles rescheduling requests only."})
        return base

    try:
        result = search_recovery_options(
            appointment_id,
            context,
            signal,
            data,
            candidate_builder=candidate_builder,
            recommender=recommender,
        )
    except InvalidDateError as exc:
        record("search_recovery_options", "error", "Requested date fell outside supported availability rules.")
        base.update({"status": "needs_human_review", "escalate_to_human": True,
                     "reason": str(exc)})
        return base
    except Exception:
        # Fail closed: tool/data errors must not produce a guessed recovery plan.
        # Do not return raw exception details to the API caller.
        record("search_recovery_options", "error", "Recovery tool failed; no action was proposed.")
        base.update({
            "status": "needs_human_review",
            "escalate_to_human": True,
            "reason": "Recovery options could not be verified. Coordinator review is required.",
        })
        return base

    record("search_recovery_options", "success" if result["proposal"] else "no_feasible_option",
           f"Checked {len(result['checked_dates'])} candidate date(s); found {len(result['candidates'])} ranked candidate(s).")
    base.update({
        "status": "awaiting_coordinator_approval" if result["proposal"] else "no_feasible_option",
        "checked_dates": result["checked_dates"],
        "candidates": result["candidates"],
        "proposal": result["proposal"],
        "approval_required": True if result["proposal"] else False,
        "reason": None if result["proposal"] else "No eligible replacement found in the search window; coordinator follow-up is required.",
    })
    return base
