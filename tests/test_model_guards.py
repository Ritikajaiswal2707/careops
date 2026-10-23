from datetime import date
from pathlib import Path
import json

import pandas as pd
import pytest

from communication_intelligence import extract_intent
from hybrid_extraction import _valid_schema, extract_intent_hybrid
from capacity_recovery import InvalidDateError, UnknownAppointmentError, validate_target_date
from reschedule_agent import resolve_candidate_dates
from agent_state_machine import RescheduleCase

ROOT = Path(__file__).resolve().parents[1]

VALID_LLM = {
    "intent": "Reschedule",
    "cancel_current": False,
    "preferred_day": "Saturday",
    "next_week": False,
    "relative_day": "tomorrow",
    "offset_days": None,
    "reason": None,
}


def test_live_llm_schema_requires_all_fields_and_types():
    assert _valid_schema(VALID_LLM)
    assert not _valid_schema({k: v for k, v in VALID_LLM.items() if k != "cancel_current"})
    assert not _valid_schema({**VALID_LLM, "cancel_current": "false"})
    assert not _valid_schema({**VALID_LLM, "next_week": 1})
    assert not _valid_schema({**VALID_LLM, "offset_days": True})
    assert not _valid_schema({**VALID_LLM, "offset_days": -1})
    assert not _valid_schema({**VALID_LLM, "offset_days": 61})
    assert not _valid_schema({**VALID_LLM, "relative_day": "next month"})
    assert not _valid_schema({**VALID_LLM, "extra": "not in contract"})


def test_ambiguous_message_escalates_when_llm_disabled():
    output = extract_intent_hybrid("Maybe, I will see", llm_call=None)
    assert output["source"] == "escalation"
    assert output["escalate_to_human"] is True


def test_zero_day_offset_is_a_real_temporal_signal():
    signal = extract_intent("Please reschedule after 0 days")
    assert signal["offset_days"] == 0
    assert signal["intent"] == "Reschedule"


def test_reschedule_zero_offset_maps_to_original_date():
    original = pd.Timestamp("2026-08-29")
    dates = resolve_candidate_dates(original, {
        "offset_days": 0, "preferred_day": None, "relative_day": None, "next_week": False
    })
    assert len(dates) == 1
    assert pd.Timestamp(dates[0]).date() == original.date()


def test_invalid_offsets_escalation_range_is_rejected():
    with pytest.raises(InvalidDateError):
        resolve_candidate_dates(pd.Timestamp("2026-08-29"), {
            "offset_days": 61, "preferred_day": None, "relative_day": None, "next_week": False
        })


def test_target_date_must_be_iso_and_within_availability_horizon():
    assert validate_target_date("2026-08-29") == date(2026, 8, 29)
    for invalid in ["29-08-2026", "2026-02-30", "2027-01-01", "2026/08/29"]:
        with pytest.raises(InvalidDateError):
            validate_target_date(invalid)


def test_state_trace_assertion_checks_state_history_not_explanation_text():
    case = RescheduleCase("APT_TEST", [{"provider_id": "PR019", "score": 47.8}])
    case.propose_next()
    lines = ["State: " + " -> ".join(case.history_trace()) + ". Case stops here; a real reply would be required for PATIENT_CONFIRMED."]
    state_line = next(line for line in lines if line.startswith("State:"))
    state_history = state_line.split(". Case stops here", 1)[0]
    assert state_history.startswith("State: PENDING -> PROPOSED")
    assert "PATIENT_CONFIRMED" not in state_history


def test_economic_artifacts_retain_verified_simulation_results():
    economics = json.loads((ROOT / "model/economics_summary.json").read_text(encoding="utf-8"))
    outcomes = json.loads((ROOT / "model/intervention_outcomes.json").read_text(encoding="utf-8"))
    assert economics["total_appointments"] == 3155
    assert economics["modeled_after_intervention"]["appointments_flagged_for_outreach"] == 631
    assert economics["modeled_after_intervention"]["true_disruptions_among_flagged"] == 212
    assert economics["breakeven_intervention_success_rate_at_base_top_k"] == pytest.approx(0.149)
    assert outcomes["bottom_up_simulated"]["recovered_visits"] == 16
    assert outcomes["bottom_up_simulated"]["net_value"] == -12850
    assert outcomes["top_down_baseline"]["recovered_visits"] == 74
    assert outcomes["top_down_baseline"]["net_value"] == 33970


def test_llm_evaluation_artifacts_keep_methodology_caveat():
    direct = json.loads((ROOT / "model/llm_vs_baseline_results.json").read_text(encoding="utf-8"))
    hybrid = json.loads((ROOT / "model/hybrid_eval_results.json").read_text(encoding="utf-8"))
    assert direct["llm"]["metrics"]["n"] == 103
    assert direct["llm"]["metrics"]["intent_accuracy"] == 1.0
    assert direct["llm"]["metrics"]["avg_latency_ms"] is None
    assert "No live Anthropic API call" in direct["llm"]["metrics"]["methodology_note"]
    assert hybrid["hybrid"]["metrics"]["intent_accuracy"] == pytest.approx(0.971)
    assert hybrid["hybrid"]["metrics"]["avg_latency_ms"] is None


def test_experiment_design_documents_cluster_caveat_and_correct_baseline():
    text = (ROOT / "EXPERIMENT_DESIGN.md").read_text(encoding="utf-8")
    assert "33.6% flagged-group disruption rate" in text
    assert "122 patients have more than one flagged appointment" in text.lower()
    assert "not run" in text.lower()


def test_reschedule_parser_accepts_natural_timing_paraphrases():
    for message in [
        "Could we move the visit to another time?",
        "Please change the timing of the nurse appointment.",
        "Can we do another date instead?",
    ]:
        assert extract_intent(message)["intent"] == "Reschedule"


def test_confirmation_parser_accepts_home_availability_phrases():
    for message in [
        "We'll be home at the scheduled time.",
        "We can make that time.",
        "We can attend as scheduled.",
    ]:
        assert extract_intent(message)["intent"] == "Confirm"


def test_uncertain_future_change_does_not_become_cancellation():
    for message in [
        "I might need to change the visit, but I will let you know.",
        "I am unsure whether we can make it; I will confirm later.",
    ]:
        result = extract_intent(message)
        assert result["intent"] == "Unclear"
        assert result["cancel_current"] is False
