# CareOps — Product Roadmap

## Roadmap principle

Do not automate the entire care operation at once. Increase automation only as evidence supports it.

---

## Phase 0 — Discovery & Shadow Mode

**Objective:** Validate that CareOps is solving the right operational problems before changing coordinator behavior.

**Activities**
- Observe coordinator workflows
- Validate prioritization logic
- Review AI recommendations alongside coordinator decisions
- Collect rejected recommendations
- Measure false positives / false negatives
- Identify operational constraints not represented in data

**Success criteria**
- Coordinators understand the risk queue
- Reasons are understandable
- Major failure modes are documented
- Recommendation disagreement can be explained

---

## Phase 1 — Coordinator Copilot

**Objective:** Reduce the coordinator's time spent identifying and understanding exceptions.

**Ship:** risk ranking, top-20% action queue, risk explanations, message interpretation, human escalation, exception ownership.

**Operating mode:** AI recommends. Coordinator decides.

**Primary metrics:** coordinator time per flagged visit, Precision@20, escalation rate, coordinator override rate.

---

## Phase 2 — Recovery Copilot

**Objective:** Reduce the time required to resolve a disrupted visit.

**Ship:** provider eligibility filtering, Recovery Score, provider recommendation, reschedule search, alternative slot proposals, recovery trace.

**Key learning:** measure not only prediction quality but whether a feasible recovery actually exists.

**Primary metrics:** feasible recovery rate, time to recovery, recovery acceptance rate, recovered visits per coordinator hour.

---

## Phase 3 — Controlled Workflow Automation

**Objective:** Automate low-risk repetitive steps.

**Candidates:** draft routine confirmation messages, prepare rescheduling options, pre-fill provider communication, create coordinator action queues, auto-route clearly interpretable messages.

**Guardrails:** human approval for consequential actions, strict state transitions, confidence/quality thresholds, audit trail, escalation fallback.

---

## Phase 4 — Capacity Intelligence

**Objective:** Address the supply-side bottleneck identified in the simulation.

**Ship:** better provider availability data, real-time capacity, coverage-zone mapping, provider workload visibility, historical recovery acceptance, supply-demand forecasting.

**Decision principle:** do not spend the next iteration only improving prediction if recovery capacity remains the limiting constraint.

---

## Phase 5 — Evidence-Based Automation

**Objective:** Earn additional autonomy based on observed performance. Only workflows meeting predefined quality and risk criteria can move to automated execution.

```text
Recommendation → Shadow mode → Assisted mode → Measured automation → Periodic review
```

---

## Roadmap dependencies

| Dependency | Why it matters |
|---|---|
| Real availability | Recovery recommendations |
| Messaging channel | Moving beyond PROPOSED |
| Provider capability data | Correct eligibility |
| Coordinator feedback | Recommendation quality |
| Outcome instrumentation | Measuring recovery |
| Privacy controls | External AI calls |

## Deliberately NOT on the roadmap

- More AI agents for the sake of complexity
- RAG without a clear retrieval problem
- Larger ML models without additional signal
- Fully autonomous healthcare decisions
- Route optimization before basic recovery capacity is solved
