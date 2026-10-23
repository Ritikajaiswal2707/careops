# Phase 10 — Frozen end-to-end holdout and proposal integrity

## What changed

- Added `data/evaluation/agent_holdout_v1.json`: 30 synthetic, author-created cases spanning reschedule requests, cancellations, confirmations, ambiguous/negated actions, compound requests, unsupported requests, and empty/noisy input.
- Added `model/evaluate_agent_holdout.py`, which reports intent accuracy, expected safe disposition, category-level performance, local latency, and revalidation of any proposed provider/date against the current synthetic availability data.
- Added a concurrent execution regression test to check that repeated simultaneous execution requests for the same approved case create one simulated execution record.

## Run

```bash
python model/evaluate_agent_holdout.py
pytest -q
```

## Evaluation policy

This holdout is frozen for regression tracking and should not be used to tune parser rules. Make changes against the development/challenge suites, then re-run the holdout to measure possible regressions. Because the cases are manually authored by the project developer and not sampled independently from real operations, it is not an independent benchmark or evidence of production generalisation.

## Safety boundaries

The evaluator invokes only the offline rules-first path (`llm_call=None`). Proposal revalidation uses bundled synthetic availability. Execution remains simulation-only; no real booking or patient/provider communication occurs. Local latency excludes external model/network latency and must not be presented as a production SLA.
