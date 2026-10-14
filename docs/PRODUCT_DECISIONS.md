# CareOps — Product Decision Log

## Decision 01 — Triage instead of autonomous prediction
**Situation:** The risk model is useful but modestly predictive.
**Options:** (1) automatically act on predictions, (2) show all predictions, (3) prioritize a fixed proportion for coordinator attention.
**Decision:** Prioritize the top 20%.
**Why:** Coordinator attention is constrained. The system optimizes for better use of human attention rather than perfect prediction.

## Decision 02 — Rank-based tiers instead of probability threshold
**Situation:** A fixed probability threshold became unreliable after correcting data leakage.
**Decision:** Use rank-based High / Medium / Low tiers.
**Why:** The coordinator needs a predictable workload rather than an arbitrary probability cutoff.

## Decision 03 — Simple model instead of more complex ML
**Situation:** The signal is modest and explanations matter.
**Decision:** Use logistic regression.
**Why:** Easier to explain and maintain; additional complexity did not justify itself without stronger signal.

## Decision 04 — Rule-first hybrid instead of LLM everywhere
**Situation:** Many messages can be handled deterministically.
**Decision:** Rules first, then LLM fallback.
**Why:** Avoid unnecessary cost and latency while retaining flexibility for ambiguous language.
**Status:** The rule-first runtime fallback is implemented in `model/hybrid_extraction.py` and is used by the interactive API. The 103-message held-out hybrid score (97.1%) reuses saved blind offline predictions; it is not a metered live-API benchmark. Live provider quality, cost, and latency remain unmeasured.

## Decision 05 — Human escalation instead of guessing
**Situation:** Healthcare coordination contains consequential actions.
**Decision:** Escalate ambiguity.
**Why:** A visible uncertainty is preferable to a confident but incorrect action.

## Decision 06 — Hard filters + weighted score
**Situation:** Not every provider is operationally eligible.
**Decision:** Separate hard constraints from soft ranking.
**Why:** A provider who scores highly but cannot perform the service must never be recommended.

## Decision 07 — Preserve provider continuity where possible
**Situation:** Continuity is valuable in recurring care.
**Decision:** Continuity is a preference, not an absolute rule.
**Why:** Availability and service capability can override continuity.

## Decision 08 — Stop the agent at PROPOSED
**Situation:** There is no real messaging/scheduling write-back.
**Decision:** Do not simulate real confirmation.
**Why:** The product should be explicit about what the system has and has not actually executed.

## Decision 09 — Capacity before model sophistication
**Situation:** The case-by-case simulation showed 164 of 212 true disruptions among flagged appointments (77%) had no eligible recovery option.
**Decision:** Prioritize provider availability and capacity data before further model sophistication.
**Why:** Improving prediction does not solve a case that has no feasible recovery path.

## Decision 10 — Publish negative results
**Situation:** Some models and assumptions failed (e.g. Stage 2 No-Show vs Cancelled at ROC-AUC 0.521; leakage-fixed AUC dropping from 0.658 to 0.58).
**Decision:** Keep the negative results in the case study.
**Why:** They changed the product direction and demonstrate evidence-driven decision making.
