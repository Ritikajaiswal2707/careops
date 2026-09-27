"""
Module 7: agent state machine.

The P0 critique on the earlier version: the simulated flow ("message
drafted -> slot reserved -> provider notified -> family notified ->
recovered") was just five strings printed in order. It never checked
whether a step was legal from the previous one, so it couldn't represent
failure ("patient declines the proposed slot") at all -- there was no
state to decline FROM.

This module makes the lifecycle a real, enforced state machine:

    PENDING -> PROPOSED -> PATIENT_CONFIRMED -> BOOKED -> PROVIDER_NOTIFIED -> COMPLETED

and the failure branch:

    PROPOSED -> DECLINED -> SEARCH_ALTERNATIVE -> PROPOSED (next candidate)
                                                -> ESCALATED (candidates exhausted)

"Real" here means: every transition is checked against ALLOWED_TRANSITIONS
before it's applied, an illegal one raises InvalidTransition instead of
silently succeeding, and the full (state, detail) history is kept -- not
narrated in a print statement, but a data structure another part of the
system (the dashboard, a test, a real booking write) can inspect.

Still local/in-memory, still no backend, exactly as the critique allowed --
"you don't need a backend, but the state machine should be real." What's
NOT simulated is a live patient reply channel: this dataset has no back-
and-forth chat, so a real call from reschedule_agent.py can only drive a
case as far as PROPOSED and stop, honestly, at "awaiting a reply we don't
have." The __main__ block below drives a case through every state
(success path and decline/retry/escalation path) with synthetic patient
responses, clearly so it's not confused with a live result, to prove the
transitions are real and correctly enforced.
"""
from enum import Enum


class State(Enum):
    PENDING = "PENDING"
    PROPOSED = "PROPOSED"
    PATIENT_CONFIRMED = "PATIENT_CONFIRMED"
    DECLINED = "DECLINED"
    SEARCH_ALTERNATIVE = "SEARCH_ALTERNATIVE"
    BOOKED = "BOOKED"
    PROVIDER_NOTIFIED = "PROVIDER_NOTIFIED"
    COMPLETED = "COMPLETED"
    # Not in the original five-state happy path -- added because a real
    # system needs a terminal state for "ran out of candidates", not just
    # an implicit dead end.
    ESCALATED = "ESCALATED"


ALLOWED_TRANSITIONS = {
    State.PENDING: {State.PROPOSED},
    State.PROPOSED: {State.PATIENT_CONFIRMED, State.DECLINED},
    State.DECLINED: {State.SEARCH_ALTERNATIVE},
    State.SEARCH_ALTERNATIVE: {State.PROPOSED, State.ESCALATED},
    State.PATIENT_CONFIRMED: {State.BOOKED},
    State.BOOKED: {State.PROVIDER_NOTIFIED},
    State.PROVIDER_NOTIFIED: {State.COMPLETED},
    State.COMPLETED: set(),
    State.ESCALATED: set(),
}


class InvalidTransition(Exception):
    pass


class RescheduleCase:
    """One appointment's journey through the lifecycle. `candidates` is the
    ranked list from capacity_recovery.recommend(..., top_n>1) -- consumed
    one at a time as SEARCH_ALTERNATIVE moves to the next-best candidate."""

    def __init__(self, appointment_id: str, candidates: list):
        self.appointment_id = appointment_id
        self.state = State.PENDING
        self.history = [(State.PENDING, None)]
        self._remaining_candidates = list(candidates)
        self.current_candidate = None

    def _transition(self, new_state: State, detail=None):
        allowed = ALLOWED_TRANSITIONS[self.state]
        if new_state not in allowed:
            raise InvalidTransition(
                f"{self.appointment_id}: {self.state.value} -> {new_state.value} "
                f"is not a legal transition (allowed: {[s.value for s in allowed] or 'none, terminal state'})"
            )
        self.state = new_state
        self.history.append((new_state, detail))

    def propose_next(self):
        """PENDING or SEARCH_ALTERNATIVE -> PROPOSED, using the next-ranked
        candidate. -> ESCALATED if none are left."""
        if not self._remaining_candidates:
            self._transition(State.ESCALATED, "no more candidates — needs manual coordinator follow-up")
            return None
        self.current_candidate = self._remaining_candidates.pop(0)
        self._transition(State.PROPOSED, self.current_candidate)
        return self.current_candidate

    def patient_confirms(self):
        self._transition(State.PATIENT_CONFIRMED, self.current_candidate)

    def patient_declines(self):
        self._transition(State.DECLINED, self.current_candidate)
        self._transition(State.SEARCH_ALTERNATIVE, "patient declined — trying next candidate")

    def book(self):
        self._transition(State.BOOKED, self.current_candidate)

    def notify_provider(self):
        self._transition(State.PROVIDER_NOTIFIED, self.current_candidate)

    def complete(self):
        self._transition(State.COMPLETED, self.current_candidate)

    def history_trace(self):
        """Plain-language rendering of self.history, for dashboard/trace display."""
        lines = []
        for state, detail in self.history:
            if detail is None:
                lines.append(state.value)
            elif isinstance(detail, dict):
                lines.append(f"{state.value} ({detail.get('provider_id', detail)})")
            else:
                lines.append(f"{state.value} ({detail})")
        return lines


if __name__ == "__main__":
    # Demo 1: the happy path, PENDING all the way to COMPLETED.
    candidates = [{"provider_id": "PR019", "score": 47.8}, {"provider_id": "PR006", "score": 41.2}]
    case = RescheduleCase("APT_DEMO_1", candidates)
    case.propose_next()       # -> PROPOSED (PR019)
    case.patient_confirms()   # -> PATIENT_CONFIRMED
    case.book()               # -> BOOKED
    case.notify_provider()    # -> PROVIDER_NOTIFIED
    case.complete()           # -> COMPLETED
    print(f"{case.appointment_id}: " + " -> ".join(case.history_trace()))

    # Demo 2: the failure/retry branch — first candidate declines, falls
    # back to the next-ranked one, then succeeds.
    candidates = [{"provider_id": "PR019", "score": 47.8}, {"provider_id": "PR006", "score": 41.2}]
    case = RescheduleCase("APT_DEMO_2", candidates)
    case.propose_next()       # -> PROPOSED (PR019)
    case.patient_declines()   # -> DECLINED -> SEARCH_ALTERNATIVE
    case.propose_next()       # -> PROPOSED (PR006)
    case.patient_confirms()
    case.book()
    case.notify_provider()
    case.complete()
    print(f"{case.appointment_id}: " + " -> ".join(case.history_trace()))

    # Demo 3: candidates fully exhausted -> ESCALATED, a real terminal
    # state instead of a silent dead end.
    case = RescheduleCase("APT_DEMO_3", [{"provider_id": "PR019", "score": 47.8}])
    case.propose_next()       # -> PROPOSED (PR019)
    case.patient_declines()   # -> DECLINED -> SEARCH_ALTERNATIVE
    case.propose_next()       # no candidates left -> ESCALATED
    print(f"{case.appointment_id}: " + " -> ".join(case.history_trace()))

    # Demo 4: prove illegal transitions are actually rejected, not just
    # documented — e.g. you cannot book a case that was never confirmed.
    case = RescheduleCase("APT_DEMO_4", [{"provider_id": "PR019", "score": 47.8}])
    case.propose_next()
    try:
        case.book()  # illegal: PROPOSED -> BOOKED skips PATIENT_CONFIRMED
    except InvalidTransition as e:
        print(f"{case.appointment_id}: correctly rejected an illegal transition — {e}")
