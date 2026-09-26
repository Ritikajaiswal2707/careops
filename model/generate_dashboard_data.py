"""
Builds the dashboard's data feed from the actual trained model + real operational
data, instead of a hand-typed dict. This is the fix for the two biggest gaps in
the original prototype:
  1. The risk list was hardcoded -> now it's the model's real output on a
     specific simulated "today".
  2. The cascade list was two invented examples -> now it's every real
     appointment on that day where operational.csv's own
     delay_cascade_triggered flag is True.

Run this whenever you want to refresh dashboard/index.html with a new "today".
"""
import json
import pandas as pd
from disruption_model import model, features, df, DATA_DIR
from communication_intelligence import extract_intent
from capacity_recovery import build_candidates, recommend
from reschedule_agent import propose_reschedule

# "Today" = the last date actually present in the appointment data. In a real
# deployment this would be appointments not yet completed; here we simulate it
# by scoring that day's appointments using only pre-visit features (the model
# never sees status/outcome), which is honest to how it would run live.
TODAY = df["date"].max()

today_df = df[df["date"] == TODAY].copy()
today_df["risk_proba"] = model.predict_proba(today_df[features])[:, 1]


def assign_percentile_tiers(scores):
    """
    Capacity-aware, rank-based triage: top 10% of *today's* visits by
    predicted risk -> High, next 20% -> Medium, remaining 70% -> Low.

    This replaces a fixed probability cutoff (>=0.5 High, >=0.3 Medium),
    which silently stopped matching the README/dashboard copy once the
    leakage-fixed model's probabilities stopped reaching 0.5 at all --
    every day showed 0 High regardless of how risky the day actually was.
    Ranking within the day keeps the flagged list a fixed, reviewable
    fraction of a coordinator's caseload no matter how the model's raw
    probabilities are distributed.
    """
    n = len(scores)
    # rank 0 = highest risk. method="first" breaks ties by original order
    # so every visit gets a distinct rank (no ties inflating a tier).
    ranks = scores.rank(ascending=False, method="first") - 1
    high_cut = n * 0.10
    medium_cut = n * 0.30  # top 30% total = High + Medium
    return ranks.apply(lambda r: "High" if r < high_cut else ("Medium" if r < medium_cut else "Low"))


def explain(row):
    # Uses the same as-of-appointment-date features the model was actually
    # scored on (see disruption_model.py) — not the static patient-level
    # summaries, so the explanation matches what the model knew at the time.
    reasons = []
    if row["new_patient_to_date"] == 1:
        reasons.append("First visit for this patient")
    if row["previous_no_shows_to_date"] >= 2:
        reasons.append(f"{int(row['previous_no_shows_to_date'])} prior no-shows before this visit")
    if row["response_rate_to_date"] < 0.5:
        reasons.append("Low message response rate so far")
    if row["travel_distance_km"] > 12:
        reasons.append(f"{row['travel_distance_km']}km from clinician")
    if row["is_evening"] == 1:
        reasons.append("Evening slot")
    if not reasons:
        reasons.append("No single dominant factor; borderline risk")
    return reasons


def suggest_action(row, t, signal=None):
    # A direct patient signal overrides the generic risk-based action —
    # this is the start of the Next-Best-Action logic the model should feed into.
    if signal:
        if signal["intent"] == "Reschedule":
            day = f" to {signal['preferred_day']}" if signal["preferred_day"] else ""
            return f"Patient requested reschedule{day} — confirm new slot"
        if signal["intent"] == "Cancel":
            return "Patient requested cancellation — offer next available slot"
        if signal["intent"] == "Confirm":
            return "Patient confirmed — no action needed"
    if t == "High" and row["travel_distance_km"] > 15:
        return "Reassign to nearer clinician if available"
    if row["response_rate_to_date"] < 0.5:
        return "Send confirmation + backup contact request"
    if row["previous_no_shows_to_date"] >= 3:
        return "Call to confirm 24h ahead"
    return "Send confirmation + backup contact request"


today_df["tier"] = assign_percentile_tiers(today_df["risk_proba"])

summary = {
    "total": int(len(today_df)),
    "high": int((today_df["tier"] == "High").sum()),
    "medium": int((today_df["tier"] == "Medium").sum()),
    "low": int((today_df["tier"] == "Low").sum()),
}

comms = pd.read_csv(f"{DATA_DIR}/communications.csv")
comms["timestamp"] = pd.to_datetime(comms["timestamp"])
latest_msg = comms.sort_values("timestamp").groupby("appointment_id").tail(1).set_index("appointment_id")

TODAY_STR = str(TODAY.date())
recovery_ctx = build_candidates(TODAY_STR)

