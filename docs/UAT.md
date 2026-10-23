# CareOps — User Acceptance Testing

## UAT objective

Verify that CareOps supports the coordinator's workflow correctly before wider rollout. Testing covers prioritization, message understanding, recovery recommendations, rescheduling, escalation, state management and exception visibility.

## UAT scenarios

| ID | Scenario | Expected result | Priority |
|---|---|---|---|
| UAT-01 | Open daily dashboard | Visits and risk tiers load correctly | P0 |
| UAT-02 | View top-risk visit | Risk explanation is shown | P0 |
| UAT-03 | View low-risk visit | No unnecessary intervention is suggested | P1 |
| UAT-04 | Clear confirmation message | Intent = Confirm | P0 |
| UAT-05 | Clear cancellation message | Intent = Cancel | P0 |
| UAT-06 | Reschedule in English | Correct requested date extracted | P0 |
| UAT-07 | Reschedule in Hinglish | Correct intent extracted | P0 |
| UAT-08 | Message contains typo | System attempts interpretation or escalates | P1 |
| UAT-09 | Ambiguous message | Case escalates to human | P0 |
| UAT-10 | Invalid LLM output | Human escalation triggered | P0 |
| UAT-11 | Provider unavailable | Provider excluded | P0 |
| UAT-12 | Provider lacks service capability | Provider excluded | P0 |
| UAT-13 | Provider has no capacity | Provider excluded | P0 |
| UAT-14 | Multiple eligible providers | Ranked alternatives shown | P0 |
| UAT-15 | No eligible providers | Manual escalation shown | P0 |
| UAT-16 | Patient requests a future date | Requested date checked first | P0 |
| UAT-17 | Requested date unavailable | Alternative date search occurs | P0 |
| UAT-18 | Same provider available later | Same provider may remain eligible | P1 |
| UAT-19 | Coordinator rejects proposal | Alternative path triggered | P1 |
| UAT-20 | Coordinator approves proposal | Case advances to correct state | P0 |
| UAT-21 | Booking before confirmation | Invalid transition rejected | P0 |
| UAT-22 | Activity timeline opened | Important actions visible | P1 |
| UAT-23 | Exception opened | Owner + next action visible | P0 |
| UAT-24 | No API key available | Product gracefully falls back / escalates | P1 |
| UAT-25 | API unavailable | No false action is taken | P0 |

> These are expected-behaviour scenarios, not evidence that a live-provider call has passed. The rule-first runtime fallback is wired in; live API quality, cost, latency, and uptime remain unverified. See the repository test report for which automated cases have actually run.

---

## Critical acceptance tests

### Risk triage
- **Given** 95 visits exist for the day
- **When** the dashboard loads
- **Then** the actionable queue contains the defined top 20%

### Message understanding
- **Given** the message: *"Tomorrow evening won't work, can we do Saturday morning?"*
- **When** the message is processed
- **Then** intent = Reschedule; requested day = Saturday; replacement of the current appointment is preserved; system proceeds to availability search

### Recovery
- **Given** a provider is unavailable or over capacity
- **When** recovery search executes
- **Then** that provider cannot be recommended

### No feasible recovery
- **Given** no provider satisfies the hard eligibility constraints
- **When** recovery search executes
- **Then** the system returns *"No eligible recovery candidate found"* and escalates rather than creating a plausible but infeasible recommendation

### State machine
- **Given** a patient has not confirmed
- **When** a booking action is requested
- **Then** the action is rejected

---

## Execution status

The table above is the test plan. Scenarios are not marked passed by this document. Automated regression coverage lives in `tests/`; run `pytest -q` to obtain the current local result. Live Render behaviour and live LLM-provider quality require separate verification.

## UAT exit criteria

CareOps is ready for the next rollout stage when:

- All P0 scenarios pass
- No critical state-machine failures exist
- No false bookings occur
- Escalation works
- Recovery recommendations respect hard constraints
- Coordinator can understand the recommended action
- All major actions are auditable
