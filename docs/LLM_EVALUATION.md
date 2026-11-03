# Metered LLM evaluation: prompts, model size and a safety guardrail

Every number here comes from real API calls to Groq's free tier, saved in `data/evaluation/*_eval.json`. The full table can be rebuilt offline with `python model/summarize_llm_evals.py`.

All three message sets are synthetic and author-labelled. They are small (30–103 messages), so a difference of one or two messages is not statistically meaningful.

## The three test sets, and why there are three

| Set | Size | Role |
|---|---|---|
| `heldout` | 103 | Original extraction set. Its v1 errors were studied to write prompt v2, so later results on it are optimistic. |
| `holdout` | 30 | Frozen end-to-end holdout. Its v2 errors were studied to write prompt v3, so it is no longer clean either. |
| `holdout2` | 39 | Written and frozen (SHA-256 pinned) **before prompt v3 was ever run**, with no messages shared with the other sets. This is the clean test. |

Each time a set's errors shaped a design decision, it stopped being a fair test of that decision. That is why a fresh set was created.

## 1. Prompt v1 → v2: the model was guessing what the labels meant

Prompt v1 listed the label names but never defined them. On `heldout`, gpt-oss-120b reached **88.3%**, and 7 of its 12 errors were the same mistake: real messages ("ok", a question about charges) labelled **No Response**, which is meant only for empty messages.

Prompt v2 added a definition for every label, written from the definitions alone, with no eval messages copied in (a test enforces this). The fix carried over to sets the prompt was never written against:

| Set | v1 | v2 |
|---|---|---|
| holdout | 80.0% | 93.3% |
| holdout2 (clean) | 76.9% | 94.9% |

## 2. v2 → v3: the fix created a more dangerous error

v2 introduced **false confirmations**, the worst error type: the coordinator believes a visit is on when the family never agreed. "Thanks." and "The nurse is running late." were both read as Confirm. The cause was v2's own wording ("short acknowledgements count", "mentions a delay but will still be there"), which the model over-applied.

v3 changes only the Confirm definition: the sender must agree themselves, and a thank-you or news of someone else's delay is Unclear. On the clean set:

| holdout2 (clean), gpt-oss-120b | v1 | v2 | v3 |
|---|---|---|---|
| Intent accuracy | 76.9% | 94.9% | **97.4%** |
| False confirmations | 0 | 2 | **1** |
| Real messages marked No Response | 7 | 0 | 0 |

## 3. Model size: an early conclusion that did not survive fresh data

On the first two sets, gpt-oss-20b looked as good as 120B (97.1% vs 98.1% on `heldout`, 96.7% vs 93.3% on `holdout`), which suggested choosing the smaller, cheaper model. The clean set reversed that:

| holdout2 (clean), prompt v3 | gpt-oss-120b | gpt-oss-20b |
|---|---|---|
| Intent accuracy | **97.4%** | 92.3% |
| False confirmations | **1** | 2 |

20B labelled "papa ki dialysis hai us din, Monday rakh lo" (move it to Monday) as **Confirm**. Both models are free here, so the live default is 120B. On a paid tier, this is the comparison to re-run before switching to the smaller model to save money.

## 4. A prompt is not a safety guarantee: the Confirm guardrail

Even v3 still read "the sister said she will be 30 mins late" as Confirm. Rather than write a v4 prompt tuned on the clean set, the fix is a separate deterministic layer, [`model/confirm_guardrail.py`](../model/confirm_guardrail.py). It runs after the model, and it can **only** turn a Confirm into a human review. It never creates a confirmation or changes any other label, so its worst case is extra review work.

It vetoes a Confirm when the message also contains: someone else's delay, change language (a weekday, "shift", "instead"), negation, or nothing but gratitude.

| Across all 10 saved runs | Without guardrail | With guardrail |
|---|---|---|
| False confirmations | 8 | **0** |
| Genuine confirmations sent to a human | — | 1 per `heldout` run ("…koi change nahi", where "nahi" negates "change") |

**Caveat:** the delay and change-language rules were motivated by errors seen on `holdout` and `holdout2`, so the guardrail's perfect scores there are optimistic. It needs a fresh set to be measured cleanly.

## What the live app uses

- Prompt v3 by default (`LLM_PROMPT_VERSION` overrides it)
- gpt-oss-120b via Groq (`LLM_PROVIDER=groq`, `LLM_MODEL=openai/gpt-oss-120b`)
- The rule-first hybrid: rules answer first, and the LLM is called only when rules abstain
- The Confirm guardrail on every Confirm, whether it came from the rules or the LLM

## Open issues

- **`cancel_current` is not a well-defined field.** Most "errors" (25 of 27 under v2) are plain reschedules where the model says the current slot is freed and the gold label says it isn't. The model's reading is defensible. The field needs an operational definition before it can be evaluated, and that is a product decision, not a model fix.
- **Latency:** p50 is about 1.2–1.3 s per message on the free tier, with occasional 5–25 s outliers. Fine for coordinator triage, not for anything interactive and time-critical.
- **Next clean test:** a third holdout, frozen before any further prompt or guardrail change.
