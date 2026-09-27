# AI Care Operations Copilot

A portfolio project exploring how AI can predict, explain, and help recover from disruptions in home healthcare delivery — with a specific focus on the operational realities of India's home-care market: contractual/gig service providers with variable day-to-day availability, elderly patients who often can't self-report precise location, and delay cascades caused by traffic, weather, or overruns.

**This is a PM portfolio project.** All data is synthetic/simulated. It exists to demonstrate product thinking — problem framing, prioritization, tradeoff decisions, and AI-product judgment — not to claim production-grade engineering or real-world validated outcomes.

## Quickstart

```
git clone <repo>
cd careops
python run.py          # macOS / Linux / Windows — anywhere Python is on PATH
```

```
./run.sh                # macOS / Linux / Git Bash / WSL
```

```
.\run.ps1                # Windows PowerShell
```

All three run the identical pipeline in dependency order and are safe to run from any working directory — every script resolves its own data/output paths from its own file location, not the caller's `cwd`, so `python model/disruption_model.py` from the repo root works exactly the same as running it from inside `model/`. The pipeline: installs the three pinned dependencies (`pandas`, `numpy`, `scikit-learn`), trains the risk model, runs the subgroup fairness check and the Stage 2 disruption-type model, runs communication extraction, runs the LLM-vs-baseline eval (rule-based half only, unless `ANTHROPIC_API_KEY` is set and `anthropic` is installed — both optional, see `requirements.txt`), prints the Recovery Score worked example, demos the agent state machine, runs the economics simulation, and finally runs `generate_dashboard_data.py`, which writes `model/dashboard_data.json` and rewrites `dashboard/index.html`'s embedded data in place. Open `dashboard/index.html` in a browser afterward — nothing else to build or serve. Already have the deps installed? Add `--no-install` (`python run.py --no-install`, `./run.sh --no-install`) or `-NoInstall` (`.\run.ps1 -NoInstall`) to skip the pip step.

## Structure

- `data/` — synthetic 6-table dataset (providers, patients, appointments, operational, communications, availability) modeling a home-care operation across 5 Indian cities, 20 clinicians, 2,000 patients, 10,000 appointments. `availability.csv` covers Jun 1 – Oct 28 (extended 60 days past the original Aug 29 cutoff — see note below). `data/communication_eval.json` is the 103-message held-out set used by `model/llm_vs_baseline_eval.py` — a real data artifact now, not embedded in the evaluator script
- `model/disruption_model.py` — logistic regression predicting visit disruption risk (time-based train/test split: train Jun-Jul, test Aug), plus a rule-based plain-language explanation layer and threshold/precision-recall tradeoff analysis. **Fits and reports both a leaky and a leakage-fixed version side by side** (see "A leakage bug, found and fixed" below) — the fixed version is what the dashboard actually runs on
- `model/fairness_subgroup_analysis.py` — real subgroup check (precision, recall, false-positive rate, calibration) split by first-time vs. returning patient, at the top-20% operational threshold — see "First-visit status" under Known limitations below for what it actually found
- `model/disruption_type_model.py` — a Stage 2 diagnostic model, trained and evaluated on appointments filtered by the TRUE status label (not conditioned on Stage 1's predicted flag — see the file's own "Naming note" for why that distinction matters), predicting No-Show vs. Cancelled specifically (the binary target treats them identically); also documents that Rescheduled-status appointments currently fall outside the disruption target entirely, counted as "not disrupted"
- `model/communication_intelligence.py` — rule/keyword-based extractor that turns raw patient messages (`communications.csv`, mixed English/Hinglish) into structured signal: intent, preferred day, urgency, reason. Not a live LLM call — no API key is wired into this environment. Agrees with the dataset's own intent labels 100% of the time, but that's measured against its own training templates — see `model/llm_vs_baseline_eval.py` below for what actually happens on unseen phrasing
- `model/llm_vs_baseline_eval.py` — the real generalization test the 100%-agreement number can't provide: the 103-message held-out set in `data/communication_eval.json`, hand-labeled with the *full* gold structure (intent, temporal signal, reason — not just intent), written independently of `communications.csv`'s 10 templates (typos, Hindi in Devanagari script, code-switching, sarcasm, compound requests, indirect phrasing, no keyword overlap in several cases on purpose). **The rule-based extractor scores 44.7% intent accuracy (macro F1 0.57), 91.3% temporal-field accuracy, 98.1% reason accuracy, and abstains (predicts "Unclear") on 65% of messages** — it's a lookup table for phrasing that resembles its 10 training templates, and its single biggest failure mode is casual/minimal confirmations ("ok", "k", "yep all good") that don't contain any of its exact `CONFIRM_WORDS` phrases. The script also calls the Anthropic API for a head-to-head structured-JSON LLM comparison (same 5 metrics, plus JSON validity and cost/latency per message) when `ANTHROPIC_API_KEY` is set — not set in this environment, so that side hasn't been run; no LLM number is claimed or estimated here. The `anthropic` package is an **optional** dependency (see `requirements.txt`) — the default pipeline never needs it; only install it if you're actually running the LLM half
- `model/capacity_recovery.py` — scores every eligible candidate provider on a weighted **Recovery Score** (continuity + proximity + remaining capacity + same-time-slot fit + service fit, minus a utilization penalty) and returns the ranked list with a plain-language "why" for each — a trade-off, not just a filtered pool. See "The Recovery Score" below
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

