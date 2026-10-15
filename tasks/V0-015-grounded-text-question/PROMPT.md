# AI Prompt for V0-015

Read `TASK.md` and every file in **Required Reading**.

Do not write code yet. First return:

1. Applicable requirements and locked decisions.
2. Ownership boundaries and source of truth.
3. State transitions and invariants.
4. Failure, timeout, retry, cancellation, fallback, and recovery paths.
5. Exact files to create or modify.
6. Tests to add before or with implementation.
7. Any OPEN decision or contradiction that blocks the task.

After the plan is approved, implement only the scope in `TASK.md`.

Rules:

- Do not expand scope.
- Do not treat proposed ADRs as accepted.
- Do not introduce a new service, database, broker, or framework without an accepted ADR.
- Update contracts before changing interfaces.
- Keep domain logic independent from provider SDKs.
- Add structured telemetry and update traceability.
- Stop if source-of-truth files conflict.
