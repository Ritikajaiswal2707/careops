import pandas as pd

from capacity_recovery import recommend


def test_recommendation_excludes_provider_when_target_slot_is_full():
    # A different-day reschedule: both providers are available and have daily
    # capacity, but one has no room left in the requested Morning slot.
    appointments = pd.DataFrame([{
        "appointment_id": "APT000001",
        "patient_id": "PAT000001",
        "provider_id": "PR_CURRENT",
        "date": "2026-08-01",
        "time_slot": "Morning",
        "service_type": "Nursing Visit",
    }])
    patients = pd.DataFrame([{
        "patient_id": "PAT000001", "area": "North",
        "latitude": 12.0, "longitude": 77.0,
    }])
    candidates = pd.DataFrame([
        {
            "provider_id": "PR_FULL", "area": "North", "specialization": "General Nursing",
            "employment_type": "Full-time", "available_today": True,
            "daily_capacity": 4, "assigned_today": 2, "remaining_capacity": 2,
            "utilization_today": 0.5, "latitude": 12.01, "longitude": 77.01,
        },
        {
            "provider_id": "PR_OPEN", "area": "North", "specialization": "General Nursing",
            "employment_type": "Full-time", "available_today": True,
            "daily_capacity": 4, "assigned_today": 1, "remaining_capacity": 3,
            "utilization_today": 0.25, "latitude": 12.02, "longitude": 77.02,
        },
    ])
    context = {
        "cand": candidates,
        "appts": appointments,
        "patients": patients,
        "slot_load_today": {("PR_FULL", "Morning"): 2, ("PR_OPEN", "Morning"): 1},
        "history": set(),
    }

    result = recommend("APT000001", "2026-08-02", context, service_type="Nursing Visit", top_n=3)

    assert result
    assert all(item["provider_id"] != "PR_FULL" for item in result)
    assert all(item["same_slot_available"] is True for item in result)
    assert [item["provider_id"] for item in result] == ["PR_OPEN"]
