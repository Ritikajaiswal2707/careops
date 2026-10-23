# CareOps — Technical Notes

## What runs where

CareOps has two distinct layers:

1. **Precomputed dashboard snapshot:** `model/generate_dashboard_data.py` writes `model/dashboard_data.json` and embeds the same data in `dashboard/index.html`. The displayed snapshot date is fixed at `2026-08-29`; it is synthetic and is not refreshed by opening the HTML.
2. **Interactive demo API:** `main.py` serves the static dashboard and exposes `/health`, `/api/operations`, `/api/analyze`, `/api/recover`, `/api/reschedule`, and `/api/agent/run`. The interactive API calls the model modules against bundled synthetic CSVs. It does not send messages, book visits, or write to a real scheduler.

The root `StaticFiles` mount is registered last so it does not shadow the API endpoints. Unknown non-API paths may be returned as a static-file 404 rather than an API method error because the dashboard is mounted at `/`.

## Module map

| File | Responsibility |
|---|---|
| `model/disruption_model.py` | Time-based train/test split and logistic-regression disruption risk model; compares leaky and leakage-fixed versions. |
| `model/fairness_subgroup_analysis.py` | First-time vs returning-patient subgroup performance and calibration checks. |
| `model/disruption_type_model.py` | Diagnostic No-Show vs Cancelled model; current ROC-AUC is near chance and should remain a disclosed negative finding. |
| `model/communication_intelligence.py` | Rules/keywords for intent, urgency, reason and temporal signals. |
| `model/my_llm_predictions.py` | Frozen blind offline predictions for 103 held-out messages; these are not runtime API calls. |
| `model/llm_direct_eval.py` | Scores rules and saved blind predictions on the held-out set. |
| `model/hybrid_extraction.py` | Rule-first runtime extractor; strict validation of the live LLM schema; human escalation when the rule/LLM path has no usable answer. |
| `model/gemini_llm.py` | Optional Gemini REST call used by the interactive API's LLM fallback. Default model is `gemini-3.8-flash`, overridable with `GEMINI_MODEL`. |
| `model/capacity_recovery.py` | Hard provider eligibility filters, historical-only continuity/location features, weighted Recovery Score, slot-capacity updates. |
| `model/reschedule_agent.py` | Existing message → temporal signal → date search → ranked proposal flow. Real calls stop at `PROPOSED`. |
| `model/recovery_agent.py` | Bounded tool-using orchestrator: validates appointment context, interprets the message, searches eligible recovery options, and returns a structured tool trace plus an approval-required proposal. No booking or notification is executed. |
| `model/agent_state_machine.py` | Enforced lifecycle transitions and history. Its demonstration of a completed flow uses synthetic responses and is not live patient confirmation. |
| `model/economics_simulation.py` | Top-down sensitivity analysis with explicit placeholder assumptions. |
| `model/intervention_outcome_simulation.py` | Bottom-up capacity-constrained simulation and per-case outcomes. |
| `model/experiment_power.py` | Reproducible unadjusted sample-size sensitivity calculator for a proposed outreach experiment. |

## Data and time boundaries

`data/` contains synthetic appointments, providers, patients, availability, operational events, communications and the 103-message evaluation set. The appointment history spans `2026-06-01` through `2026-08-29`; `availability.csv` spans `2026-06-01` through `2026-10-28`, with future availability generated rather than observed. Recovery target dates are limited to that supported availability horizon. Provider proximity is inferred from historical patient locations, not measured provider GPS. Provider-service compatibility is an explicit business-rule mapping.

Do not submit real patient information to this portfolio demo. If external Gemini/Anthropic calls are enabled, a message sent to the interactive endpoint may be shared with that provider under the configured account's terms; privacy, consent, retention and data-minimization requirements have not been validated for a real care operation.

## Install and run

Python 3.11 is the configured deployment runtime. From the repository root:

```bash
python -m pip install -r requirements.txt
python run.py
```

The launchers `run.py`, `run.sh`, and `run.ps1` invoke the same 11 pipeline stages. The offline pipeline does not make external LLM calls; unresolved messages are escalated while generating the static snapshot. Open `dashboard/index.html` to inspect the snapshot.

