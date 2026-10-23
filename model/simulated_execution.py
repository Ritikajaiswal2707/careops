"""Safe, idempotent simulated execution for approved CareOps recovery cases.

This module only records a simulated recovery in SQLite. It never books in a
real scheduling system and never contacts patients or providers.
"""
from __future__ import annotations

from typing import Callable

from approval_store import (
    CaseConflictError,
    CaseNotFoundError,
    get_case,
    record_simulated_execution,
)
from capacity_recovery import InvalidDateError, build_candidates, recommend


class RevalidationError(ValueError):
    """The previously proposed recovery is no longer eligible."""


def revalidate_proposal(proposal: dict) -> dict:
    """Re-check the exact proposed provider/date against current synthetic data."""
    appointment_id = str(proposal.get("appointment_id", ""))
    target_date = str(proposal.get("new_date", ""))
    provider_id = str(proposal.get("provider_id", ""))
    if not appointment_id or not target_date or not provider_id:
        raise RevalidationError("Proposal is missing required recovery fields.")

    try:
        context = build_candidates(target_date)
        candidates = recommend(appointment_id, target_date, context, top_n=100)
    except (InvalidDateError, FileNotFoundError):
        raise
    except Exception as exc:
        # Do not expose raw internal errors to the API caller.
        raise RevalidationError("Recovery eligibility could not be verified.") from exc

    match = next((candidate for candidate in (candidates or [])
                  if str(candidate.get("provider_id")) == provider_id), None)
    if match is None:
        raise RevalidationError(
            "The proposed provider is no longer eligible or has no capacity in the required slot."
        )
    return {
        "provider_id": provider_id,
        "target_date": target_date,
        "appointment_id": appointment_id,
        "eligibility_revalidated": True,
        "same_slot_available": bool(match.get("same_slot_available")),
        "service_fit": match.get("service_fit"),
        "recovery_score_at_revalidation": match.get("score"),
        "execution_mode": "simulation_only",
    }


def execute_approved_case(
    case_id: str,
    *,
    validator: Callable[[dict], dict] = revalidate_proposal,
) -> dict:
    """Revalidate and record one simulated execution for an approved case."""
    case = get_case(case_id)
    if case.get("status") != "approved":
        raise CaseConflictError("Case must be approved before simulated execution.")
    if case.get("simulated_execution"):
        return case

    validated = validator(case["proposal"])
    return record_simulated_execution(case_id, validated)
