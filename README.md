# AI Care Operations Copilot

A portfolio project exploring how AI can predict, explain, and help recover from disruptions in home healthcare delivery — with a specific focus on the operational realities of India's home-care market: contractual/gig service providers with variable day-to-day availability, elderly patients who often can't self-report precise location, and delay cascades caused by traffic, weather, or overruns.

**This is a PM portfolio project.** All data is synthetic/simulated. It exists to demonstrate product thinking — problem framing, prioritization, tradeoff decisions, and AI-product judgment — not to claim production-grade engineering or real-world validated outcomes.

## Structure

- `data/` — synthetic 6-table dataset (providers, patients, appointments, operational, communications, availability) modeling a home-care operation across 5 Indian cities, 20 clinicians, 2,000 patients, 10,000 appointments
- `model/disruption_model.py` — logistic regression predicting visit disruption risk (time-based train/test split: train Jun-Jul, test Aug), plus a rule-based plain-language explanation layer and threshold/precision-recall tradeoff analysis
- `model/communication_intelligence.py` — rule/keyword-based extractor that turns raw patient messages (`communications.csv`, mixed English/Hinglish) into structured signal: intent, preferred day, urgency, reason. Not a live LLM call — no API key is wired into this environment — but it operates on raw text and generalizes; validated at 100% agreement against the dataset's own intent labels
- `model/capacity_recovery.py` — for appointments flagged as needing reassignment, searches `providers.csv` + `availability.csv` for a real candidate provider (same city, available that day, spare daily capacity). Note: checking `providers.csv`'s `specialization` field against how providers are actually assigned in `appointments.csv` shows almost no relationship, so specialization is used as a soft tie-breaker here, not a hard filter
- `model/reschedule_agent.py` — the understand → check → propose loop for reschedule requests: takes the extracted intent, resolves a requested day (or searches the next few days) against real availability/capacity, and proposes a specific new provider + date. Does not write to `appointments.csv` and does not get a real "yes" back — there's no live channel to confirm with. Explicitly distinguishes "no provider had capacity" from "no availability data exists for that date" (the dataset only covers Jun 1 - Aug 29, so proposals dated after Aug 29 can't be confirmed either way — this shows up honestly in the two real cases from Aug 29's flagged list)
- `model/economics_simulation.py` — modeled before/after impact of using the risk model to prioritize coordinator outreach on the August test period. Two inputs (intervention success rate, revenue per completed visit) are labeled placeholders, not measured figures — this is a simulation, not a result
- `model/generate_dashboard_data.py` — runs the full pipeline (risk model → communication signal → reassignment recommendation) and writes the dashboard's data. The dashboard reads this generated output; nothing in it is hand-typed
- `dashboard/index.html` — an interactive "Today's Care Operations" view: capacity-aware risk triage, patient-message signal on flagged visits, and a delay/cascade view with real detected cascades and, where a gap exists, a real recovery candidate or an honest "no coverage today"

## Known limitations (intentional, and part of the case study)

- The model over-indexes on first-time-patient status as a risk signal — flagged here as a fairness/design concern requiring mitigation before any real use, not something smoothed over
- Risk tiering is directionally reliable in aggregate but noisy on any single simulated day, given the model's modest predictive strength (ROC-AUC ≈ 0.66; this is honestly reported, not inflated)
- The pipeline is reproducible, not live: `generate_dashboard_data.py` is run manually to produce a fresh snapshot. There is no backend serving live predictions on request, and no real actions are sent (no WhatsApp, no scheduling-system writes) — the dashboard's "Approve" button changes local UI state only
- Communication intelligence is rule-based, not an LLM call, for the reason stated above
- The economics module is a labeled simulation with placeholder assumptions, not a validated business result — no real intervention was run and no real outcome was logged

## Full case study

The complete product narrative — problem framing, autonomy-level framework, prioritization decisions, and simulated impact — lives in the accompanying case study deck (linked from the portfolio).

## Experiment design

`EXPERIMENT_DESIGN.md` specs the RCT that would replace the placeholder assumptions in `economics_simulation.py` with a measured result — sample size, guardrail metrics, and what a null result would mean. Not run; this is the design, not a result.
