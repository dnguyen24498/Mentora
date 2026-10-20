# AI Prompt for V0-024

Read `TASK.md` and every file in **Required Reading**.

Do not write code yet. First return:

1. Applicable requirements and locked decisions.
2. Ownership boundaries and source of truth (which verbs belong to a teacher, an
   administrator and a student).
3. State transitions and invariants (`SCHEDULED → ACTIVE`; a join requires
   `ACTIVE` **and** the caller's own enrolment).
4. Failure, timeout, retry, fallback and recovery paths (a class that is not
   started, a student who is not enrolled, a stale remembered class id).
5. Exact files to create or modify.
6. Tests to add before or with implementation.
7. Any OPEN decision or contradiction that blocks the task.

After the plan is approved, implement only the scope in `TASK.md`.

Rules:

- Do not expand scope.
- Do not treat proposed ADRs as accepted. `DEC-DATA-003` (ordered per-class
  stream) and `DEC-TECH-003` (durable scheduler) stay `OPEN`: the polling added
  here is **client-local** and must be labelled so; nothing may claim live sync.
- Do not give an institution administrator teacher verbs, and do not let a student
  start or enrol: the separation of duties is V0-022's.
- Do not let enrolment create an account; it resolves one that exists.
- Do not change the join credential's claims or the pinned-publication rule.
- Update contracts before changing interfaces.
- Keep domain logic independent from provider SDKs and the frontend's layout
  mobile-first at 320px.
- Add tests and update traceability.
- Stop if source-of-truth files conflict.
