# AI Care Operations Copilot

A portfolio project exploring how AI can predict, explain, and help recover from disruptions in home healthcare delivery — with a specific focus on the operational realities of India's home-care market: contractual/gig service providers with variable day-to-day availability, elderly patients who often can't self-report precise location, and delay cascades caused by traffic, weather, or overruns.

**This is a PM portfolio project.** All data is synthetic/simulated. It exists to demonstrate product thinking — problem framing, prioritization, tradeoff decisions, and AI-product judgment — not to claim production-grade engineering or real-world validated outcomes.

## Structure

- `data/` — synthetic 6-table dataset (providers, patients, appointments, operational, communications, availability) modeling a home-care operation across 5 Indian cities, 20 clinicians, 2,000 patients, 10,000 appointments. `availability.csv` covers Jun 1 – Oct 28 (extended 60 days past the original Aug 29 cutoff — see note below)
- `model/disruption_model.py` — logistic regression predicting visit disruption risk (time-based train/test split: train Jun-Jul, test Aug), plus a rule-based plain-language explanation layer and threshold/precision-recall tradeoff analysis. **Fits and reports both a leaky and a leakage-fixed version side by side** (see "A leakage bug, found and fixed" below) — the fixed version is what the dashboard actually runs on
- `model/communication_intelligence.py` — rule/keyword-based extractor that turns raw patient messages (`communications.csv`, mixed English/Hinglish) into structured signal: intent, preferred day, urgency, reason. Not a live LLM call — no API key is wired into this environment. Agrees with the dataset's own intent labels 100% of the time, but that's measured against its own training templates — see `model/llm_vs_baseline_eval.py` below for what actually happens on unseen phrasing
- `model/llm_vs_baseline_eval.py` — the real generalization test the 100%-agreement number can't provide: a 103-message held-out set, hand-labeled with the *full* gold structure (intent, temporal signal, reason — not just intent), written independently of `communications.csv`'s 10 templates (typos, Hindi in Devanagari script, code-switching, sarcasm, compound requests, indirect phrasing, no keyword overlap in several cases on purpose). **The rule-based extractor scores 44.7% intent accuracy (macro F1 0.57), 91.3% temporal-field accuracy, 98.1% reason accuracy, and abstains (predicts "Unclear") on 65% of messages** — it's a lookup table for phrasing that resembles its 10 training templates, and its single biggest failure mode is casual/minimal confirmations ("ok", "k", "yep all good") that don't contain any of its exact `CONFIRM_WORDS` phrases. The script also calls the Anthropic API for a head-to-head structured-JSON LLM comparison (same 5 metrics, plus JSON validity and cost/latency per message) when `ANTHROPIC_API_KEY` is set — not set in this environment, so that side hasn't been run; no LLM number is claimed or estimated here
- `model/capacity_recovery.py` — scores every eligible candidate provider on a weighted **Recovery Score** (continuity + proximity + remaining capacity + same-time-slot fit + service fit, minus a utilization penalty) and returns the ranked list with a plain-language "why" for each — a trade-off, not just a filtered pool. See "The Recovery Score" below
- `model/reschedule_agent.py` — the understand → check → propose loop for reschedule requests: takes the extracted intent, resolves a requested day (or searches the next few days) against real availability/capacity via `capacity_recovery.recommend()` (the same Recovery Score used for same-day recovery, not a separate heuristic), and proposes a specific new provider + date. Drives a real `agent_state_machine.RescheduleCase` (see below) — a live call honestly stops at PROPOSED, since there's no reply channel to actually get PATIENT_CONFIRMED or DECLINED back. Does not write to `appointments.csv`. Distinguishes "no provider had capacity" from "no availability data exists for that date"; with `availability.csv` now extended through Oct 28, this boundary case is rare rather than something every reschedule demo runs into
- `model/agent_state_machine.py` — the reassignment/reschedule lifecycle as an enforced state machine, not five printed strings in a row: `PENDING -> PROPOSED -> PATIENT_CONFIRMED -> BOOKED -> PROVIDER_NOTIFIED -> COMPLETED`, plus the failure branch `PROPOSED -> DECLINED -> SEARCH_ALTERNATIVE -> PROPOSED (next candidate) | ESCALATED`. Every transition is checked against an explicit allow-list — an illegal one (e.g. booking a case that was never confirmed) raises `InvalidTransition` instead of silently succeeding. Still local/in-memory, no backend, per the original scope — `python3 agent_state_machine.py` demos all four paths (happy path, decline-and-retry, candidates-exhausted, and a rejected illegal transition) with synthetic patient responses, since this dataset has no live back-and-forth to draw a real one from
- `model/economics_simulation.py` — modeled before/after impact of using the risk model to prioritize coordinator outreach on the August test period. Two inputs (intervention success rate, revenue per completed visit) are labeled placeholders, not measured figures — this is a simulation, not a result
- `model/generate_dashboard_data.py` — runs the full pipeline (risk model → communication signal → reassignment recommendation), writes `dashboard_data.json`, **and rewrites the `const DATA = {...}` line in `dashboard/index.html` directly** — there is no manual copy-paste step between the pipeline and the dashboard anymore
- `dashboard/index.html` — an interactive "Today's Care Operations" view: capacity-aware risk triage, patient-message signal on flagged visits, and a delay/cascade view with real detected cascades and, where a gap exists, a real recovery candidate or an honest "no coverage today". **"Simulate approval" now drives a simulated execution chain** (message drafted → slot reserved → provider notified → family notified → marked recovered), stepped through in real time using the actual recommendation/proposal data from the Python pipeline — not a boolean flip. It's still simulated (no real WhatsApp send, no real write to a scheduling system — there isn't one in this environment), but the UI now behaves like the product it's describing instead of a static mockup. State is in-memory per browser tab; refreshing resets it, same as re-running the pipeline would

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

