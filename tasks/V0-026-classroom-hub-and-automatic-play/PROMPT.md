# AI Prompt for V0-026

Read `TASK.md` and every file in **Required Reading**.

Do not write code yet. First return:

1. Applicable requirements and locked decisions.
2. Ownership boundaries and source of truth (who may list, start, join, navigate).
3. State transitions and invariants (the hub only calls existing verbs; a start
   is the aggregate's `START`; navigation is `NAVIGATE_SCENE`; a student reader
   must be on the roster).
4. Failure, timeout, retry, fallback and recovery paths (start refusal, class not
   running, stale state version, ended class, refused navigate, failed slide
   fetch, tab closed).
5. Exact files to create or modify.
6. Tests to add before or with implementation.
7. Any OPEN decision or contradiction that blocks the task.

After the plan is approved, implement only the scope in `TASK.md`.

Rules:

- Do not expand scope.
- Do not treat proposed ADRs as accepted. `DEC-DATA-003` (ordered per-class
  stream), `DEC-TECH-003` (durable scheduler) and `DEC-TECH-007` (voice provider)
  stay `OPEN`. Auto-play is **client-local**: the teacher's tab is the clock and
  nothing runs while it is closed. Never claim live sync, a worker or a voice.
- The hub composes existing endpoints only; no new route stands in for a
  transition the domain already owns.
- Keep the classroom aggregate as the only writer of session state; do not write
  a snapshot directly.
- Resolve content only from the package the session pinned (`DEC-CONTENT-005`);
  never parse the source deck or ask for the current publication.
- A student's list is scoped by the server; do not filter it in the page as a
  substitute for authorization.
- Do not reintroduce a mutated-object timer or a second scheduler: one timer per
  slide, derived from the current scene, is the whole mechanism.
- Update READMEs/traceability and stop if source-of-truth files conflict.
