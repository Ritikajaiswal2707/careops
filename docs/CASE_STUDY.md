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
| Needs you | The visits that need the coordinator today, by person and time, with a plain reason and a suggested action |
| Message understanding | Reads English, Hindi and Hinglish messages: confirm, reschedule, cancel, or unclear |
| Ready-to-send replies | Drafts the WhatsApp message to the family in Hinglish or English for every suggested action; the coordinator edits and sends it |
| Recovery | Proposes a replacement nurse or a new date, with the reasons, using hard eligibility rules first, and never dead-ends |
| Voice visit reports | Turns a caregiver's voice note into a structured report and a family update, and holds risky updates for review |
| Human approval | Nothing is booked or sent without the coordinator |

## Key product decisions

1. **Rules first, AI only when the rules abstain.** Rules are free, instant and predictable; the model handles only what they can't.
2. **Optimise for the worst error, not average accuracy.** A false "Confirm" means a coordinator thinks a visit is on when the family said no. I tracked false confirmations as their own metric.
3. **Checks after the model.** A vital sign must actually appear in the caregiver's note; red flags (a fall, low sugar) always go to a human. The model can propose, never release.
4. **Fail closed.** If the model is unavailable or its output is invalid, the case goes to a coordinator instead of guessing.
5. **Size the flagged list to coordinator capacity,** not to a probability cutoff, so the list stays reviewable in a day.

## Testing it as five coordinators

Before real user sessions, I used the product as five coordinator personas: a field coordinator at a nursing agency, an elder-companionship coordinator, a hospital clinical lead, a night-shift coordinator and an agency owner. Average usefulness was about 5 out of 10, well below the quality of the AI underneath. Three findings mattered most:

1. **Trust breaks on small words.** Approving a visit with no backup nurse said "handled". A coordinator would assume the visit was covered. It now says "Escalated · unassigned".
2. **Order of operations is a safety issue.** A reschedule told the nurse before the family agreed. Now the family is asked first.
3. **The AI was not the bottleneck; the last step was.** Every suggestion still needed a hand-typed WhatsApp message, so each action now comes with an editable Hinglish or English draft.

I also learned that a disruption usually arrives per nurse ("Sunita is sick today"), not per visit, so I added a first version of that flow: pick the nurse who is out and CareOps suggests cover for all her visits without overloading anyone. It also exposed a real capacity problem in the data: for most nurses, fewer than half of their visits can be covered the same day.

A second round with ten reviewers (a recruiter, a senior PM, an AI PM interviewer, an engineer, a data scientist, a designer, an agency founder, an NRI son, a nurse and a doctor) led to clearer framing (a portfolio banner, "where AI is used"), an accessibility pass (no automated WCAG 2 AA violations), cited thresholds, a check that family updates never add medical words the caregiver did not use, confidence intervals on every headline number, and a calibration plot for the risk model.

A third pass caught a framing problem: the page's first line described the product ("CareOps reads family messages…"). That is a pitch for visitors, not information for an operator who already knows the tool. The page now has a coordinator's view whose first line is today's work: how many families wrote in, how many visits have no backup nurse, how many nurses are running late.

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
2. Ask them whether the "nurse is out today" flow matches how sick calls really arrive.
3. Measure the guardrail on a third holdout frozen before any further change.
4. Turn on live road ETAs and check whether they change the recommended provider.
5. Calibrate the risk model for first-time patients.

## How this was built

I defined the problem, users, product decisions, evaluation design and safety rules, and reviewed every change. The code was written with Claude as an AI pair programmer. Tests, evaluation data and results are all in this repository.
