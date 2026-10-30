# CareOps — AI operations copilot for home healthcare

**When a home-care visit is about to fail, CareOps reads the family's message, finds a safe replacement provider, and drafts the fix — then waits for a human coordinator to approve it.**

Built for the realities of India's home-care market: contractual providers with day-to-day availability, families who message in English, Hindi and Hinglish, and elderly patients who can't afford a missed visit.

> All data is synthetic. This is a product portfolio project: it shows problem framing, evaluation and AI-product judgment, not production outcomes.

---

## How it works

```
Family message ──► Understand ──► Find recovery options ──► Propose ──► Coordinator approves
"aaj nahi aa       rules first,     hard eligibility filter,   draft fix    nothing is booked or
 payenge, kal?"    LLM only when    then a weighted Recovery    + reasons    sent without a human
                   rules abstain    Score (continuity, ETA,
                                    capacity, slot fit, load)
```

| Step | What it does | Why it's built this way |
|---|---|---|
| **Understand** | Extracts intent, requested day, reason and whether the current visit is being dropped | Rules are free and instant, so the LLM is called only when they abstain. A deterministic guardrail can send any Confirm to a human; anything unclear escalates instead of guessing |
| **Recover** | Ranks eligible replacement providers with a plain-language "why" | Service fit is a hard filter, not a score, so an ineligible provider can never win on proximity |
| **Approve** | Persists every proposal and decision with an audit trail | High-stakes actions stay human; the agent fails closed on errors |

## Results (synthetic, author-labelled data)

**Message understanding: real API runs on Groq's free tier** ([full write-up](docs/LLM_EVALUATION.md))

| On a fresh 39-message holdout, frozen before the final prompt existed | Accuracy | False confirmations |
|---|---|---|
| Rule-based parser alone (103-message set) | 53.4% | — |
| gpt-oss-120b, prompt v1 (labels not defined) | 76.9% | 0 |
| gpt-oss-120b, prompt v2 (labels defined) | 94.9% | 2 |
| gpt-oss-120b, prompt v3 (Confirm rule fixed) | **97.4%** | 1 |
| gpt-oss-120b, prompt v3 + deterministic Confirm guardrail | **100%** ¹ | **0** |

- **The prompt fix created a worse error.** Defining the labels lifted accuracy from 77% to 95%, but introduced false confirmations ("Thanks." read as "visit confirmed"). A targeted v3 fixed most of them; a guardrail that can only ever send a Confirm to a human removed the rest. Across all 10 saved runs, false confirmations went from 8 to 0, at the cost of one extra human review per 103 messages.
- **The smaller model looked as good, until fresh data said otherwise.** gpt-oss-20b matched 120B on the first two sets, then fell to 92.3% on the clean one, including reading "Monday rakh lo" (move it to Monday) as Confirm.
- About 1.2 s per message (p50) and ₹0 spent.

¹ The guardrail's rules were motivated by errors on this set, so its 100% is optimistic until measured on a new holdout.

**Rest of the system**

| What was measured | Result |
|---|---|
| Recovery agent on a frozen 30-case holdout (offline rules path) | **25/30** correct dispositions, **0** false cancellations, all 5 proposals passed revalidation |
| Disruption-risk model after fixing a data-leakage bug | ROC-AUC fell from 0.658 to **0.58**, reported honestly rather than kept inflated |

## What I'd change next

- Define `cancel_current` operationally: most of the model's "errors" on it are a labelling ambiguity, not model mistakes.
- Measure the guardrail on a third holdout frozen before any further change.
- Replace inferred distance with real road travel time in the Recovery Score.
- Calibrate the risk model for first-time patients, where it is overconfident (+8.6-point calibration gap on a small subgroup).

## Try it

```bash
git clone https://github.com/Ritikajaiswal2707/careops.git && cd careops
pip install -r requirements.txt
uvicorn main:app --reload          # open http://127.0.0.1:8000
python -m pytest -q                # full test suite
```

The dashboard's main views show a **precomputed synthetic snapshot**; the "Try the AI" tab calls the live FastAPI backend. The approval animation is a **browser-side simulation**: nothing is booked or sent. A Render config (`render.yaml`) deploys a read-only public demo with external LLM calls disabled; the hosted URL was not verified for this update.

## Go deeper

- [Technical deep dive](docs/DEEP_DIVE.md) — every module, evaluation, bug found and limitation
- [PRD](docs/PRD.md) · [Product decisions](docs/PRODUCT_DECISIONS.md) · [Roadmap](docs/PRODUCT_ROADMAP.md) · [Experiment design](EXPERIMENT_DESIGN.md)
- [Agent evaluation](docs/AGENT_EVALUATION.md) · [Parser safety audit](PHASE13_EVALUATION.md) · [Approval lifecycle](docs/APPROVAL_LIFECYCLE.md)
