# AI Care Operations Copilot

A portfolio project exploring how AI can predict, explain, and help recover from disruptions in home healthcare delivery — with a specific focus on the operational realities of India's home-care market: contractual/gig service providers with variable day-to-day availability, elderly patients who often can't self-report precise location, and delay cascades caused by traffic, weather, or overruns.

**This is a PM portfolio project.** All data is synthetic/simulated. It exists to demonstrate product thinking — problem framing, prioritization, tradeoff decisions, and AI-product judgment — not to claim production-grade engineering or real-world validated outcomes.

## Structure

- `data/` — synthetic 6-table dataset (providers, patients, appointments, operational, communications, availability) modeling a home-care operation across 5 Indian cities, 20 clinicians, 2,000 patients, 10,000 appointments. `availability.csv` covers Jun 1 – Oct 28 (extended 60 days past the original Aug 29 cutoff — see note below)
- `model/disruption_model.py` — logistic regression predicting visit disruption risk (time-based train/test split: train Jun-Jul, test Aug), plus a rule-based plain-language explanation layer and threshold/precision-recall tradeoff analysis. **Fits and reports both a leaky and a leakage-fixed version side by side** (see "A leakage bug, found and fixed" below) — the fixed version is what the dashboard actually runs on
- `model/communication_intelligence.py` — rule/keyword-based extractor that turns raw patient messages (`communications.csv`, mixed English/Hinglish) into structured signal: intent, preferred day, urgency, reason. Not a live LLM call — no API key is wired into this environment — but it operates on raw text and generalizes; validated at 100% agreement against the dataset's own intent labels (see limitation below — that number is weaker evidence than it sounds)
- `model/capacity_recovery.py` — scores every eligible candidate provider on a weighted **Recovery Score** (continuity + proximity + remaining capacity + same-time-slot fit + service fit, minus a utilization penalty) and returns the ranked list with a plain-language "why" for each — a trade-off, not just a filtered pool. See "The Recovery Score" below
- `model/reschedule_agent.py` — the understand → check → propose loop for reschedule requests: takes the extracted intent, resolves a requested day (or searches the next few days) against real availability/capacity, and proposes a specific new provider + date. Does not write to `appointments.csv` and does not get a real "yes" back — there's no live channel to confirm with. Distinguishes "no provider had capacity" from "no availability data exists for that date"; with `availability.csv` now extended through Oct 28, this boundary case is rare rather than something every reschedule demo runs into
- `model/economics_simulation.py` — modeled before/after impact of using the risk model to prioritize coordinator outreach on the August test period. Two inputs (intervention success rate, revenue per completed visit) are labeled placeholders, not measured figures — this is a simulation, not a result
- `model/generate_dashboard_data.py` — runs the full pipeline (risk model → communication signal → reassignment recommendation), writes `dashboard_data.json`, **and rewrites the `const DATA = {...}` line in `dashboard/index.html` directly** — there is no manual copy-paste step between the pipeline and the dashboard anymore
- `dashboard/index.html` — an interactive "Today's Care Operations" view: capacity-aware risk triage, patient-message signal on flagged visits, and a delay/cascade view with real detected cascades and, where a gap exists, a real recovery candidate or an honest "no coverage today". **"Approve" now drives a simulated execution chain** (message drafted → slot reserved → provider notified → family notified → marked recovered), stepped through in real time using the actual recommendation/proposal data from the Python pipeline — not a boolean flip. It's still simulated (no real WhatsApp send, no real write to a scheduling system — there isn't one in this environment), but the UI now behaves like the product it's describing instead of a static mockup. State is in-memory per browser tab; refreshing resets it, same as re-running the pipeline would

## A leakage bug, found and fixed

The original model scored every appointment using `previous_no_shows` and `communication_response_rate` pulled straight from `patients.csv` — static, patient-level, end-of-dataset summaries. A June appointment was effectively scored using no-show counts that include no-shows that hadn't happened yet at prediction time. `new_patient` had the same problem (a fixed per-patient flag, not "is this literally their first visit").

`disruption_model.py` now computes rolling versions of all three — `previous_no_shows_to_date`, `response_rate_to_date`, `new_patient_to_date` — using only appointments/communications for that patient strictly before the appointment being scored, and fits both versions on the same time-based split so the effect is visible instead of silently swapped out:

