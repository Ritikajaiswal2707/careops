# CareOps Recovery Agent — Implementation Notes

## Status

Implemented as a bounded, tool-using prototype in `model/recovery_agent.py`, exposed at `POST /api/agent/run` and through the dashboard's **Run recovery agent** action.

## Current workflow

1. `lookup_appointment`: validate the appointment and linked synthetic patient record.
2. `interpret_disruption`: run the existing rules-first, LLM-fallback extractor. Unresolved messages are escalated.
3. `search_recovery_options`: resolve candidate dates, query the existing capacity-aware recovery engine, and rank eligible candidates.
4. Return a `PROPOSED` recommendation that explicitly requires coordinator approval.

The response includes a structured `tool_trace`, `agent_version`, status, intent source, candidate dates, and an optional proposal. The request message itself is not copied into the tool trace.

## Safety and scope boundaries

- All data is synthetic.
- The agent currently handles rescheduling intents only; other intents are returned as unsupported rather than acted on.
- The existing capacity-recovery engine owns provider eligibility and scoring. The LLM does not override these constraints.
- Ambiguous messages escalate rather than being guessed.
- A proposal is not a booking. There is no persistence layer, approval endpoint, patient/provider messaging, or real scheduling integration yet.
- The agent does not autonomously make clinical decisions.

## Verification performed

- Unit/API test suite: `46 passed` in the development environment.
- Python compilation: `python -m compileall -q main.py model tests` passed.
- Dashboard JavaScript syntax: `node --check` passed on the extracted inline script.
- Manual API smoke test: a bundled synthetic rescheduling case returned a `PROPOSED` option and the three expected tool-trace entries.

These checks demonstrate local prototype behaviour only. They do not establish production readiness, live LLM provider performance, real-world recovery rates, or operational safety.

## Next implementation priorities

1. Add explicit case IDs and a controlled approval/rejection lifecycle with durable audit records.
2. Build a versioned evaluation dataset with expected outcomes across clear, ambiguous, no-capacity, invalid-ID, conflict, and tool-failure scenarios.
3. Compare the agent against rules-only and existing reschedule baselines.
4. Measure task success, hard-constraint violations, escalation rate, end-to-end latency, and metered LLM cost.
5. Add adversarial and regression tests; define release thresholds before claiming performance.
6. Only consider a real scheduling or messaging integration after access controls, consent, privacy, idempotency, and rollback behaviour are designed.
