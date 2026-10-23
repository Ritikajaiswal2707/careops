# Recovery Agent Approval and Simulated Execution

## Scope

CareOps supports a synthetic, approval-gated recovery workflow. After a proposal is approved, the `/execute` endpoint revalidates the proposed provider/date against the bundled synthetic availability and scheduling constraints, then records a simulated execution. This is **not** a real booking, capacity reservation, patient/provider notification, or write to an external scheduling system.

## Endpoints

- `POST /api/agent/run`: interpret a message and create an approval case when a feasible proposal exists.
- `GET /api/agent/cases/{case_id}`: retrieve case, workflow status, optional simulated execution and audit history.
- `POST /api/agent/cases/{case_id}/decision`: body `{"decision":"approve|reject","note":"optional"}`.
- `POST /api/agent/cases/{case_id}/execute`: only an approved case can be revalidated and recorded as simulated execution.

## State transitions

`pending_approval -> approved -> simulated_resolved`

or `pending_approval -> rejected`.

`status` remains the coordinator decision (`approved` after approval); `workflow_status` becomes `simulated_resolved` once the simulation record exists. Execution is idempotent per case: repeated calls return the same execution ID and do not create duplicate execution/audit rows. The endpoint refuses execution unless the proposal is approved and the revalidated appointment, provider and date match the approved proposal.

## Revalidation and execution

The system calls the capacity recovery engine immediately before recording execution. The exact proposed provider must still be in the eligible candidate set for the proposed date and original appointment time slot. If no longer eligible, the request fails closed and no execution record is written. The execution record is persisted in SQLite and explicitly marked `simulated: true` with `execution_mode: simulation_only`.

## Tests

Run `pytest -q`. Tests cover approval gating, exact proposal matching, revalidation failure, repeated execution idempotency, unknown cases and API responses. The full integration path also uses bundled synthetic records only.

## Security and production gaps

There is no authentication or role-based authorization. The case store defaults to a temporary database unless `CAREOPS_DB_PATH` is configured. The simulator does not reserve capacity atomically in a real scheduling system. A production implementation would require authenticated coordinator identity, a transactional scheduling-system adapter, real-time slot reservation with concurrency control, idempotency keys at the external system boundary, privacy controls, observability and integration tests against a non-production scheduling environment.
