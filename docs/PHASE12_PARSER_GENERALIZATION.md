# CareOps Phase 12 — Parser Generalization

## What changed

- Expanded cancellation paraphrases (e.g., skipping a visit, removing a booking, and explicit requests not to send anyone).
- Expanded rescheduling paraphrases (date/slot changes, postponement, shifting, and moving a visit).
- Expanded positive attendance confirmations.
- Added conservative handling for uncertain confirmations such as “I cannot confirm now” and “not confirmed yet”; these remain `Unclear` rather than being treated as confirmation.
- Added a separate, mutable 36-case development suite and a reproducible evaluator: `data/evaluation/parser_development_v1.json` and `model/evaluate_parser_development.py`.

## Validation results

| Evaluation | Result | Interpretation |
|---|---:|---|
| Development parser suite | 36/36 (100%) | Synthetic development cases; used for iteration |
| Challenge v4 end-to-end suite | 15/15 (100%) | Synthetic challenge regression suite |
| Frozen end-to-end holdout v1 | 25/30 (83.33%) | Regression check only; suite file was not edited or used to choose individual rules |
| Proposal revalidation | 5/5 (100%) | All generated proposals in this run passed the existing revalidation checks |
| Full automated tests | 80 passed | Local test suite |

The previous Phase 11 report recorded 23/30 (76.67%) on the frozen holdout. This run scored 25/30 (83.33%). This is an observed regression-check change, not a statistically reliable estimate of generalisation. The holdout is synthetic and author-created, not independently sampled. Parser changes were guided by new development cases and existing challenge coverage; the holdout was run after the changes as a final check.

## Remaining errors

The frozen holdout still has five classification/disposition failures: three direct-reschedule messages, one cancellation message, and one confirmation message. They were not used as targets for further tuning in this phase. Continue development on a separate dataset, and consider human review for unsupported or ambiguous messages.

## Limitations

- All evaluation messages are synthetic and manually authored.
- External LLM calls were disabled; results measure the offline rule-based path only.
- Latency is local Python execution time, not hosted API latency or a production SLO.
- No real patient messages, notifications, or bookings were used. Results do not establish clinical safety or production readiness.
