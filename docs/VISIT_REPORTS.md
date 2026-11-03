# Voice visit reports

A caregiver ends a visit by sending a voice note in English, Hindi or Hinglish. CareOps turns it into a structured report for the coordinator and a short update for the family, which is held back whenever a human should look first.

```
voice note ──► Whisper ──► LLM structuring ──► deterministic safety checks ──► coordinator / family
               (Groq,       vitals, medicines,  grounding + red flags;          summary released only
                free)       observations,       can only make the report         when no review is needed
                            concerns, summary   more cautious
```

Code: [`model/visit_report.py`](../model/visit_report.py) · API: `POST /api/visit-report` (text) and `POST /api/visit-report/audio` (voice note, up to 10 MB).

## Why the safety checks sit after the model

The intent work showed that a prompt is not a safety guarantee, so the same pattern is applied here. The model writes a draft; deterministic code decides what is trusted.

| Check | What it does | Failure it prevents |
|---|---|---|
| **Grounding** | A vital value counts only if that number appears in the note. Anything else moves to `unverified_vitals` and the report goes to review. | The model "filling in" a normal-looking BP or SpO₂ that was never measured |
| **Red flags** | Configurable thresholds (e.g. SpO₂ below 92, systolic 180+) and keywords (a fall, chest pain, breathlessness, confusion) force review, whatever the model says. Unverified values are checked too, and so is every reading stated in the note, not just the one the model reported. | A worrying visit reaching the family as a cheerful update |
| **Summary hold** | `family_summary` is released only when no review is needed; the draft is kept for the coordinator. | Unchecked text going to a family |
| **Fail closed** | No LLM configured, invalid JSON, or external calls disabled → the report asks for review. | Silent failures |

The thresholds are illustrative routing rules for a portfolio demo, not clinical guidance. They only decide whether a human sees the report first.

## Evaluation

[`data/evaluation/visit_report_eval_v1.json`](../data/evaluation/visit_report_eval_v1.json): 30 synthetic Hinglish notes, frozen and SHA-256 pinned, labelled with today's vitals and whether a coordinator should see the note first. The set includes deliberate traps:

- notes with **no vitals at all** (the model must not invent any)
- **spoken numbers** ("BP ek sau bees by assi")
- **distractor numbers** (room number, age, last week's BP, tablet counts)
- **red flags** by value and by keyword

Run it with `python model/visit_report_eval.py` (Groq free tier). It reports raw model output and post-safety output side by side: invented vitals, wrong values released, review recall (must be 100%), and how many routine notes were sent to review anyway.

### Baseline: what the safety layer costs, measured with a perfect model

Feeding the safety layer the gold answers isolates its own behaviour:

| | Result |
|---|---|
| Invented vitals released | 0 |
| Wrong values released | 0 |
| Review recall | 100% (all 8 notes needing review flagged) |
| Routine notes sent to review anyway | **18%**, all four spoken-number notes |

The cost is specific and known: "ek sau bees" contains no digits, so grounding cannot verify the model's 120 and plays safe. The next iteration, after measuring the real model, is to let the grounding check read spoken Hindi and English numbers.

### Real model: gpt-oss-120b on Groq (free tier)

| | Raw model | Safety v1.0 | Safety v1.1 |
|---|---|---|---|
| Vital field accuracy | 97.2% | 92.2% | 92.2% |
| Invented vitals (value where the note gave none) | **0** | 0 | 0 |
| Notes needing review that were flagged | — | 87.5% (7/8) | **100% (8/8)** |
| Routine notes sent to review anyway | — | 18% | 18% |
| Wrong or invented vitals reaching a family | — | **1** | **0** |

Saved run: `data/evaluation/visit_report_openai_gpt-oss-120b_v1_eval.json` (recorded with safety v1.0). The v1.1 column is reproduced offline from the same raw outputs with `python model/visit_report_eval.py --rescore <file>`.

**What the real run showed**

1. **A missed red flag.** "Sugar 62 tha … 15 min baad 88 aaya": the model reported only the later, normal reading, so v1.0 checked 88, found nothing, and would have released a cheerful family update after a low-sugar episode. **Fix (v1.1):** a deterministic scan of every reading stated next to a vital keyword, within a plausible range (so "15 min" or "room 120" never count). Any out-of-range reading escalates, whichever value the model reports. Same principle as the Confirm guardrail: do not let one model answer decide a safety outcome.
2. **The model misreads spoken Hindi numbers, and grounding caught it.** "oxygen sattanve" (97) came back as 100; "pulse bahattar" (72) as 78. Neither was released. The 18% routine review rate, which the perfect-model baseline made look like pure cost, is catching real errors, so it should not be relaxed by trusting the model's conversion. The right next step is a deterministic Hindi/English number parser that checks the model's conversion, not one that replaces the check.
3. **Repeated readings.** "186/104, dobara liya toh 182/100": the model kept the second reading where the labels hold the first. Both are red flags and the note was escalated, so this is a labelling convention (like `cancel_current`), not a safety error.
4. **No invented vitals at all.** On the four notes with no vitals, and among the distractor numbers (age, room number, last week's BP, day counts), the model never made up a value.

## Not yet measured

- **Speech-to-text accuracy.** The eval uses text notes, so Whisper's errors on real Hinglish audio are not represented. A small set of self-recorded synthetic voice notes is the next step. Never use real patient audio.
- **Family summary quality.** Only checked mechanically (no unstated numbers); tone and helpfulness need human rating. One observed issue: a released routine summary said the vitals were "all within normal range", a mild clinical judgement the prompt asks the model not to make. Not unsafe on a routine note, but it is the first thing a summary-quality rubric should check.
