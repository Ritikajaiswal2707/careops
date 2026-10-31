# CareOps — technical deep dive

> The full build log and evaluation history. For the short version, see the [README](../README.md).

A portfolio project exploring how AI can predict, explain, and help recover from disruptions in home healthcare delivery — with a specific focus on the operational realities of India's home-care market: contractual/gig service providers with variable day-to-day availability, elderly patients who often can't self-report precise location, and delay cascades caused by traffic, weather, or overruns.

**This is a PM portfolio project.** All data is synthetic/simulated. It exists to demonstrate product thinking — problem framing, prioritization, tradeoff decisions, and AI-product judgment — not to claim production-grade engineering or real-world validated outcomes.

## User discovery and evidence boundaries

CareOps was informed by real conversations and observed app/workflow interactions with city coordinators, nurses, and other care-operations stakeholders at an elder-care startup in India. Those conversations informed the problem framing and workflow around disruption triage, interpreting family messages, provider eligibility, availability, location/specialisation constraints, and escalation when no suitable replacement exists. These are qualitative discovery inputs, not a claim that every insight was independently validated across a quantified sample. No measured coordinator handling-time baseline, controlled usability result, production adoption, or real-world recovery outcome is claimed in this repository. All public evaluation datasets and outcome simulations remain synthetic. See the existing interview guide and case-study materials for the research narrative; do not publish identifiable or confidential operational details.

## Public demo safety mode

The Render configuration enables `CAREOPS_PUBLIC_DEMO_READ_ONLY=true` and `CAREOPS_DISABLE_EXTERNAL_LLM=true`. In this mode, persisted agent-case retrieval/creation, approval, and simulated execution endpoints are disabled, and external LLM calls are skipped. The dashboard's non-persistent analysis/recovery examples remain available using local rules and synthetic data. For the full approval lifecycle, run locally with these flags unset/false. This is a portfolio-demo safeguard, not a substitute for production authentication or security review.

## Recovery agent evaluation

Run the authored regression suite with `python model/evaluate_agent.py` and the default phrasing challenge suite with `python model/evaluate_agent_challenge.py`. Additional authored challenge versions can be run with `python model/evaluate_agent_challenge.py --suite data/evaluation/agent_challenge_v3.json --output data/evaluation/latest_agent_challenge_v3_eval.json` (change the suite/output paths for v2 or v4). See [`docs/CHALLENGE_EVALUATION.md`](CHALLENGE_EVALUATION.md) and [`docs/PHASE8_LANGUAGE_ROBUSTNESS.md`](PHASE8_LANGUAGE_ROBUSTNESS.md). These are synthetic, offline evaluations with external LLM calls disabled, not production benchmarks.


## Quickstart

```bash
git clone https://github.com/Ritikajaiswal2707/careops.git
cd careops
python run.py
```

On macOS/Linux/Git Bash/WSL, `./run.sh` runs the same 11-stage pipeline. On Windows PowerShell, use `.\run.ps1`. All launchers resolve paths from their own location and install from `requirements.txt`; pass `--no-install` to `run.py`/`run.sh` or `-NoInstall` to `run.ps1` to skip installation.

The pipeline trains/evaluates the models, runs the offline saved-prediction comparisons, and regenerates `model/dashboard_data.json` plus the embedded `DATA` snapshot in `dashboard/index.html`. It **does not call an external LLM API**: unresolved messages in snapshot generation escalate rather than trigger a network call. Open `dashboard/index.html` directly for the static snapshot, or start the API below for the interactive tab.

## Live demo

The dashboard has two distinct modes: the main risk/cascade views display a **precomputed synthetic snapshot**; the "Try the AI" tab sends requests to the FastAPI backend in `main.py`. Those interactive API requests call the same model modules used by the pipeline, using the repository's synthetic appointment/provider data. The default live request path can call Gemini when `GEMINI_API_KEY` is configured; otherwise ambiguous messages escalate. The dashboard's legacy approval/execution animation is a **browser-side simulation**, not an actual booking or notification. The recovery-agent API now persists proposal cases and coordinator approve/reject decisions in SQLite with an audit trail. Decisions are recorded only; they do not book appointments or send messages.

Run it locally:
```
pip install -r requirements.txt
uvicorn main:app --reload
```
Open `http://127.0.0.1:8000`. The API also exposes `/health`, `/api/operations`, `/api/analyze`, `/api/recover`, `/api/reschedule`, `/api/agent/run`, `GET /api/agent/cases/{case_id}`, and `POST /api/agent/cases/{case_id}/decision`. The **Run recovery agent** button exercises a bounded tool-using flow: appointment lookup → message interpretation → candidate search → approval-gated proposal. It never books or sends messages.

