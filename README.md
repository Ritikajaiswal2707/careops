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
| **Understand** | Extracts intent, requested day, reason and whether the current visit is being dropped | Rules are free and instant, so the LLM is called only when they abstain. Anything still unclear escalates to a human instead of guessing |
| **Recover** | Ranks eligible replacement providers with a plain-language "why" | Service fit is a hard filter, not a score, so an ineligible provider can never win on proximity |
| **Approve** | Persists every proposal and decision with an audit trail | High-stakes actions stay human; the agent fails closed on errors |

## Results (synthetic, author-labelled data)

| What was measured | Result |
|---|---|
| Rule-based parser on 103 held-out Hinglish/English messages | **53.4%** intent accuracy — it memorised its 10 training templates |
| Rule-first hybrid with LLM fallback, same set | **98.1%** intent accuracy, with **13.6%** escalated to a human rather than guessed ¹ |
| Recovery agent on a frozen 30-case holdout | **25/30** correct dispositions, **0** false cancellations, all 5 proposals passed revalidation |
| Disruption-risk model after fixing a data-leakage bug | ROC-AUC fell from 0.658 to **0.58** — reported honestly rather than kept inflated |
| Metered LLM run (Gemini, free tier) | Runner ready in [`model/gemini_eval.py`](model/gemini_eval.py); result pending |

¹ The LLM side of this number came from blind predictions without a metered API call. The Gemini run above replaces it with real accuracy, latency and token counts.

## What I'd change next

- Replace inferred distance with real road travel time in the Recovery Score.
- Calibrate the risk model for first-time patients, where it is overconfident (+8.6-point calibration gap on a small subgroup).
- Add a gate check on the hybrid parser: both of its errors were the rules being confidently wrong instead of abstaining.

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
