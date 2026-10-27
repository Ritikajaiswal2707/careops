# Extraction strategy comparison

Run from the repository root:

```bash
python model/compare_extraction_strategies.py
```

The script compares three approaches on the same 103-message synthetic labeled dataset:

1. **Rules only:** runs the current rule-based extractor.
2. **Saved blind LLM predictions:** scores existing saved structured predictions. This is an offline artifact, not a live API benchmark.
3. **Rules-first hybrid:** uses rules when they return a non-`Unclear` intent and saved LLM predictions for rule-based `Unclear` cases.

The output is written to `data/evaluation/extraction_strategy_comparison.json`.

## Latest local evaluation

| Strategy | Intent accuracy | Intent macro-F1 | Temporal accuracy | Reason accuracy | LLM route rate |
|---|---:|---:|---:|---:|---:|
| Rules only | 53.4% | 63.2% | 90.3% | 98.1% | N/A |
| Saved blind LLM predictions | 100.0% | 100.0% | 100.0% | 98.1% | N/A |
| Rules-first hybrid | 98.1% | 98.0% | 96.1% | 96.1% | 58.3% |

These results are from the latest reported local run on 103 synthetic labeled messages. Rerun the script to refresh the metrics. The 100% saved-prediction result is not evidence that a live deployed model will achieve 100% accuracy.

## Methodology and limitations

- The strategies are scored against the same gold labels in `data/communication_eval.json`.
- The saved LLM predictions are reused for the LLM-only and hybrid approaches. This is not a live API run or an independent replication.
- The hybrid routes messages to the saved LLM prediction path when the rule-based intent is `Unclear`. On this run, 58.3% of messages were routed.
- The hybrid made 2 intent misclassifications out of 103 messages. Both were produced by the rule-based path, showing that the current abstention gate does not catch every incorrect rule prediction.
- Cost and latency for saved LLM predictions are unknown and must not be treated as zero.
- Rules-only local execution latency and zero external API cost apply only to the measured offline function call, not the full application.
- The dataset is synthetic and relatively small. Intent extraction metrics do not measure end-to-end recovery success, appointment feasibility, or clinical safety.
- A live, metered comparison requires configuring `ANTHROPIC_API_KEY` and running `python model/llm_vs_baseline_eval.py`. Check current provider pricing before publishing cost estimates.
- Before generalising these results, have domain users review the labels and create a new locked test set that is not used to tune rules or prompts.

## Product interpretation

In this offline evaluation, the rules-first hybrid achieved 98.1% intent accuracy versus 53.4% for rules alone, with 58.3% of messages routed to the saved LLM prediction path. This suggests a quality/complexity trade-off worth testing, not proof of production performance. The next decision should be based on a locked test set and measured live fallback economics, not accuracy alone.