For deployment, connect this repository to [Render](https://render.com); it reads `render.yaml`. Configure `GEMINI_API_KEY` in Render only if you want the live LLM fallback, and optionally `ANTHROPIC_API_KEY` if the Anthropic SDK is installed. Set `GEMINI_MODEL` to override the default model. Environment variables in `.env.example` are examples only: `main.py` does not load a local `.env` file automatically. **The hosted URL was not verified as reachable during this repository update**, so no live URL is promoted here.

All bundled data is synthetic or simulated. The interactive API does not send patient/provider messages, make real bookings, or write to a production scheduling system. Do not submit real patient information to this portfolio demo.

## Structure

- `data/` — synthetic 6-table dataset (providers, patients, appointments, operational, communications, availability) modeling a home-care operation across 5 Indian cities, 20 clinicians, 2,000 patients, 10,000 appointments. `availability.csv` covers Jun 1 – Oct 28 (extended 60 days past the original Aug 29 cutoff — see note below). `data/communication_eval.json` is the 103-message held-out set used by `model/llm_direct_eval.py` and `model/llm_vs_baseline_eval.py` — a real data artifact now, not embedded in the evaluator script
- `model/disruption_model.py` — logistic regression predicting visit disruption risk (time-based train/test split: train Jun-Jul, test Aug), plus a rule-based plain-language explanation layer and threshold/precision-recall tradeoff analysis. **Fits and reports both a leaky and a leakage-fixed version side by side** (see "A leakage bug, found and fixed" below) — the fixed version is what the dashboard actually runs on
- `model/fairness_subgroup_analysis.py` — real subgroup check (precision, recall, false-positive rate, calibration) split by first-time vs. returning patient, at the top-20% operational threshold — see "First-visit status" under Known limitations below for what it actually found
- `model/disruption_type_model.py` — a Stage 2 diagnostic model, trained and evaluated on appointments filtered by the TRUE status label (not conditioned on Stage 1's predicted flag — see the file's own "Naming note" for why that distinction matters), predicting No-Show vs. Cancelled specifically (the binary target treats them identically); also documents that Rescheduled-status appointments currently fall outside the disruption target entirely, counted as "not disrupted"
- `model/communication_intelligence.py` — rule/keyword-based extractor that turns raw patient messages (`communications.csv`, mixed English/Hinglish) into structured signal: intent, `cancel_current`, preferred day, urgency, reason. Not a live LLM call — no API key is wired into this environment. Agrees with the dataset's own intent labels 100% of the time, but that's measured against its own training templates — see `model/llm_direct_eval.py` below for what actually happens on unseen phrasing
- **Taxonomy note — compound requests.** A single Cancel/Reschedule label can't represent a message like *"aaj cancel, kal aa jaunga"* ("cancel today's, I'll come tomorrow"): the patient is cancelling the current slot **and** requesting a new one in the same breath. Forcing that into one label was an actual bug found while building the held-out eval below — two messages (`data/communication_eval.json` cases 50 and 81) were originally gold-labeled `Cancel` when the real ask was `Reschedule`. The fix was a second boolean field, `cancel_current`, rather than adding more single-choice labels: `{"intent": "Reschedule", "cancel_current": true, "preferred_day": "Wednesday", ...}` now represents "cancel the current one, book Wednesday instead" without ambiguity. Both the rule-based extractor and the live-API schema in `llm_vs_baseline_eval.py` implement it; see `communication_intelligence.py`'s `extract_intent()` for the compound-detection logic.
- `model/hybrid_extraction.py` — the production architecture decision built on the eval below: don't call an LLM on every message, only on the ones the free rule-based parser abstains on (`intent="Unclear"`), and escalate to a human coordinator when neither side has a usable answer. This is a **rule-first hybrid with LLM fallback** — the gate is the rule-based extractor's own abstention, not a calibrated confidence score, hence the name (an earlier draft called this "confidence-gated," which overstated what the gate actually is — see the module's own naming note). `reschedule_agent.py` and `generate_dashboard_data.py` both call `extract_intent_hybrid()`, not the bare rule-based `extract_intent()`, for the patient-signal path. See the table below
- `model/llm_direct_eval.py` (+ `model/llm_vs_baseline_eval.py`, + `model/my_llm_predictions.py`) — the real generalization test the 100%-agreement number can't provide: the 103-message held-out set in `data/communication_eval.json`, hand-labeled with the *full* gold structure (intent, `cancel_current`, temporal signal, reason — not just intent), written independently of `communications.csv`'s 10 templates (typos, Hindi in Devanagari script, code-switching, sarcasm, compound requests, indirect phrasing, no keyword overlap in several cases on purpose). **Results on the held-out set (offline):**

  | Metric | Rule-based | Claude (direct extraction) |
  |---|---|---|
  | Intent accuracy | 53.4% | **100%** |
  | Intent macro F1 | 0.632 | **1.0** |
  | Temporal-field accuracy | 90.3% | **100%** |
  | Reason-field accuracy | 98.1% | 98.1% |
  | `cancel_current` accuracy | 100%¹ | not scored² |
  | Abstention rate | 58.3% | 14.6% |
  | JSON validity | 100% | 100% |
  | Cost / message | ₹0 | not measured |
  | Latency / message | ~0.01ms | not measured |

  **Blind offline evaluation: Claude 100% vs. rules 53.4% intent accuracy on 103 held-out messages.** That's the accurate way to state this result — not "production LLM accuracy = 100%." The 100% number above is Claude performing the extraction directly on all 103 messages, blind to gold labels, with no metered Anthropic API call involved (see ¹/² and the paragraph below the table). It's a real, honest signal that the extraction-quality gap is worth taking seriously; it is not a production benchmark, and shouldn't be quoted as one.

  ¹ The rule-based side implements `cancel_current` in live code (`extract_intent()`), so it's scored normally against gold.
  ² Claude's 103 predictions in `model/my_llm_predictions.py` were frozen *before* `cancel_current` existed in the schema — backfilling a value for it now would be grading hindsight, not a blind answer, so `llm_direct_eval.py` reports it as `null` rather than fabricating a number. A fresh blind pass (or a live API run via `llm_vs_baseline_eval.py`, whose system prompt already asks for the field) would be needed to measure it honestly.

  **The product decision this table actually supports isn't "always call an LLM" — it's when to.** Calling an LLM on every message would mean paying its cost/latency on the 35% of messages the free rule-based parser already gets right. `model/hybrid_extraction.py` implements a **rule-first hybrid with LLM fallback** instead (not "confidence-gated" — see the naming note in that module's docstring: the gate is a binary abstention signal, not a calibrated confidence score, and this project isn't going to build one just to justify a fancier name): the rule-based extractor runs first and is accepted unconditionally whenever it isn't abstaining; only its 58.3% routing ("Unclear") share is routed to an LLM fallback, and anything neither side can resolve — 13.6% of the full 103-message set, JSON-invalid or still `Unclear` after the fallback — is escalated to a human coordinator rather than guessed. Scored the same way as the table above (same held-out set, same LLM side — the blind, unmetered predictions, not a metered API call):

  | Metric | Rule-first hybrid (LLM fallback) |
  |---|---|
  | Intent accuracy | **98.1%** |
  | Intent macro F1 | 0.980 |
  | Temporal-field accuracy | 96.1% |
  | Reason-field accuracy | 98.1% |
  | Routed to LLM | 58.3% (rest resolved free, by rules alone) |
  | Escalated to human | 13.6% |
  | Cost / latency | not measured — see below |

  98.1% is *below* the LLM-alone 100%, not above it — the 2 hybrid misclassifications are cases where the rule-based gate abstained when it shouldn't have trusted itself, i.e. it was confidently wrong instead of abstaining (see `hybrid_extraction.py`'s `__main__` output), which is itself a real finding: the gate's abstention signal isn't a perfectly reliable proxy for correctness, and a production version of this would want a held-out check on *that*, not just on end-to-end accuracy. The honest sell here isn't "98.1% beats 44.7%" — it's "the LLM is only ever paid for on the 58.3% of messages routed by the rules-first gate, instead of on all of them," which is a structural cost/latency advantage regardless of what the eventual metered ₹/message number turns out to be. `hybrid_extraction.py`'s `default_llm_call()` tries the configured Gemini API first and may fall back to Anthropic if the optional SDK/key are configured. This runtime provider path is separate from the saved blind predictions used for the offline score; its live quality, cost and latency have not been measured.

  **Temporal-label convention fix.** The 90.3%/100% pair above reflects a second labeling bug found while re-checking the eval set: `preferred_day`/`next_week`/`relative_day`/`offset_days` are supposed to encode the day the patient is *requesting*, but 7 of the 103 gold rows instead encoded any date-like mention in the message — including a day the patient explicitly says they *can't* do ("kal nahi ho payega, agle hafte try karte hain" → the real target is `next_week=true`, not `relative_day="tomorrow"`) or the date of a conflicting event ("next tuesday ko doctor ka appointment hai, uske baad kisi din kar lo" → no specific day was actually requested, so it should be `null`, not "Tuesday"). Fixing those 7 rows moved Claude's blind-extraction temporal accuracy from 93.2% to **100%** — it turns out Claude was never confusing "unavailable" with "requested," the old gold labels were. It also, honestly, moved the rule-based extractor's temporal accuracy *down*, from 91.3% to 90.3%: `parse_temporal()` tags any weekday/relative-day token it finds regardless of polarity, so it was previously getting credit for the same mislabeling it now gets marked wrong for. That's a real, newly-exposed limitation of the rule-based parser (it doesn't distinguish "not free tomorrow" from "works for me tomorrow"), left as-is rather than patched with a fragile negation heuristic — documented here instead, the same way this project chose not to chase the risk model's 0.58 ROC-AUC.

  The rule-based extractor is a lookup table for phrasing that resembles its 10 training templates, and its single biggest failure mode is casual/minimal confirmations ("ok", "k", "yep all good") that don't contain any of its exact `CONFIRM_WORDS` phrases. The LLM side is a genuine, blind offline result — predictions in `model/my_llm_predictions.py` were written from a plain numbered list of the 103 messages, with no access to the gold labels, then scored — but it is **not** from a metered Gemini or Anthropic API call. The saved evaluation does not depend on whichever API keys happen to be present in the current environment. Claude performed the extraction directly instead, using the exact same schema `llm_vs_baseline_eval.py`'s system prompt specifies (minus `cancel_current`, added later — see above). That means intent/temporal/reason accuracy above are real and honest; cost-per-message and latency are not, and are reported as `null` in `model/llm_vs_baseline_results.json` rather than estimated. This blind, unmetered result is deliberately **not the headline number for this project** — treat it as evidence the extraction quality gap is real and worth a real benchmark, not as a substitute for one. Cost and latency for the current Gemini/Anthropic runtime path are not measured. Do not quote a per-message cost or latency until `model/llm_vs_baseline_eval.py` is run against a metered provider call and the model, token counts, region, request timing and pricing date are documented. Claude had 0 intent misclassifications and 0 temporal mismatches on this pass; the intent fix was a compound-request taxonomy correction (see above) and the temporal fix was the labeling-convention correction described above — both are gold-label corrections, not new information handed to the predictor.
- `model/capacity_recovery.py` — scores every eligible candidate provider on a weighted **Recovery Score** (continuity + proximity + remaining capacity + same-time-slot fit + service fit, minus a utilization penalty) and returns the ranked list with a plain-language "why" for each — a trade-off, not just a filtered pool. See "The Recovery Score" below
- `model/recovery_agent.py` — bounded orchestration over appointment lookup, message interpretation, recovery-option search and approval-gated proposals; returns a structured tool trace and does not execute bookings. Exposed through `/api/agent/run`.
- `model/approval_store.py` — SQLite persistence for synthetic recovery cases, coordinator approve/reject decisions, and append-only decision events. Approval is recorded but does not trigger a booking or notification. Set `CAREOPS_DB_PATH` to choose the writable database path; default is a temporary-directory file.
- `model/reschedule_agent.py` — the understand → check → propose loop for reschedule requests: takes the extracted intent, resolves a requested day (or searches the next few days) against real availability/capacity via `capacity_recovery.recommend()` (the same Recovery Score used for same-day recovery, not a separate heuristic), and proposes a specific new provider + date. Drives a real `agent_state_machine.RescheduleCase` (see below) — a live call honestly stops at PROPOSED, since there's no reply channel to actually get PATIENT_CONFIRMED or DECLINED back. Does not write to `appointments.csv`. Distinguishes "no provider had capacity" from "no availability data exists for that date"; with `availability.csv` now extended through Oct 28, this boundary case is rare rather than something every reschedule demo runs into. `propose_reschedule()` now accepts already-loaded dataframes and a shared `build_candidates()` cache (both optional) so a full pipeline run doesn't re-read the same CSVs and rebuild the same candidate pool once per flagged appointment — see the file's own "Perf note"
- `model/agent_state_machine.py` — the reassignment/reschedule lifecycle as an enforced state machine, not five printed strings in a row: `PENDING -> PROPOSED -> PATIENT_CONFIRMED -> BOOKED -> PROVIDER_NOTIFIED -> COMPLETED`, plus the failure branch `PROPOSED -> DECLINED -> SEARCH_ALTERNATIVE -> PROPOSED (next candidate) | ESCALATED`. Every transition is checked against an explicit allow-list — an illegal one (e.g. booking a case that was never confirmed) raises `InvalidTransition` instead of silently succeeding. Still local/in-memory, no backend, per the original scope — `python3 agent_state_machine.py` demos all four paths (happy path, decline-and-retry, candidates-exhausted, and a rejected illegal transition) with synthetic patient responses, since this dataset has no live back-and-forth to draw a real one from
- `model/economics_simulation.py` — modeled before/after impact of using the risk model to prioritize coordinator outreach on the August test period. Three inputs (intervention success rate, revenue per completed visit, coordinator hourly cost) are labeled placeholders, not measured figures — this is a simulation, not a result. Runs two 1-D sensitivity sweeps (by intervention success rate, by coordinator bandwidth) instead of reporting one point estimate, and computes a breakeven intervention success rate — see "Economics: a breakeven number, not a point estimate" below
- `model/intervention_outcome_simulation.py` — closes the Predict → Recommend → Propose loop into Predict → Recommend → Propose → simulated patient response → outcome logged. Drives every true-disruption appointment among the flagged set through the REAL `capacity_recovery.recommend()` ranking and the REAL `agent_state_machine.RescheduleCase` state machine (not a new mechanism invented for this script), with a seeded random accept/decline draw per proposed candidate and automatic retry against the next-ranked candidate on a decline. Writes a full per-case outcome log plus a bottom-up vs. top-down economics comparison — see "The intervention loop: what closing it actually showed" below for what that comparison found
- `model/generate_dashboard_data.py` — runs the full pipeline (risk model → communication signal → reassignment recommendation), writes `dashboard_data.json`, **and rewrites the `const DATA = {...}` line in `dashboard/index.html` directly** — there is no manual copy-paste step between the pipeline and the dashboard anymore
- `dashboard/index.html` — an interactive "Today's Care Operations" view: capacity-aware risk triage, patient-message signal on flagged visits, and a delay/cascade view with real detected cascades and, where a gap exists, a real recovery candidate or an honest "no coverage today". **"Simulate approval" now drives a simulated execution chain** (message drafted → slot reserved → provider notified → family notified → marked recovered), stepped through in real time using the actual recommendation/proposal data from the Python pipeline — not a boolean flip. It's still simulated (no real WhatsApp send, no real write to a scheduling system — there isn't one in this environment), but the UI now behaves like the product it's describing instead of a static mockup. State is in-memory per browser tab; refreshing resets it, same as re-running the pipeline would

## A leakage bug, found and fixed

The original model scored every appointment using `previous_no_shows` and `communication_response_rate` pulled straight from `patients.csv` — static, patient-level, end-of-dataset summaries. A June appointment was effectively scored using no-show counts that include no-shows that hadn't happened yet at prediction time. `new_patient` had the same problem (a fixed per-patient flag, not "is this literally their first visit").

`disruption_model.py` now computes rolling versions of all three — `previous_no_shows_to_date`, `response_rate_to_date`, `new_patient_to_date` — using only appointments/communications for that patient strictly before the appointment being scored, and fits both versions on the same time-based split so the effect is visible instead of silently swapped out:

| | Leaky (original) | Fixed (as-of-date) |
|---|---|---|
| ROC-AUC | 0.658 | 0.58 |
| Top 20% risk band precision | 41.8% | 33.6% |
| Top 20% risk band recall | 32.6% | 26.1% |
| `new_patient` coefficient | 0.861 | 0.10 |

The drop is the point: the leaky model was partly learning from information it wouldn't have at deployment time, and a large share of that came through the `new_patient` flag. 0.58 is a weaker but honest number. The product argument doesn't change — it's still a triage signal for scarce coordinator attention, not an autonomous decision-maker — but it now rests on a number that would hold up if someone re-ran the split correctly.

## The Recovery Score

The original capacity-recovery logic was a filter: same city, available, spare capacity, not the current provider — then one soft tie-breaker (specialization, compared against the *current* provider rather than what the visit actually required). A filter can't explain a trade-off between two acceptable candidates, and comparing to the current provider's specialization isn't the same question as "can this candidate actually deliver the requested service?". `capacity_recovery.py` now enforces service fit as a **hard eligibility filter** via an explicit `service_type → specialization` compatibility mapping, then scores every remaining eligible candidate:

```
Recovery Score =
    25 × continuity        (has this provider treated this patient before?)
  + 25 × proximity          (distance from the provider's inferred operating area to the patient)
  + 15 × remaining capacity (headroom today, as a fraction of daily_capacity)
  + 15 × schedule fit       (is there room in the SAME time-of-day slot, not just somewhere in the day?)
  +  5 × service fit        (tie-breaker among already-eligible candidates: primary vs. an acceptable secondary spec)
  - 10 × utilization penalty (ramps up past 70% booked — protects against pushing an already-full provider into a delay cascade)
```

Same-day recovery and rescheduling (`reschedule_agent.py`) now go through this one engine — reschedule proposals are ranked by the same Recovery Score, not a separate "pick whoever has the most spare capacity today" heuristic.

**Two scheduling simplifications, fixed:**
- *Same-provider rescheduling.* `recommend()` used to exclude the appointment's currently-assigned provider from every candidate pool, including when rescheduling to a different date — so "move this visit a few days later with the same provider," usually the best outcome for the patient, was never even considered. It now excludes the current provider only for same-day recovery (they're the one running late *today*); a reschedule to any other date lets them compete like any other candidate. One real case this recovers: a Mumbai wound-dressing visit that previously came back "no eligible candidate found" across a 3-day search window now correctly proposes the patient's own provider, free on 2026-09-01.
- *Slot-level capacity across recommendations in one run.* Every `recommend()` call scored candidates off a snapshot of remaining capacity and per-slot load taken once, at the start of the run — so two different flagged appointments in the same run could both be told the same provider had room in the same slot, an oversubscription the dashboard itself would never surface. `commit_recommendation()` now decrements that provider's capacity in the shared context the moment a recommendation is accepted, so the next call in the same run sees the update.
- *Per-slot capacity that didn't sum to the provider's own daily capacity.* The per-slot cap used to be `round(daily_capacity / 3)` applied identically to all three slots. Checked against `providers.csv`: `daily_capacity` there is only ever 4, 5, 6, 7 or 8, and for every value except 6 that rounding doesn't sum back to the original number — capacity=4 lost a slot (1+1+1=3), capacity=5 invented one (2+2+2=6), same under/over pattern at 7 and 8. That's 17 of the 20 providers with a slot-capacity total that silently didn't match their own daily capacity. `slot_capacities()` now floors and distributes the remainder across the three slots, so they always sum to exactly `daily_capacity`. Separately checked whether a *smarter*, non-even split was justified by the data (e.g. per-provider historical Morning/Afternoon/Evening mix) — it isn't: the actual time_slot distribution is ~33.8/33.5/32.7% overall and flat within noise (≤8 percentage points spread) for every one of the 20 providers, so an even split isn't a shortcut here, it's what the data itself supports.