The original capacity-recovery logic was a filter: same city, available, spare capacity, not the current provider — then one soft tie-breaker (specialization, compared against the *current* provider rather than what the visit actually required). A filter can't explain a trade-off between two acceptable candidates, and comparing to the current provider's specialization isn't the same question as "can this candidate actually deliver the requested service?". `capacity_recovery.py` now enforces service fit as a **hard eligibility filter** via an explicit `service_type → specialization` compatibility mapping, then scores every remaining eligible candidate:

```
Recovery Score =
    25 × continuity        (has this provider treated this patient before?)
  + 25 × proximity          (distance from the provider's inferred operating area to the patient)
  + 15 × remaining capacity (headroom today, as a fraction of daily_capacity)
  + 15 × schedule fit       (is there room in the SAME time-of-day slot, not just somewhere in the day?)
  +  5 × service fit        (tie-breaker among already-eligible candidates: primary vs. an acceptable secondary spec)
  - 10 × utilization penalty (ramps up past 70% booked — protects against pushing an already-full provider into a delay cascade)
```

Same-day recovery and rescheduling (`reschedule_agent.py`) now go through this one engine — reschedule proposals are ranked by the same Recovery Score, not a separate "pick whoever has the most spare capacity today" heuristic.

Worked example, one real flagged appointment on 2026-08-29 (`python3 capacity_recovery.py`):

| Candidate | Score | Why |
|---|---|---|
| PR019 | 47.8 | 8.5 km from patient (inferred), 3 slots free, room in the same morning slot, Physiotherapy — primary fit for Physiotherapy Session |

Two data limitations, carried over honestly from the original version:
- `providers.csv` has no lat/long, only `area` (city). "Proximity" here uses each provider's own historical patient locations (mean lat/long of patients they've actually served, from `appointments.csv`) as an inferred operating centroid — a real, data-derived signal, but an approximation, not GPS ground truth. Recovery decisions for a given date now only draw on appointments strictly before that date, for both this centroid and continuity history — the original version used the full history regardless of date, a real temporal leak.
- `specialization` vs. how providers are actually assigned to `service_type` in the data still shows close to no relationship (~20-23% for every specialization, regardless of service type) — this mapping is imposed as a business rule, not learned from the data.

**A real finding from enforcing this properly:** with the hard service-fit filter in place, most flagged reassignment cases in this 20-provider synthetic dataset now come back with **zero** eligible candidates — `providers.csv` has only 1-2 providers per (area, specialization) combination, so requiring "same area + right specialization + available + spare capacity" at once is rarely satisfiable. The earlier, looser version was recommending reassignments that weren't actually valid; the honest version instead surfaces a real capacity-planning gap (too few backup providers per specialty per area) rather than papering over it with a plausible-looking but wrong recommendation. Worth a line in the case study either way it's framed.

## Known limitations (intentional, and part of the case study)

- The model over-indexes on first-time-patient status as a risk signal, even after the leakage fix — flagged here as a fairness/design concern requiring mitigation before any real use, not something smoothed over
- Risk tiering is directionally reliable in aggregate but noisy on any single simulated day, given the model's modest predictive strength (ROC-AUC ≈ 0.58 on the leakage-fixed version; this is honestly reported, not inflated)
- The pipeline is reproducible, not live: `generate_dashboard_data.py` is run manually to produce a fresh snapshot. There is no backend serving live predictions on request, and no real actions are sent (no WhatsApp, no scheduling-system writes) — the dashboard's "Approve" button changes local UI state only
- Communication intelligence is rule-based, not an LLM call, and generalizes poorly: 100% agreement against its own training labels, but only **44.7% intent accuracy (macro F1 0.57)** on the 103-message held-out set in `model/llm_vs_baseline_eval.py` — it's overfit to its 10 training templates, not a system that understands language, and abstains on 65% of held-out messages rather than guessing wrong (a safer failure mode than it sounds, but still means most messages need a human to actually read them). That script also scores temporal-field accuracy (91.3%), reason accuracy (98.1%), and is wired to call an LLM for a real head-to-head comparison — including JSON validity and cost/latency per message — but no `ANTHROPIC_API_KEY` is set in this environment, so the LLM side hasn't actually been run
- The economics module is a labeled simulation with placeholder assumptions, not a validated business result — no real intervention was run and no real outcome was logged
- `availability.csv`'s extension past Aug 29 is generated, not observed: each provider's future availability is drawn using that same provider's own historical availability rate (e.g. contractual providers ~50-60%, full-time providers ~90%+), not real future scheduling data

## Full case study

The complete product narrative — problem framing, autonomy-level framework, prioritization decisions, and simulated impact — lives in the accompanying case study deck (linked from the portfolio).

## Experiment design

`EXPERIMENT_DESIGN.md` specs the RCT that would replace the placeholder assumptions in `economics_simulation.py` with a measured result — sample size, guardrail metrics, and what a null result would mean. Not run; this is the design, not a result.
