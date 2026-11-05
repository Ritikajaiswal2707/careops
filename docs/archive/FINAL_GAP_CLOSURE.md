# CareOps finalisation pass — 23 October 2026

## Changes made in this pass

1. **Evidence hygiene:** corrected the README's stale frozen-holdout headline from 23/30 to the current locally reproduced 25/30 result. The old result is retained only as historical context. The holdout remains author-created and synthetic.
2. **Customer discovery attribution:** the README now explicitly records that the project was informed by real conversations and observed workflow/app interactions with city coordinators, nurses, and care-operations stakeholders at an elder-care startup in India. It describes the documented qualitative insights without inventing a participant count, measured handling-time baseline, quotes, or quantified frequency.
3. **Public demo guardrails:** Render is configured with `CAREOPS_PUBLIC_DEMO_READ_ONLY=true` and `CAREOPS_DISABLE_EXTERNAL_LLM=true`. Agent case creation/retrieval/decision/execution endpoints return 403 in public read-only mode. The external LLM fallback returns no result when disabled, allowing the parser to escalate rather than make a network call.
4. **Regression coverage:** added tests for public read-only mode and external-LLM disabling.

## Local validation

- `python -m pytest -q`: 84 passed.
- `python model/evaluate_agent_holdout.py`: 25/30 intent accuracy (83.33%); 25/30 expected disposition pass; 5/5 generated proposals passed synthetic revalidation.
- `python model/evaluate_parser_safety.py`: development suite 36/36; frozen holdout 25/30; 0 false cancellations, 0 false confirmations, 1 missed cancellation and 1 missed confirmation on the holdout.
- `python -m compileall -q main.py model tests`: passed.

These are local tests on synthetic, author-created data. They are not independent evidence of real-world safety or customer outcomes. Local latency excludes external API and hosted network latency.

## Known limitations not solved by code changes

- Hosted Render behaviour was not verified from this environment. The repository configuration is safer by default, but the deployed service must be tested in a browser after deployment.
- No measured coordinator handling-time baseline or controlled user study is claimed. The existing discovery evidence is qualitative.
- No independently annotated benchmark, live metered model comparison, or real operational outcome is available in this repo.
- The public demo guardrails are not production authentication. Any production use requires authentication, authorisation, data governance, observability, incident handling, and a formally approved operational workflow.

## What the project owner needs to do

1. Deploy the updated repository to Render and confirm `/health` returns `mode: synthetic-demo`.
2. Confirm that `/api/agent/run` returns 403 on the public demo and that the interactive analysis path does not invoke a provider API when `CAREOPS_DISABLE_EXTERNAL_LLM=true`.
3. If the interview research included measured handling-time figures, add the actual method, sample size, and results. If handling time was not timed, leave it explicitly unmeasured—do not estimate retrospectively.
4. Before publishing the case study, remove any confidential participant details and only include quotes or sample counts that are actually recorded.