Worked example, one real flagged appointment on 2026-08-29 (`python3 capacity_recovery.py`):

| Candidate | Score | Why |
|---|---|---|
| PR019 | 47.8 | 8.5 km from patient (inferred), 3 slots free, room in the same morning slot, Physiotherapy — primary fit for Physiotherapy Session |

Two data limitations, carried over honestly from the original version:
- `providers.csv` has no lat/long, only `area` (city). "Proximity" here uses each provider's own historical patient locations (mean lat/long of patients they've actually served, from `appointments.csv`) as an inferred operating centroid — a real, data-derived signal, but an approximation, not GPS ground truth. Recovery decisions for a given date now only draw on appointments strictly before that date, for both this centroid and continuity history — the original version used the full history regardless of date, a real temporal leak.
- `specialization` vs. how providers are actually assigned to `service_type` in the data still shows close to no relationship (~20-23% for every specialization, regardless of service type) — this mapping is imposed as a business rule, not learned from the data.

**A real finding from enforcing this properly:** with the hard service-fit filter in place, most flagged reassignment cases in this 20-provider synthetic dataset now come back with **zero** eligible candidates — `providers.csv` has only 1-2 providers per (area, specialization) combination, so requiring "same area + right specialization + available + spare capacity" at once is rarely satisfiable. The earlier, looser version was recommending reassignments that weren't actually valid; the honest version instead surfaces a real capacity-planning gap (too few backup providers per specialty per area) rather than papering over it with a plausible-looking but wrong recommendation. Worth a line in the case study either way it's framed.

