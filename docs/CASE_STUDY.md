# CareOps: one-page case study

**An AI operations copilot that helps a home-care coordinator fix visits before they fail, without letting the AI act unchecked.**
[Live demo](https://careops-live-demo-18xj.onrender.com/) · [73-second video](media/careops-demo.mp4) · All data synthetic

---

## The problem

I saw this while working in Indian home care. A coordinator runs dozens of visits a day with contractual nurses and companions. Visits fail in predictable ways: the provider is running late, a family member writes "aaj nahi ho payega, kal?" on WhatsApp, or a nurse drops out an hour before. Each one means reading the message, finding someone free and suitable, and messaging everyone, all by hand. Missed visits hurt elderly patients most.

**User:** the operations coordinator, not the family or the nurse.
**Job to be done:** "Tell me which visits need me today, and give me a safe fix I can approve in one tap."

## What I built

| Capability | What it does |
|---|---|
| Risk ranking | Flags the ~20% of visits most likely to go wrong, with plain-language reasons, sized to what one coordinator can review |
| Message understanding | Reads English, Hindi and Hinglish messages: confirm, reschedule, cancel, or unclear |
| Recovery | Proposes a replacement provider or a new date, with the reasons, using hard eligibility rules first |
| Voice visit reports | Turns a caregiver's voice note into a structured report and a family update, and holds risky updates for review |
| Human approval | Nothing is booked or sent without the coordinator |

## Key product decisions

1. **Rules first, AI only when the rules abstain.** Rules are free, instant and predictable; the model handles only what they can't.
2. **Optimise for the worst error, not average accuracy.** A false "Confirm" means a coordinator thinks a visit is on when the family said no. I tracked false confirmations as their own metric.
3. **Checks after the model.** A vital sign must actually appear in the caregiver's note; red flags (a fall, low sugar) always go to a human. The model can propose, never release.
4. **Fail closed.** If the model is unavailable or its output is invalid, the case goes to a coordinator instead of guessing.
5. **Size the flagged list to coordinator capacity,** not to a probability cutoff, so the list stays reviewable in a day.

## Results (synthetic data, real model runs)

| Metric | Result |
|---|---|
| Message understanding on a fresh 39-message holdout (frozen before the final prompt) | 77% → **97.4%** across three prompt versions |
| False confirmations across all saved runs | **8 → 0** with prompt v3 plus a guardrail that can only escalate |
| Wrong or invented vitals reaching a family (30 Hinglish voice notes) | **0** |
| Cost and speed | ₹0 on free tiers; about 1.2 s per message |

## What I learned

- **A prompt fix can make the dangerous error worse.** Defining the labels raised accuracy from 77% to 95% but introduced false confirmations ("Thanks." read as "visit confirmed"). Average accuracy hid it; the error-type metric caught it.
- **A smaller model can look equal until fresh data.** gpt-oss-20b matched the larger model on two test sets, then dropped to 92.3% on a clean one.
- **Real model runs find gaps that perfect-model tests don't.** In "Sugar 62 … later 88", the model kept only the normal 88. Scanning every reading in the note fixed it.
- **Honest numbers over flattering ones.** Fixing a data leak dropped the risk model from 0.658 to 0.58 ROC-AUC. I reported the lower number.

## What's next

1. Test with 3 to 5 real coordinators ([testing kit](USER_TESTING.md)) and measure time to resolve a disrupted visit.
2. Measure the guardrail on a third holdout frozen before any further change.
3. Turn on live road ETAs and check whether they change the recommended provider.
4. Calibrate the risk model for first-time patients.

## How this was built

I defined the problem, users, product decisions, evaluation design and safety rules, and reviewed every change. The code was written with Claude as an AI pair programmer. Tests, evaluation data and results are all in this repository.
