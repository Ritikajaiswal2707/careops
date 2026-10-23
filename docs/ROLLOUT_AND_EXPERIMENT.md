# CareOps — Rollout & Experiment Plan

## Rollout philosophy

CareOps moves from recommendation → assisted workflow → controlled automation. No consequential healthcare workflow becomes autonomous without evidence.

---

## Stage 1 — Shadow Mode

**Objective:** Determine whether CareOps recommendations are useful without changing coordinator behavior.

```text
Real operational case → CareOps recommendation → Coordinator makes normal decision → Compare
```

**Measure:** recommendation agreement (AI vs coordinator action), false positives, missed cases, recovery feasibility, coordinator feedback.

## Stage 2 — Assisted Mode

CareOps recommendations become visible to coordinators. The coordinator remains responsible for all actions.

**Measure:** recommendation acceptance, override rate, coordinator time, time to recovery, disruption rate.

## Stage 3 — Controlled Experiment

**Hypothesis:** Proactive intervention on visits in the top 20% risk band reduces visit disruption compared with the current workflow.

**Design:** Randomize at appointment creation.
- **Control:** existing coordinator workflow
- **Treatment:** CareOps-supported intervention

**Primary metric:** appointment-level disruption rate.

**Guardrails:** coordinator time per flagged visit, patient complaints, patient opt-outs, completion rate of the non-flagged group.

**Secondary metrics:** recovery rate, time to recovery, recommendation acceptance, escalation rate.

See also [`../EXPERIMENT_DESIGN.md`](../EXPERIMENT_DESIGN.md) for sample size and null-result interpretation.

## Stage 4 — Limited Automation

Only the safest and highest-performing workflows are eligible: clear confirmation messages, structured status updates, low-risk administrative preparation. Consequential booking or care changes remain human-approved until evidence supports greater autonomy.

---

## Experiment decision tree

```text
Recommendation quality good?
        | YES
        ↓
Operational outcome improves?
        | YES
        ↓
Guardrails remain healthy?
        | YES
        ↓
Increase rollout
```

If any answer is NO: stop expansion and investigate the failure mode.