## Cascade semantics: one definition, found and fixed

`operational.csv` ships a `delay_cascade_triggered` flag, and the dashboard's "Delay & cascade" tab used to filter on it while separately telling the coordinator, per card: *"System buffer for this slot: X min — within buffer, no cascade"* or *"exceeds buffer, next visit at risk"* — implying the buffer comparison was what decided cascade status. Checking that against the data directly: it never was. The flag turns out to be a flat `delay_minutes > 15` cutoff that ignores `buffer_minutes_needed` entirely, and no row in the dataset ever has `delay_minutes` literally exceed `buffer_minutes_needed` (the generator always leaves at least 1 minute of headroom) — so the "exceeds buffer" branch was dead code, and every real cascade card was rendering the misleading "within buffer, no cascade" line on an appointment already being shown *as* a cascade.

Fix: one rule now drives both the filter and the copy — a visit is a downstream cascade risk when its delay has burned through **at least 85% of the buffer minutes built into that slot** (`delay_minutes / buffer_minutes_needed >= 0.85`), computed per visit in `generate_dashboard_data.py` rather than read off the pre-baked flag. It's a buffer-relative threshold instead of one flat number applied to every slot regardless of how much slack it actually had, and it makes the UI copy always true for whatever it's describing.

| | Old flag (`delay_minutes > 15`) | New rule (`delay/buffer >= 0.85`) |
|---|---|---|
| Whole dataset (10,000 appts) | 583 | 521 |
| 2026-08-29 ("today" in the dashboard) | 3 | 3 |

