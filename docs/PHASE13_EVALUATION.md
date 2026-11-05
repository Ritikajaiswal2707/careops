# CareOps Phase 13 — Parser Safety Audit

## What changed

- Added `model/evaluate_parser_safety.py` to report a confusion matrix, per-intent recall, false confirmations, false cancellations, missed confirmations, and missed cancellations.
- Added regression tests to check audit fields and ensure the frozen holdout file is not modified by the audit.
- Added `data/evaluation/latest_parser_safety_audit.json`, generated offline from the existing development and frozen holdout suites.

## Results (offline rule parser, synthetic authored cases)

| Suite | Cases | Accuracy | False cancellations | False confirmations | Missed cancellations | Missed confirmations |
|---|---:|---:|---:|---:|---:|---:|
| Mutable development suite v1 | 36 | 100.00% | 0 | 0 | 0 | 0 |
| Frozen holdout v1 | 30 | 83.33% (25/30) | 0 | 0 | 1 | 1 |

The development suite is used for iteration and is not independent. The holdout was read only and not used to tune the parser. These are counts on small, manually authored synthetic suites, not estimates of real-world safety or performance. Zero false confirmations/cancellations in 30 examples does not imply zero risk.

## Full validation

- `python -m pytest -q`: **82 passed**.
- `python model/evaluate_parser_safety.py`: completed successfully.
- External LLM disabled; no API cost or live model latency measured.
- No real patient data or real appointment changes used.

## Recommended next validation gate

Before making claims about generalisation, have care-operations reviewers independently annotate a fresh set of de-identified or consented messages, with a written label guide and adjudication for disagreements. Keep that set locked away from development. Report per-intent precision/recall, false cancellation and false confirmation rates with confidence intervals, abstention/escalation rate, and end-to-end disposition safety. Do not connect to live appointment execution until operational owners approve hard constraints and a monitored shadow-mode trial.