At the base case (top 20% flagged), that breakeven point is **~14.9%** — well below the 35% placeholder this project has been assuming. That's the one honest headline number here: the modeled ROI isn't fragile to getting the placeholder exactly right, it only needs a real intervention to clear a fairly low bar. That's also exactly the number `EXPERIMENT_DESIGN.md`'s proposed RCT would go measure — a breakeven threshold is a testable claim; "59,200 recovered" was not.

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
- The pipeline is reproducible, not live: `generate_dashboard_data.py` is run manually to produce a fresh snapshot. There is no backend serving live predictions on request, and no real actions are sent (no WhatsApp, no scheduling-system writes) — the dashboard's "Approve" button changes local UI state only
- Communication intelligence is rule-based, not an LLM call, and generalizes poorly: 100% agreement against its own training labels, but only **44.7% intent accuracy (macro F1 0.57)** on the 103-message held-out set in `model/llm_vs_baseline_eval.py` — it's overfit to its 10 training templates, not a system that understands language, and abstains on 65% of held-out messages rather than guessing wrong (a safer failure mode than it sounds, but still means most messages need a human to actually read them). That script also scores temporal-field accuracy (91.3%), reason accuracy (98.1%), and is wired to call an LLM for a real head-to-head comparison — including JSON validity and cost/latency per message — but no `ANTHROPIC_API_KEY` is set in this environment, so the LLM side hasn't actually been run
- The economics module is a labeled simulation with placeholder assumptions, not a validated business result — no real intervention was run. `model/intervention_outcome_simulation.py` now logs a per-case simulated outcome (see above), which is a real artifact in the sense that every case is actually driven through the real ranking + state machine — but the accept/decline draw itself is still a coin flip at the same unmeasured 35% placeholder rate, not a real patient response
- Stage 2 (`model/disruption_type_model.py`), a diagnostic evaluated on the TRUE disruption label (not Stage 1's predicted flag): distinguishing No-Show from Cancelled, among appointments that actually disrupted, comes back at **ROC-AUC 0.521 — essentially chance**. The 6 patient/booking-side features that drive Stage 1 don't separate WHY a visit was disrupted, only THAT it was; the model collapses to predicting the majority class. Reported as a negative result rather than left unexamined. Separately, Rescheduled-status appointments (4.4% of the August test set) currently fall outside the disruption target entirely — counted as "not disrupted," lumped in with Completed — a target-definition simplification, not a hidden bug
- `requirements.txt` only pins the three packages the default pipeline needs (`pandas`, `numpy`, `scikit-learn`). `anthropic` is called out as an optional install, only needed for the LLM half of `model/llm_vs_baseline_eval.py` — running `run.py`/`run.sh`/`run.ps1` never requires it
- `availability.csv`'s extension past Aug 29 is generated, not observed: each provider's future availability is drawn using that same provider's own historical availability rate (e.g. contractual providers ~50-60%, full-time providers ~90%+), not real future scheduling data

## Full case study

The complete product narrative — problem framing, autonomy-level framework, prioritization decisions, and simulated impact — lives in the accompanying case study deck (linked from the portfolio).

## Experiment design

`EXPERIMENT_DESIGN.md` specs the RCT that would replace the placeholder assumptions in `economics_simulation.py` with a measured result — sample size, guardrail metrics, and what a null result would mean. Not run; this is the design, not a result.