The two rules pick a different 3 appointments for today (not a superset of each other) — the point isn't matching the old numbers, it's that there is now exactly one place a cascade is decided and exactly one sentence that explains why.

## Economics: a breakeven number, not a point estimate

The original version of `economics_simulation.py` printed one number — "recovered visits worth ~59,200" — built on two unmeasured placeholder assumptions (intervention success rate, revenue per completed visit). A single point estimate built on placeholders invites the wrong read: that 59,200 is a claim. It never was, but the script didn't make that hard to miss.

Two changes:
- Added `coordinator_hourly_cost` (also a placeholder) so the model can report **net value** (revenue recovered minus coordinator time spent), not just gross revenue recovered — a number that can go negative if the real intervention success rate turns out low enough.
- Replaced the single point with two 1-D sensitivity sweeps — by intervention success rate (15%–55%) and by coordinator bandwidth (10%–30% of visits flagged) — plus a closed-form **breakeven intervention success rate**: the real-world success rate at which coordinator time is exactly paid back.

At the base case (top 20% flagged), the **top-down model's** break-even intervention-success assumption is ~14.9%. This is an economic threshold under placeholder revenue and coordinator-cost inputs, not evidence of profitability or a predicted reduction in disruption. The capacity-constrained bottom-up simulation is negative under its own assumptions; see the comparison below. A real intervention experiment would need to measure outcomes, and provider availability must be validated before treating either model as a business case.

