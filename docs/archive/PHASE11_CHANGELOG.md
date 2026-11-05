# Phase 11 — Parser robustness and frozen-holdout regression

## Changes
- Added common rescheduling paraphrases: “another time/date”, “change the timing”, “move the visit”, and “move the appointment”.
- Added confirmation phrasing for home availability and scheduled attendance.
- Added a conservative deferral guard so “confirm later” / “will let you know” is treated as unclear rather than as a present confirmation.
- Added regression tests for these phrases and for uncertain future changes. Ambiguous messages should remain non-actionable and must not set `cancel_current`.
- Added the Phase 11 challenge-evaluation report at `data/evaluation/latest_agent_challenge_v4_eval_phase11.json`.

## Validation
- Full test suite: **77 passed**.
- Challenge v4: **15/15 intent classifications and 15/15 expected dispositions passed**. This is a small, author-created synthetic suite and was already passing before these changes; it is a regression check, not evidence of a measured improvement on that suite.
- Frozen holdout v1: **23/30 intent classifications and 23/30 expected dispositions passed (76.67%)**; all 5 generated proposals passed revalidation. The frozen holdout file was not edited and was not used to select parser changes.

## Limitations
- All test messages and evaluation scenarios are synthetic and manually authored.
- The holdout remains at 76.67%; no improvement is claimed there. Remaining failures across cancellation, confirmation, and direct rescheduling categories require future work using a separate development set and preferably real coordinator feedback.
- The LLM is disabled in these offline evaluations. No live model quality, hosted latency, or cost was measured.
- This remains a prototype. No real appointment is cancelled, booked, or rescheduled.
