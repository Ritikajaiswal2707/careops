# CareOps — User Stories & Acceptance Criteria

## Epic 1 — Risk Triage

### US-01 — See visits requiring attention
**As a coordinator,** I want to see which upcoming visits are most likely to be disrupted so that I can spend my limited time on the highest-priority cases.

**Acceptance criteria**
- Visits are ranked by risk.
- Top 20% are surfaced as actionable.
- High / Medium / Low tiers are visible.
- Coordinator can open any flagged visit.
- Risk ranking does not use future information.

### US-02 — Understand why a visit is risky
**As a coordinator,** I want to understand the main reasons behind a risk score so that I can decide whether intervention is appropriate.

**Acceptance criteria**
- At least one human-readable explanation is shown.
- Explanation maps to available features.
- No unsupported reason is generated.
- Coordinator can distinguish model signal from operational fact.

---

## Epic 2 — Communication Intelligence

### US-03 — Understand patient messages
**As a coordinator,** I want patient messages converted into structured intent so that I do not have to manually interpret every message.

**Acceptance criteria**
- System identifies supported intent.
- Date preference is extracted when present.
- Relative dates are interpreted.
- Compound cancellation/reschedule requests are preserved.
- Unclear messages remain unresolved rather than guessed.

### US-04 — Escalate ambiguity
**As a coordinator,** I want ambiguous messages sent to me so that the system does not make an unsafe assumption.

**Acceptance criteria**
- Invalid AI output triggers escalation.
- Unclear AI output triggers escalation.
- Escalation reason is displayed.
- Coordinator can continue manually.

---

## Epic 3 — Recovery

### US-05 — Find eligible providers
**As a coordinator,** I want the system to filter providers based on operational constraints so that I only see feasible recovery options.

**Acceptance criteria — a provider is excluded if:**
- unavailable
- lacks required service capability
- has no remaining capacity
- fails location/area requirements
- cannot fit the requested slot

### US-06 — Rank recovery options
**As a coordinator,** I want feasible providers ranked by continuity, proximity, capacity and schedule fit so that I can compare alternatives quickly.

**Acceptance criteria**
- Only eligible candidates are scored.
- Score is deterministic for the same input.
- Reasons for score are shown.
- Coordinator can inspect alternatives.
- Current provider is not incorrectly excluded when a valid reschedule with the same provider is possible.

### US-07 — Handle no feasible candidate
**As a coordinator,** I want the system to clearly tell me when no suitable provider exists so that I do not waste time investigating impossible options.

**Acceptance criteria**
- "No eligible candidate" is explicitly displayed.
- Coordinator sees why candidates were excluded where practical.
- Case moves to manual escalation.
- System does not fabricate a recommendation.

---

## Epic 4 — Rescheduling

### US-08 — Understand reschedule request
**As a coordinator,** I want a patient's reschedule request converted into a specific date preference so that I can act without manually interpreting the message.

**Acceptance criteria**
- Requested day / relative date is extracted when present.
- The intent to replace the current appointment is preserved.
- If no date can be determined, the case is flagged rather than guessed.

### US-09 — Propose a replacement slot
**As a coordinator,** I want CareOps to search future dates and recommend the best feasible option so that I can respond faster to the family.

**Acceptance criteria**
- Requested date is checked first where specified.
- Alternative dates are searched when necessary.
- Same Recovery Score logic is used.
- Recommended provider and date are shown, with reasons.
- No proposal is made when no feasible option exists.

---

## Epic 5 — Human-in-the-Loop

### US-10 — Approve recommendation
**As a coordinator,** I want to approve or reject the proposed action so that I remain responsible for consequential care decisions.

**Acceptance criteria**
- Recommendation does not automatically become booked.
- Approval changes the case state.
- Rejection triggers alternative search or escalation.
- Every action is logged.

---

## Epic 6 — Operational Visibility

### US-11 — Understand exception ownership
**As a coordinator,** I want every exception to tell me who owns it and what to do next so that I do not waste time figuring out the next action.

**Acceptance criteria — every exception displays:** Issue, Owner, Next action, SLA where relevant.

### US-12 — View activity history
**As a coordinator,** I want an activity timeline for important actions so that I can understand what happened during a case.

**Acceptance criteria — timeline captures:** timestamp, event, actor, major state change, communication or approval event where relevant.

---

## Epic 7 — Reliability

### US-13 — Prevent invalid state transitions
**As a product team,** we want case states enforced by the system so that operationally invalid actions cannot occur.

**Acceptance criteria**
- Booking before confirmation is rejected.
- Completed before required workflow is rejected.
- Invalid transitions return a clear error.
- State history remains traceable.
