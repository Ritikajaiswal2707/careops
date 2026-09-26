# Experiment design: does model-prioritized outreach actually reduce disruptions?

This is the piece the rest of the repo can't provide on its own. Everything in
`model/` shows what the system *would* do; none of it shows what happens when
a real patient gets a real message. This document specs a test that would
close that gap — it hasn't been run, and no result is claimed here.

## Hypothesis

Sending proactive outreach (confirmation request / reschedule offer) to
appointments the model flags in its top 20% risk band reduces the disruption
rate (no-show + cancellation) for that group, relative to no outreach.

## Design

Randomized controlled trial, appointment-level randomization (not
patient-level — a patient can appear in either arm on different visits,
since risk is driven by per-appointment context like lead time and slot,
not just patient history).

- **Population:** all appointments landing in the top 20% by predicted risk
  (using the existing `disruption_model.py` scoring)
- **Control:** current process, no model-driven outreach
- **Treatment:** the action `generate_dashboard_data.py` already recommends
  for that appointment (confirmation request, reschedule offer, etc.),
  actually sent
- **Randomize at:** appointment creation time, so assignment can't be
  contaminated by coordinators self-selecting who to contact

## Sample size

Using this dataset's own real baseline — August test-period disruption rate
of **25.7%** (811/3,155) — to detect a drop to 20% (a 22% relative
reduction, which is roughly what the top-20%-precision numbers in
`economics_simulation.py` would imply if the intervention worked):

**~850 appointments per arm** (α=0.05, power=0.80, two-proportion test).
At current volume (~3,300 appointments/month in this data), that's roughly
2-3 weeks of the top-20% flagged population — achievable in a single
operating month.

## Primary metric

Disruption rate (no-show + cancelled) at the appointment level, treatment
vs. control, at the visit's scheduled date.

## Guardrail metrics (should not get worse)

- Coordinator time spent per flagged appointment (the model's operational
  cost) — track against `coordinator_min_per_contact` in
  `economics_simulation.py`
- Patient complaint / opt-out rate from outreach messages
- Completion rate for the *non-flagged* 80% (make sure attention isn't
  being pulled away from appointments that needed it for other reasons)

## What this replaces once it runs

- `INTERVENTION_SUCCESS_RATE = 0.35` in `economics_simulation.py` is
  currently a placeholder. The trial's actual (treatment disruption rate)
  vs (control disruption rate) replaces it with a real number, and every
  downstream figure in that file (recovered visits, coordinator hours,
  contribution) becomes a measured result instead of a modeled one.
- A null result (no significant difference) is a genuinely useful outcome
  too — it would mean the risk model is fine but the *action* isn't moving
  behavior, which points at Module 2/4 (communication intelligence, the
  reschedule agent) as the next place to invest, not the risk model itself.
