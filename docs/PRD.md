# CareOps — Product Requirements Document

> **Status note:** This PRD describes the target product. Implementation status of each requirement in this repo snapshot is summarized in [Section 13](#13-implementation-status-of-this-repo). All data is synthetic.

## 1. Product Overview

CareOps is an AI Operations Copilot for home healthcare coordinators.

It helps coordinators:

1. Identify visits that are most likely to be disrupted
2. Understand why a visit may require intervention
3. Interpret patient/family messages
4. Find feasible recovery options
5. Propose a new provider or date
6. Escalate cases when the system cannot safely resolve them
7. Track the outcome of the intervention

### Product principle

> The system handles prioritization and recommendations; the coordinator owns exceptions and final decisions.

CareOps is designed around a constrained operational environment where coordinator attention is limited and provider availability is not unlimited.

---

## 2. Problem Statement

Home-healthcare coordinators manage a large number of visits across patients, providers, locations and time slots.

When something goes wrong, the coordinator may need to:

- identify which visit needs attention
- contact the family
- interpret an ambiguous response
- find a suitable provider
- check provider availability
- evaluate continuity, location and workload
- reschedule the visit
- communicate the new plan
- follow up if the recovery fails

The operational problem is therefore not simply "predict no-shows". It is:

> How can a coordinator spend limited time on the visits most likely to need intervention while making recovery decisions quickly and safely?

---

## 3. Users

### Primary user: City / Operations Coordinator

Responsible for care fulfillment and exception handling. The system should surface cases requiring intervention rather than forcing the coordinator to manually review every normal visit.

### Secondary users

- Patients / parents
- Family members
- Nurses and other providers
- Operations leadership

---

## 4. User Jobs

The coordinator needs to answer four questions quickly:

1. **What needs attention?** Which visits are most likely to fail or already have an exception?
2. **Why does it need attention?** What signals contributed to the risk?
3. **What should I do?** Confirm, call, reassign, reschedule, or escalate?
4. **Can I actually recover it?** Is there a provider who is available, qualified, geographically reasonable and not already overloaded?

---

## 5. Goals

**Primary goal:** Reduce operational disruption while making better use of coordinator time.

**Product goals**

- Prioritize the highest-value cases for coordinator attention
- Reduce manual interpretation of patient messages
- Reduce time required to identify recovery options
- Preserve provider continuity where practical
- Prevent infeasible recommendations
- Make AI uncertainty visible
- Keep the coordinator in control of consequential actions
- Create a measurable workflow that can be experimentally validated

---

## 6. Non-Goals

CareOps V1 will not:

- make clinical decisions
- replace doctors or nurses
- automatically cancel or book visits without approval
- send real patient communications
- write directly to a production scheduling system
- optimize complete provider routes
- perform accounting or financial reconciliation
- act as a generic healthcare CRM

---

## 7. Core Workflow

```text
Scheduled Visits
      ↓
Risk Prioritization
      ↓
Explain Risk
      ↓
Patient / Family Message
      ↓
Message Understanding
      ↓
Recovery Search
      ↓
Provider + Slot Recommendation
      ↓
Coordinator Approval
      ↓
Simulated / Recorded Outcome
      ↓
Measurement
```

---

## 8. Functional Requirements

### FR-01 — Risk Triage
The system must rank upcoming visits by disruption risk.

- Generate a disruption score for each eligible visit
- Rank visits for coordinator attention
- Flag the top 20% as actionable
- Display High / Medium / Low tiers
- Show the main factors contributing to the score

*Rationale:* Coordinator bandwidth is limited, so ranking is more useful than showing every visit as equally actionable.

### FR-02 — Risk Explanation
Each flagged visit has a human-readable explanation, e.g. *"High risk because the patient has 2 previous no-shows, low response history and an evening appointment."* Explanations use only features available at prediction time.

### FR-03 — Patient Message Understanding
Convert free-form messages into structured intent.

- Supported intents: Confirm, Reschedule, Cancel, Unclear, No Response
- Optional outputs: requested day, relative date, cancellation of current appointment, reason
- Messages may contain English, Hindi, Hinglish, spelling errors, indirect phrasing, compound requests

### FR-04 — Hybrid AI Routing
Rule-first approach:

```text
Message
   ↓
Rule extractor
   ├── Understood → accept
   └── Unclear → LLM fallback
                     ├── Valid → accept
                     └── Invalid / Unclear → human
```

The LLM must not be called for messages that deterministic rules can already handle.

### FR-05 — Human Escalation
Escalate cases the system cannot safely interpret or resolve: ambiguous intent, invalid structured output, unsupported request, no feasible provider, conflicting scheduling constraints.

Each escalation communicates **Issue, Owner, Next action, SLA (where applicable)**.

### FR-06 — Recovery Search
For an at-risk or reschedule case, identify eligible providers. Hard eligibility filters — a provider must satisfy:

- required service capability
- correct operating area
- availability
- remaining capacity
- valid schedule fit

Only eligible candidates enter scoring.

### FR-07 — Recovery Score
Eligible providers are ranked using continuity, proximity, remaining capacity, schedule fit, service fit, and a utilization penalty. The system returns both the recommendation and the reasons for it.

### FR-08 — Rescheduling
For a reschedule request the system must: understand the request → determine requested date/window → check provider availability → search feasible alternatives → rank eligible options → propose the best option → stop for coordinator / patient confirmation. If no feasible option exists, escalate to the coordinator.

### FR-09 — State Management
Controlled transitions:

```text
PENDING → PROPOSED → PATIENT_CONFIRMED → BOOKED → PROVIDER_NOTIFIED → COMPLETED
```

Alternative paths: `PROPOSED → DECLINED → SEARCH_ALTERNATIVE → PROPOSED | ESCALATED`.

Illegal transitions must be rejected. A case is never marked booked before required confirmation.

### FR-10 — Exception Visibility
Every exception exposes **Issue, Owner, Next Action, SLA**. Applicable cases: high-risk visit, unassigned visit, missed visit, reschedule request, provider unavailable, incomplete report, health-related operational flag, billing issue.

### FR-11 — Activity Timeline
Log important operational actions (assignment, reassignment, reschedule request/proposal, confirmation, family communication, escalation, completion) so the coordinator can answer: *what happened, when, and who acted?*

---

## 9. Success Metrics

**North Star:** Completed visits per coordinator hour.

**Primary product metrics**
- Disruption rate in flagged group
- Recovered visits per 100 flagged visits
- Time to recovery
- Coordinator time per flagged visit
- Recommendation acceptance rate
- Feasible recovery rate

**AI metrics**
- Risk model: Precision@20, Recall@20, Lift@20, calibration
- Message understanding: intent accuracy, macro F1, temporal accuracy, human escalation rate
- Recovery: candidate feasibility rate, recommendation acceptance, no-feasible-candidate rate

**Guardrail metrics**
- Completion rate of non-flagged visits
- Patient complaints / opt-outs
- Incorrect automated recommendations
- Coordinator overrides
- Invalid AI outputs
- Provider overload incidents

---

## 10. AI Safety / Autonomy

CareOps begins as recommendation software.

| Level | Mode | Description |
|---|---|---|
| 1 | Recommend | AI identifies a problem and recommends an action |
| 2 | Prepare | AI prepares the action, message or rescheduling proposal |
| 3 | Coordinator approval | Coordinator confirms the action |
| 4 | Controlled automation | Only low-risk workflows, after sufficient evidence |

Autonomy increases only after quality and operational metrics support it.

---

## 11. Dependencies

- Provider availability data
- Provider capability mapping
- Schedule data
- Patient communication channel
- Coordinator workflow
- Historical visit data
- Human review process

---

## 12. Key Risks

| Risk | Mitigation |
|---|---|
| Weak prediction signal | Use triage instead of autonomous decisions |
| LLM misinterpretation | Rule-first routing + structured output + escalation |
| No feasible replacement provider | Hard eligibility filters |
| Provider overload | Capacity and utilization constraints |
| AI over-reliance | Human approval |
| Data leakage | Time-aware feature construction and temporal validation |
| Synthetic data mismatch | Shadow mode + real-world experiment before scale |
| Privacy risk | Data minimization before external model calls |

---

## 13. Implementation status of this repo

| Requirement | Status in this repo snapshot |
|---|---|
| FR-01 / FR-02 Risk triage + explanation | Implemented (`model/disruption_model.py`); leakage-fixed ROC-AUC ≈ 0.58 — triage signal, not autonomous decision |
| FR-03 Message understanding | Rule-based extractor implemented; 44.7% intent accuracy and 65% abstention on the 103-message held-out set |
| FR-04 LLM fallback | Runtime integration implemented through `model/hybrid_extraction.py` and `model/gemini_llm.py`; saved blind predictions support offline scoring, but live API quality/cost/latency are unverified |
| FR-05 Escalation | State-machine `ESCALATED` path, no-candidate handling, and ambiguous/invalid LLM-result escalation are implemented; live provider failure behaviour is covered only to the extent verified by tests |
| FR-06 / FR-07 Recovery search + score | Implemented (`model/capacity_recovery.py`) |
| FR-08 Rescheduling | Implemented, stops at `PROPOSED` (`model/reschedule_agent.py`) |
| FR-09 State management | Implemented, enforced allow-list (`model/agent_state_machine.py`) |
| FR-10 / FR-11 Exceptions, timeline | Partially represented in the dashboard and state-machine history; full owner/SLA model is roadmap |
