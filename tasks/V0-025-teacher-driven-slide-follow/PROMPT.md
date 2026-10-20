# AI Prompt for V0-025

Read `TASK.md` and every file in **Required Reading**.

Do not write code yet. First return:

1. Applicable requirements and locked decisions.
2. Ownership boundaries and source of truth (which verbs belong to a teacher, an
   administrator and a student).
3. State transitions and invariants (`ACTIVE`/`DEGRADED` only; a slide command is
   a `NAVIGATE_SCENE`; a student reader must be on the roster).
4. Failure, timeout, retry, fallback and recovery paths (class not started, stale
   state version, ended class, out-of-range scene, failed slide fetch, poll gap).
5. Exact files to create or modify.
6. Tests to add before or with implementation.
7. Any OPEN decision or contradiction that blocks the task.

After the plan is approved, implement only the scope in `TASK.md`.

Rules:

- Do not expand scope.
- Do not treat proposed ADRs as accepted. `DEC-DATA-003` (ordered per-class
  stream) and `DEC-TECH-003` (durable scheduler) stay `OPEN`: the student's
  follow mechanism is a **client-local short poll** and must be labelled so;
  nothing may claim live sync.
- Update contracts before changing interfaces.
- Keep the classroom aggregate as the only writer of session state; do not write
  a snapshot directly.
- Resolve content only from the package the session pinned (`DEC-CONTENT-005`);
  never parse the source deck or ask for the current publication.
- A student is a participant: their class/snapshot/scene reads must be checked
  against the class roster, not just the tenant.
- Add structured telemetry and update traceability.
- Stop if source-of-truth files conflict.
