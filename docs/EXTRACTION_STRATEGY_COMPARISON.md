# Extraction strategy comparison

Run from the repository root:

```bash
python model/compare_extraction_strategies.py
```

The script compares three approaches on the same 103-message synthetic labeled dataset:

1. **Rules only:** runs the current rule-based extractor.
2. **Saved blind LLM predictions:** scores the existing saved structured predictions in `model/my_llm_predictions.py`.
3. **Rules-first hybrid:** uses the rules when they return a non-`Unclear` intent, and uses the saved LLM prediction for rule-based `Unclear` cases.

The output is written to `data/evaluation/extraction_strategy_comparison.json`.

## Latest local snapshot

| Strategy | Intent accuracy | Intent macro-F1 | Temporal accuracy | Reason accuracy | LLM route rate |
|---|---:|---:|---:|---:|---:|
| Rules only | 49.5% | 59.4% | 90.3% | 98.1% | N/A |
| Saved blind LLM predictions | 100.0% | 100.0% | 100.0% | 98.1% | N/A |
| Rules-first hybrid | 97.1% | 96.8% | 96.1% | 96.1% | 60.2% |

These numbers are the current run's results; rerun the script to refresh them. The 100% saved-prediction result is not evidence that a live deployed model will achieve 100% accuracy.

## Methodology and limitations

- The three strategies are scored against the same gold labels in `data/communication_eval.json`.
- The LLM-only and hybrid LLM-side outputs reuse the saved prediction artifact `model/my_llm_predictions.py`. This is not a live API run and is not an independent replication.
- Cost and latency for saved LLM predictions are unknown. The report correctly records them as `null`; they must not be treated as zero.
- The rules-only path has measured local execution latency and zero external API cost for this offline function call. That does not mean the full application has zero operating cost.
- The set is synthetic and relatively small. Intent extraction metrics do not measure end-to-end recovery success, appointment feasibility, or clinical safety.
- A live, metered comparison requires configuring `ANTHROPIC_API_KEY` and running `python model/llm_vs_baseline_eval.py`. Review the current provider pricing before publishing cost estimates.
- Before making a generalisation claim, have domain users review labels and create a new locked test set that is not used to tune rules or prompts.

## Product interpretation

On this dataset, the rules-first hybrid improves intent accuracy over rules alone while invoking the saved LLM prediction path for about 60% of messages. That suggests a potential quality/complexity trade-off worth testing, but no cost/latency conclusion is possible without a live metered run. The next decision should be based on a locked test set and measured live fallback economics, not accuracy alone.