| Intervention success rate | Recovered visits | Net value (modeled) |
|---|---|---|
| 15% | 32 | 370 |
| 25% | 53 | 17,170 |
| 35% (base) | 74 | 33,970 |
| 45% | 95 | 50,770 |
| 55% | 117 | 68,370 |

## The intervention loop: what closing it actually showed

Every earlier version of this project's economics stopped at a single multiply: `recovered_visits = true_positives × intervention_success_rate`. That formula implicitly assumes a recoverable slot always exists the moment a patient is asked — `model/intervention_outcome_simulation.py` tests that assumption by actually running the negotiation, case by case, through the real Recovery Score ranking and the real state machine (not a new simulated mechanism) instead of skipping straight to an aggregate rate.

The result reverses the expected direction. Given multiple candidate attempts per case, the intuitive guess is that bottom-up simulation would recover MORE visits than the flat multiply (more chances to say yes). It recovers far fewer — **16 vs. 74** at the same 20%-flagged, 35%-success-rate assumptions — because **164 of the 212 true disruptions among flagged appointments (77%) have zero eligible recovery candidates at all**, before a single simulated patient response is even drawn. The bottleneck the top-down formula couldn't see is capacity, not patient willingness: `net_value_modeled` flips from **+33,970 to −12,850** once that constraint is actually modeled instead of assumed away.