To run the interactive API:

```bash
python -m pip install -r requirements.txt
uvicorn main:app --reload
```

Then open `http://127.0.0.1:8000`. The API works without LLM keys; unclear messages escalate. `main.py` does not load `.env` automatically. Set `GEMINI_API_KEY`/`GEMINI_MODEL` in the shell or deployment environment if enabling Gemini, and optionally `ANTHROPIC_API_KEY` after installing the optional `anthropic` package. Model availability can change; check Google’s [Gemini model list](https://ai.google.dev/gemini-api/docs/models) and [deprecation schedule](https://ai.google.dev/gemini-api/docs/deprecations) before deploying. The current model ID has not been verified with a live API call in this audit.

For tests and static checks:

```bash
python -m pip install -r requirements-dev.txt
pytest -q
python -m compileall -q main.py model tests
```

## API contracts

- `GET /health`: liveness only; it does not verify external provider access.
- `GET /api/operations`: returns the precomputed synthetic snapshot or `503` if the artifact is unavailable/corrupt.
- `POST /api/analyze`: JSON body `{"message":"..."}`; nonblank text up to 2,000 characters. Ambiguous messages can return `escalate_to_human: true`.
- `POST /api/recover`: JSON body with an existing `appointment_id`, `target_date` in strict `YYYY-MM-DD` format within `2026-06-01` to `2026-10-28`, and optional supported `service_type`.
- `POST /api/reschedule`: JSON body with an existing `appointment_id` and nonblank message up to 2,000 characters. Returns a trace and optional proposal. A proposal is not a booking.
- `POST /api/agent/run`: same request schema; returns agent version, status, structured tool trace, intent source, checked dates and an optional proposal requiring coordinator approval. The endpoint does not persist approval or change appointment records.

Request schema errors return `422`, unknown appointment IDs return `404`, and missing/corrupt required artifacts return `503`. Error responses should not echo submitted message contents.

## Evaluation provenance

The headline offline values are stored in JSON artifacts under `model/`. The 103-message LLM and hybrid evaluation reuses frozen blind predictions from `model/my_llm_predictions.py`; it is not a benchmark from live Gemini/Anthropic responses. LLM cost/latency are `null` because they have not been measured with a metered request. Runtime provider access and current model quality have not been verified by an end-to-end live API call in this audit.

The risk model's ROC-AUC is about `0.58`, while the leaky comparison was higher (`0.658`). Top-20% precision is `33.6%` and recall `26.1%` on the synthetic test split. Stage 2 No-Show-vs-Cancelled ROC-AUC is `0.521`. These modest/negative results are important limitations, not defects to hide.

## Economics and experiment limits

At the placeholder 35% intervention-success assumption, the top-down simulation estimates 74 recovered visits and +₹33,970 modelled net value. The bottom-up, capacity-constrained simulation estimates 16 recovered visits and −₹12,850. The latter finds 164 of 212 true disruptions in the flagged group have no eligible candidate. All revenue, cost and intervention-success inputs are assumptions. The 14.9% break-even number belongs to the top-down formula and is not a proven economic threshold under the constrained simulation.

`EXPERIMENT_DESIGN.md` proposes (but does not report) a randomized outreach study. Its sample-size table is an unadjusted planning calculation. Repeat appointments from the same patient require a protocol decision on patient-level randomization or a cluster-aware analysis before any real trial.

## Known operational limitations

- Data and future availability are synthetic; there are no real customers, providers or operations connected.
- The dashboard snapshot is static; interactive API calls use synthetic files.
- Browser-side “Simulate approval” does not send messages or write a booking.
- There is no production database, authentication, audit retention, scheduling integration or patient messaging channel.
- Model discrimination is modest, subgroup calibration is a concern, message evaluation uses saved blind predictions, and LLM live quality/cost/latency/uptime are not measured.
- A clean local/API test is not evidence that the remote Render deployment is healthy. Verify the deployed URL separately before sharing it.
