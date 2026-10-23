# Phase 8 — Language robustness and evaluation iteration

## What changed

- Expanded the deterministic intent parser to recognise additional cancellation, confirmation, and rescheduling paraphrases in English and Hinglish.
- Added safer handling for negated cancellation requests (for example, "don't cancel" and "not asking to cancel"), returning `Unclear` instead of treating the message as a cancellation.
- Extended date extraction to support number words and phrases such as "seven days from now".
- Made the challenge evaluator accept a suite and output path so each version can be run reproducibly.
- Added challenge suites v2, v3 and v4 plus saved JSON reports. The suites were written by the project author; they are not production-sampled or independently annotated.

## Current synthetic results

The current parser was evaluated offline with external LLM calls disabled:

| Suite | Cases | Intent accuracy | Safe disposition pass rate | Interpretation |
|---|---:|---:|---:|---|
| v1 | 24 | 100% on latest run | 100% on latest run | Original challenge set; used during development, so not a blind holdout |
| v2 | 20 | 100% on latest run | 100% on latest run | Used to diagnose and tune paraphrase coverage; not a blind holdout after iteration |
| v3 | 18 | 100% on latest run | 100% on latest run | Newer authored set; useful regression evidence, but still author-created synthetic data |
| v4 | 15 | 100% on latest run | 100% on latest run | Newer authored set; some phrases informed parser improvements, so not a blind final test |

These numbers are not evidence of production accuracy. The phrase sets are small and synthetic, and parser rules were iteratively changed after reviewing errors. A truly independent evaluation would require messages sampled from realistic workflows, reviewed by multiple annotators, and locked before tuning.

## LLM comparison status

No live LLM-versus-rules comparison was run in this environment because provider credentials were not configured. The existing evaluation harness can be used when a valid provider key is available. Do not estimate or invent LLM accuracy, latency, or cost.

## Known limitations and next steps

1. Rule-based phrase lists remain brittle and can overfit author-written examples.
2. Some phrases depend on conversation context; isolated message classification may not distinguish confirmation from a new scheduling request.
3. Hindi/Hinglish coverage is limited and should be validated with native-speaker review.
4. Before a live pilot, build a locked, independently annotated dataset; measure per-class precision/recall, false cancellation rate, abstention, task success, and constraint violations.
5. The agent remains a synthetic-data prototype and does not book real appointments or contact patients/providers.