flagged = []
ranked = today_df.sort_values("risk_proba", ascending=False)
for _, row in ranked[ranked["tier"] != "Low"].iterrows():
    signal = None
    patient_signal_out = None
    if row["appointment_id"] in latest_msg.index:
        msg_row = latest_msg.loc[row["appointment_id"]]
        if isinstance(msg_row["message"], str) and msg_row["message"].strip():
            signal = extract_intent(msg_row["message"])
            patient_signal_out = {
                "channel": msg_row["channel"],
                "message": msg_row["message"],
                **signal,
            }

    action = suggest_action(row, row["tier"], signal)
    item = {
        "id": row["appointment_id"],
        "time": row["time_slot"],
        "service": row["service_type"],
        "risk": round(float(row["risk_proba"]), 2),
        "tier": row["tier"],
        "reasons": explain(row),
        "action": action,
    }
    if patient_signal_out:
        item["patientSignal"] = patient_signal_out
        if signal["intent"] == "Reschedule":
            agent_result = propose_reschedule(row["appointment_id"], msg_row["message"])
            item["agentTrace"] = agent_result["trace"]
            if agent_result["proposal"]:
                item["rescheduleProposal"] = agent_result["proposal"]  # structured, for the dashboard's simulated-execution flow
                item["action"] = (f"Agent proposed: move to {agent_result['proposal']['new_date']} "
                                  f"with {agent_result['proposal']['provider_id']} — awaiting confirmation")
            else:
                item["action"] = "Reschedule requested — no matching slot found, needs manual follow-up"

    # capacity recovery: only where the action is actually a reassignment.
    # recommend() now returns a scored, ranked candidate with a "reasons"
    # breakdown (continuity, proximity, schedule fit, utilization) instead of
    # just a filtered pick — see capacity_recovery.py.
    if "Reassign" in action:
        rec = recommend(row["appointment_id"], TODAY_STR, recovery_ctx)
        if rec:
            item["recommendedReassignment"] = rec
            item["action"] = f"Reassign to {rec['provider_id']} — " + ", ".join(rec["reasons"])
        else:
            item["action"] = "Reassign needed — no covering provider with spare capacity today"

    flagged.append(item)

# ---- cascade detection: real flag from operational.csv, not invented examples ----
providers = pd.read_csv(f"{DATA_DIR}/providers.csv")
cascade_today = today_df[today_df["delay_cascade_triggered"] == True].merge(
    providers, on="provider_id", how="left"
)

cascades = []
for _, row in cascade_today.iterrows():
    c = {
        "id": row["appointment_id"],
        "service": row["service_type"],
        "slot": row["time_slot"],
        "provider": f"{row['provider_id']} ({row['employment_type']})",
        "delay": int(row["delay_minutes"]),
        "buffer": int(row["buffer_minutes_needed"]),
        "notified": bool(row["downstream_notified"]),
        "locGap": bool(row["travel_distance_km"] > 15 and not row["downstream_notified"]),
    }
    if not row["downstream_notified"]:
        rec = recommend(row["appointment_id"], TODAY_STR, recovery_ctx)
        if rec:
            c["recovery"] = f"Backup available: {rec['provider_id']} — " + ", ".join(rec["reasons"])
        else:
            c["recovery"] = "No backup provider with spare capacity today — needs manual coordinator call"
    cascades.append(c)

output = {
    "today": str(TODAY.date()),
    "summary": summary,
    "flagged": flagged,
    "cascades": cascades,
}

with open("dashboard_data.json", "w") as f:
    json.dump(output, f, indent=2)

# ---- inject the freshly generated output straight into the dashboard HTML ----
# Previously this JSON was hand-pasted into a `const DATA = {...};` line in
# dashboard/index.html as a separate manual step — which quietly meant "the
# dashboard reads this generated output; nothing in it is hand-typed" wasn't
# actually true end-to-end. This closes that gap: the HTML's data line is now
# rewritten by this script every run, so there is no manual copy step at all.
DASHBOARD_HTML = "../dashboard/index.html"
with open(DASHBOARD_HTML, "r", encoding="utf-8") as f:
    html_lines = f.readlines()

data_line_idx = next(
    (i for i, line in enumerate(html_lines) if line.strip().startswith("const DATA =")), None
)
if data_line_idx is None:
    raise RuntimeError(f"Could not find 'const DATA =' line in {DASHBOARD_HTML} to update.")

html_lines[data_line_idx] = f"const DATA = {json.dumps(output)};\n"
with open(DASHBOARD_HTML, "w", encoding="utf-8") as f:
    f.writelines(html_lines)

print(f"today = {TODAY.date()}")
print(f"summary = {summary}")
print(f"flagged appointments = {len(flagged)}")
print(f"real cascades detected = {len(cascades)}")
print("wrote model/dashboard_data.json")
print(f"updated {DASHBOARD_HTML} (line {data_line_idx + 1}) with the same output — no manual copy step")