| | Leaky (original) | Fixed (as-of-date) |
|---|---|---|
| ROC-AUC | 0.658 | 0.58 |
| Top 20% risk band precision | 41.8% | 33.6% |
| Top 20% risk band recall | 32.6% | 26.1% |
| `new_patient` coefficient | 0.861 | 0.10 |

The drop is the point: the leaky model was partly learning from information it wouldn't have at deployment time, and a large share of that came through the `new_patient` flag. 0.58 is a weaker but honest number. The product argument doesn't change — it's still a triage signal for scarce coordinator attention, not an autonomous decision-maker — but it now rests on a number that would hold up if someone re-ran the split correctly.

## The Recovery Score

The original capacity-recovery logic was a filter: same city, available, spare capacity, not the current provider — then one soft tie-breaker (specialization). A filter can't explain a trade-off between two acceptable candidates. `capacity_recovery.py` now scores every eligible candidate:

```
Recovery Score =
    25 × continuity        (has this provider treated this patient before?)
  + 25 × proximity          (distance from the provider's inferred operating area to the patient)
  + 15 × remaining capacity (headroom today, as a fraction of daily_capacity)
  + 15 × schedule fit       (is there room in the SAME time-of-day slot, not just somewhere in the day?)
  +  5 × service fit        (soft, low-weight — see note below)
  - 10 × utilization penalty (ramps up past 70% booked — protects against pushing an already-full provider into a delay cascade)
```

Worked example, one real flagged appointment on 2026-08-29 (`python3 capacity_recovery.py`):

| Candidate | Score | Why |
|---|---|---|
| PR016 | 47.1 | 7.9 km from patient, 1 slot free, **has treated this patient before**, already 85% booked today |
| PR019 | 44.8 | 8.5 km from patient, 3 slots free, room in the same morning slot |

PR016 wins narrowly despite being nearly fully booked, because continuity of care is weighted more heavily than open capacity — a real trade-off the score can show, not just a winner it can't explain.

Two data limitations, carried over honestly from the original version:
- `providers.csv` has no lat/long, only `area` (city). "Proximity" here uses each provider's own historical patient locations (mean lat/long of patients they've actually served, from `appointments.csv`) as an inferred operating centroid — a real, data-derived signal, but an approximation, not GPS ground truth.
- `specialization` vs. how providers are actually assigned to `service_type` in the data still shows close to no relationship (~22% ± 2pp for every specialization, regardless of service type). "Service fit" stays a low weight in the score for this reason — the data doesn't support leaning on it, so the score doesn't.

## Known limitations (intentional, and part of the case study)

- The model over-indexes on first-time-patient status as a risk signal, even after the leakage fix — flagged here as a fairness/design concern requiring mitigation before any real use, not something smoothed over
- Risk tiering is directionally reliable in aggregate but noisy on any single simulated day, given the model's modest predictive strength (ROC-AUC ≈ 0.58 on the leakage-fixed version; this is honestly reported, not inflated)
- The pipeline is reproducible, not live: `generate_dashboard_data.py` is run manually to produce a fresh snapshot. There is no backend serving live predictions on request, and no real actions are sent (no WhatsApp, no scheduling-system writes) — the dashboard's "Approve" button changes local UI state only
- Communication intelligence is rule-based, not an LLM call. The 100%-agreement number in `communication_intelligence.py` is also weaker evidence than it looks: the source CSV has only 10 unique messages, and `extracted_intent` labels are already in the dataset the rules were built against — so it demonstrates that the rules reproduce their own training labels, not that the extractor generalizes to unseen phrasing. A real evaluation needs a held-out, manually labeled set of 100–200 diverse English/Hinglish messages, scored on intent F1, reason-extraction accuracy, and hallucination rate against an actual LLM call — not built yet
- The economics module is a labeled simulation with placeholder assumptions, not a validated business result — no real intervention was run and no real outcome was logged
- `availability.csv`'s extension past Aug 29 is generated, not observed: each provider's future availability is drawn using that same provider's own historical availability rate (e.g. contractual providers ~50-60%, full-time providers ~90%+), not real future scheduling data

## Full case study

The complete product narrative — problem framing, autonomy-level framework, prioritization decisions, and simulated impact — lives in the accompanying case study deck (linked from the portfolio).

## Experiment design

`EXPERIMENT_DESIGN.md` specs the RCT that would replace the placeholder assumptions in `economics_simulation.py` with a measured result — sample size, guardrail metrics, and what a null result would mean. Not run; this is the design, not a result.
