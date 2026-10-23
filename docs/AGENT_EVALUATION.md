# CareOps Recovery Agent Evaluation

## Run the evaluation

From the repository root:

```bash
python model/evaluate_agent.py
pytest -q
```

The evaluator disables external LLM calls and uses the bundled synthetic appointment records. It writes detailed per-case results to `data/evaluation/latest_agent_eval.json`.

## Current regression run

- Scenario count: 31
- Intent match on this authored suite: 31/31 (100%)
- Expected disposition pass rate: 31/31 (100%)
- Reschedule scenarios: 13
- Reschedule proposal rate: 12/13 (92.31%); one scenario had no feasible option in the configured search window
- Ambiguous scenarios safely escalated: 10/10 (100%)
- Response-integrity errors: 0
- Negative-path checks: unknown appointment rejected; no candidate returns no proposal; recovery tool failure escalates without leaking exception details
- Automated tests: 58 passed in the current environment

## What these numbers mean—and do not mean

This is a small, hand-authored regression suite used to catch known behaviour changes. The 100% intent match is only on these 31 scenarios; it is **not** an independent holdout result and does not establish generalisation to real patient messages. The suite uses synthetic records and runs with the external LLM disabled, so it does not measure live LLM quality, provider latency, API cost, or production reliability. The proposal rate is a synthetic workflow outcome, not a real appointment recovery rate.

## Iteration driven by evaluation

The initial run exposed two expected-intent mismatches:

- "Could we change the visit to Sunday instead?" was not recognised as a reschedule request.
- "I will be there for the scheduled visit" was not recognised as a confirmation.

The rule vocabulary was updated to cover these phrasings. The regression suite then passed all 31 scenarios. Because the same authored cases informed the rule update, the 100% result should be interpreted as regression coverage—not as unbiased model performance. Next, expand the scenario set with independently authored paraphrases, multilingual messages, typos, negation, conflicting requests, and adversarial/ambiguous cases before using the result as a stronger evaluation claim.

## Next evaluation milestones

1. Grow the set to 300–500 scenarios with separate development and held-out splits.
2. Track per-intent precision/recall and confusion matrix, not just aggregate accuracy.
3. Add property-based checks for invalid appointment IDs, appointment mismatch, missing availability, tool exceptions, and no eligible replacement.
4. Compare rules-only and rules-plus-LLM using the same cases; record API cost and latency only when real calls are made and metered.
5. Validate the workflow with care coordinators before claiming product impact.

## Phase 4: safety and failure-path hardening

The current implementation adds two targeted safeguards:

- Candidate selection now excludes a provider when the target time-of-day slot is already at its configured slot capacity, even if the provider has remaining daily capacity.
- If recovery search raises an unexpected tool/data exception, the agent fails closed: it returns `needs_human_review`, emits no proposal, and records a generic tool error without exposing the exception message.

Additional tests cover a full-slot provider being excluded and recovery-tool failure escalation. The latest offline run reports 31/31 authored regression scenarios passing, all negative-path checks passing, and 58 automated tests passing.

These tests establish expected behaviour for the cases covered; they do not prove zero constraint violations across all possible inputs. The agent still uses synthetic data, and no live booking or messaging is executed.

## Phase 5: execution observability

The evaluator now records per-case local execution time, tool-call counts, final status counts, and p50/p95/mean local latency. These values are useful for detecting regressions in the local synthetic workflow, but are not production latency measurements: the external LLM is disabled and live API/network latency and costs are not measured.

The negative-path checks now also verify that a malformed LLM response is rejected and escalated without creating a proposal. The four checks currently cover unknown appointment IDs, no eligible candidate, recovery tool failure, and invalid LLM schema.

Latest local run (31 authored synthetic scenarios):

- Expected disposition pass rate: 31/31 (100%) on this regression suite.
- Status distribution: 12 awaiting coordinator approval, 10 needs human review, 1 no feasible option, 8 unsupported intent.
- Tool traces: 75 calls across 31 cases (2.419 average recorded tool steps per case).
- Local execution latency: p50 49.684 ms, p95 131.015 ms, mean 72.449 ms in this run. These timings are environment-dependent and do not include a live LLM call.
- Negative-path checks: 4/4 passed.
- Response-integrity errors: 0.

Do not use these numbers as live service SLAs or real-world task-success claims. The next benchmark upgrade should use an independently authored holdout set, measure actual LLM cost/latency only with metered live calls, and compare end-to-end task success against a defined baseline.