| | Bottom-up (simulated per-case) | Top-down (flat multiply) |
|---|---|---|
| Recovered visits | 16 | 74 |
| Coordinator hours | 85.5 | 84.1 |
| Net value (modeled) | −12,850 | 33,970 |

This points the highest-leverage next fix at the scheduling-data gap already disclosed below (daily/slot-split capacity instead of real provider+date+time-slot availability), not at re-tuning `intervention_success_rate` — the placeholder success rate was never the thing driving the gap.

## Known limitations (intentional, and part of the case study)

- **First-visit status is not what it was assumed to be.** The README used to claim "the model over-indexes on first-time-patient status" — read off the raw logistic coefficient alone. Two problems with that: after the leakage fix, `previous_no_shows_to_date` (0.268) is the larger coefficient, not `new_patient_to_date` (0.10); and raw coefficients on differently-scaled features (a 0/1 flag vs. a count vs. a rate vs. km) aren't comparable to begin with. `model/fairness_subgroup_analysis.py` replaces that with an actual subgroup check at the top-20% operational threshold: first-time patients (n=47 in the August test set) are flagged *less* often than returning patients (10.6% vs 20.1%) and have a *lower* false-positive rate (10.3% vs 18.0%) — the opposite of the old claim. What the model IS doing wrong: it's overconfident about first-time patients specifically — mean predicted risk 25.6% against an actual disruption rate of 17.0% (a +8.6-point calibration gap, vs. +1.3 points for returning patients) — on a subgroup 66x smaller than the returning-patient one. That's a real calibration concern (thin data, overconfident predictions) worth fixing before operational use, just not the fairness direction the old claim asserted
- Risk tiering is directionally reliable in aggregate but noisy on any single simulated day, given the model's modest predictive strength (ROC-AUC ≈ 0.58 on the leakage-fixed version; this is honestly reported, not inflated)
- The main dashboard risk/cascade content is a precomputed synthetic snapshot dated **2026-08-29**; it is not live operational data. The FastAPI backend serves interactive `/api/analyze`, `/api/recover`, `/api/reschedule`, and recovery-agent APIs against bundled synthetic data. Agent case approvals/rejections persist in SQLite, but no WhatsApp, patient/provider notification, real booking, or scheduling-system write occurs. The legacy dashboard "Simulate approval" animation remains browser-side only.
- Communication intelligence's *production* path is now `hybrid_extraction.extract_intent_hybrid()`, not the bare rule-based `extract_intent()`: rules alone generalize poorly (100% agreement against its own training labels, but only **53.4% intent accuracy, macro F1 0.632** on the 103-message held-out set — overfit to its 10 training templates) and its temporal parser has a related limitation (tags any weekday/relative-day mention regardless of whether the patient is confirming or ruling that day out, capping temporal accuracy at 90.3%). This is a **rule-first hybrid with LLM fallback**, not "confidence-gated" — the gate is the rule-based side's own binary abstention ("Unclear"), not a calibrated confidence score, and the rule-based side's honest 58.3% routing rate on held-out messages is exactly what that gate uses as its routing signal, not a weakness to hide: rules alone resolve the other 35% for free, an LLM fallback is only ever invoked on the 58.3% share, and 13.6% of the full set still can't be resolved by either side and gets escalated to a human rather than guessed. That still leaves a real, honest gap: even the hybrid path (98.1% intent accuracy on the same held-out set — see `hybrid_extraction.py`) has 2 misclassifications, all cases where the rule-based gate was confidently *wrong* rather than abstaining — i.e. abstention isn't a perfectly reliable proxy for correctness, which is a separate finding from the abstention rate itself. **What's still genuinely unmeasured, on purpose:** cost-per-message and latency for the LLM fallback (`hybrid_extraction.default_llm_call()` is wired for the interactive Gemini API with an optional Anthropic fallback, but this runtime provider path has not been run against a metered key here — see `model/llm_vs_baseline_eval.py` for the same disclosed limitation), reliability/uptime of that call in production, model-version stability over time, and data-privacy handling of patient messages sent to an external API. These are treated as open production-validation requirements, not claimed results — see `EXPERIMENT_DESIGN.md`
- The economics module is a labeled simulation with placeholder assumptions, not a validated business result — no real intervention was run. `model/intervention_outcome_simulation.py` now logs a per-case simulated outcome (see above), which is a real artifact in the sense that every case is actually driven through the real ranking + state machine — but the accept/decline draw itself is still a coin flip at the same unmeasured 35% placeholder rate, not a real patient response
- Stage 2 (`model/disruption_type_model.py`), a diagnostic evaluated on the TRUE disruption label (not Stage 1's predicted flag): distinguishing No-Show from Cancelled, among appointments that actually disrupted, comes back at **ROC-AUC 0.521 — essentially chance**. The 6 patient/booking-side features that drive Stage 1 don't separate WHY a visit was disrupted, only THAT it was; the model collapses to predicting the majority class. Reported as a negative result rather than left unexamined. Separately, Rescheduled-status appointments (4.4% of the August test set) currently fall outside the disruption target entirely — counted as "not disrupted," lumped in with Completed — a target-definition simplification, not a hidden bug
- `requirements.txt` includes the core offline packages (`pandas`, `numpy`, `scikit-learn`) plus the FastAPI runtime (`fastapi`, `uvicorn`, `requests`). The optional `anthropic` SDK is only needed for that live fallback path and the metered API evaluator; the default offline pipeline does not require it and does not call external LLM APIs.
- `availability.csv`'s extension past Aug 29 is generated, not observed: each provider's future availability is drawn using that same provider's own historical availability rate (e.g. contractual providers ~50-60%, full-time providers ~90%+), not real future scheduling data

## Product and engineering documentation

The `docs/` directory documents product scope and delivery status: [PRD](PRD.md), [user stories](USER_STORIES.md), [product decisions](PRODUCT_DECISIONS.md), [assumptions](ASSUMPTIONS.md), [UAT scenarios](UAT.md), [roadmap](PRODUCT_ROADMAP.md), [rollout and experiment plan](ROLLOUT_AND_EXPERIMENT.md), and [technical notes](TECHNICAL_NOTES.md). UAT entries describe expected behaviour; the test report from a particular run determines what actually passed.

## Full case study

The complete product narrative — problem framing, autonomy-level framework, prioritization decisions, and simulated impact — lives in the accompanying case study deck (linked from the portfolio).

## Experiment design

`EXPERIMENT_DESIGN.md` specs the RCT that would replace the placeholder assumptions in `economics_simulation.py` with a measured result — sample size, guardrail metrics, and what a null result would mean. Not run; this is the design, not a result.

### Recovery agent safety and evaluation

CareOps includes a bounded recovery-agent prototype with persistent, approval-gated proposal records. The agent does not execute bookings or send messages. It fails closed when recovery search errors occur, and candidate selection excludes providers whose target time slot is already full.

Run the offline synthetic benchmark with `python model/evaluate_agent.py` and the test suite with `pytest -q`. See `docs/AGENT_EVALUATION.md` and `docs/APPROVAL_LIFECYCLE.md` for methodology and limitations.

### Simulated recovery execution (Phase 6)

The approval lifecycle now includes `POST /api/agent/cases/{case_id}/execute`. After coordinator approval, CareOps revalidates the exact proposed provider/date against the bundled synthetic recovery engine and records an idempotent simulated execution. The dashboard exposes approve, reject, and execute-simulation actions for the agent result.

This remains a simulation: no external appointment is booked, no capacity is reserved in a live scheduling system, and no patient/provider messages are sent. Repeated execution calls for the same case return the same simulation record. See `docs/APPROVAL_LIFECYCLE.md` for state transitions, API details, tests, and production gaps.
## Extraction strategy comparison

Compare the rules-only extractor, saved blind LLM predictions, and rules-first hybrid on the same synthetic labeled messages:

```bash
python model/compare_extraction_strategies.py
```

See [`docs/EXTRACTION_STRATEGY_COMPARISON.md`](EXTRACTION_STRATEGY_COMPARISON.md) for the latest snapshot and methodological limitations. The saved LLM predictions are not a live API benchmark; cost and latency are not measured for that path.

### Frozen end-to-end holdout (Phase 10)

Run `python model/evaluate_agent_holdout.py` for the frozen 30-case synthetic holdout. The evaluator reports intent accuracy, safe disposition, per-category results, local offline latency, and revalidates any proposal against the bundled synthetic availability rules. The suite is intended for regression tracking and should not be used to tune parser rules; it is author-created, not independently sampled, and external LLM calls are disabled.

Latest Phase 12/13 local run: **83.33% intent accuracy and 83.33% expected-disposition pass rate (25/30)**. All **5/5 proposals** generated in that run passed revalidation against the current synthetic availability rules. This is a small, author-created synthetic holdout, not an independent estimate of real-world performance. The prior Phase 10/11 snapshot was 23/30 (76.67%); it is retained only as historical context. Do not compare these small-set changes as statistically reliable evidence of generalisation. Local p50/p95 timings exclude hosted API/network latency and are not production SLAs. The current report is `data/evaluation/latest_agent_holdout_eval.json`; methodology and boundaries are in `docs/PHASE10_HOLDOUT_EVALUATION.md` and `PHASE13_EVALUATION.md`.

## Phase 13: Parser safety audit

Run `python model/evaluate_parser_safety.py` to generate a confusion matrix and separate counts for false confirmations, false cancellations, and missed intents across the mutable development suite and frozen holdout. Results and caveats are documented in [`PHASE13_EVALUATION.md`](../PHASE13_EVALUATION.md). This is a synthetic offline diagnostic, not a production safety certification.
