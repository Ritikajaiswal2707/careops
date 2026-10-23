# CareOps challenge evaluation (v1)

Run from the repository root:

```bash
python model/evaluate_agent_challenge.py
```

The script evaluates a separately authored 24-case synthetic challenge suite. It disables external LLM calls so the result is deterministic and cost-free. It reports intent accuracy, safe workflow disposition, category-level results, local latency, and the exact cases that failed.

## Snapshot from the implementation run

- Cases: 24
- Intent accuracy: 70.83% (17/24)
- Safe disposition pass rate: 70.83% (17/24)
- Category accuracy: reschedule paraphrases 8/9; cancel-only 1/3; confirmations 1/3; ambiguous 5/7; compound requests 2/2.
- Local offline latency: p50 43.759 ms; p95 103.476 ms in this run. This excludes hosted LLM/API latency and is not a production SLO.

These numbers are a snapshot from one local run, not a universal guarantee. Re-run the script after code changes; `data/evaluation/latest_agent_challenge_eval.json` is generated output.

## Product interpretation

The challenge set exposes phrasing gaps in the rules-first parser, especially casual confirmations and cancellation paraphrases. This is useful evidence: the original authored regression suite passing 31/31 does not imply robust generalisation. Keep these challenge cases separate from development cases when iterating. If a case is used to tune the parser, move it into the regression suite and create a new challenge set rather than continuing to call it unseen.

## Limitations

- Messages are synthetic and manually authored, not sampled from a production population.
- No live LLM is invoked, so this does not measure LLM-fallback performance.
- The expected labels reflect the intended taxonomy and may need review by domain users.
- The agent's recovery proposals still use synthetic operational records; passing this suite does not prove real-world task success or clinical safety.
