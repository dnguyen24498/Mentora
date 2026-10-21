# AI Prompt for V0-027

Read `TASK.md` and every file in **Required Reading**.

Do not write code yet. First return:

1. Applicable requirements and locked decisions.
2. Ownership boundaries and source of truth (who may end, reopen, read an ended
   class, and who is locked out).
3. State transitions and invariants (`END` and `REOPEN` as aggregate commands;
   the new epoch; the lesson reset; the roster and pinned tuple retention; the
   participant read guard).
4. Failure, timeout, retry, fallback and recovery paths (double end, reopen of a
   running class, reopen of an unstarted class, stale state version, damaged
   pinned plan, a student opening an ended class, a token from the old epoch, a
   teacher's tab closing).
5. Exact files to create or modify.
6. Tests to add before or with implementation.
7. Any OPEN decision or contradiction that blocks the task.

After the plan is approved, implement only the scope in `TASK.md`.

Rules:

- Do not expand scope.
- Do not treat proposed ADRs as accepted. `DEC-DATA-003` (ordered per-class
  stream), `DEC-TECH-003` (durable scheduler) and `DEC-TECH-007` (voice provider)
  stay `OPEN`.
- `COMPLETED` is the canonical state; **Ended** is its user-facing label. Do not
  add a new state to the vocabulary.
- The aggregate remains the only writer of session state. Do not update the
  session or snapshot rows directly from a router or the frontend.
- A reopen is the **same class occurrence**: keep the roster and the pinned
  package; do not resolve a newer publication and do not create a second plan.
- A reopen must bump the actor epoch and revoke the session's credentials. Do not
  reuse an epoch for a credential that outlived the end.
- Lock the **content** for students, not the class metadata: the student must
  still be able to see that the class ended.
- Do not reintroduce a server scheduler or claim automatic end. Ending is an
  explicit teacher action; automatic play stopping at the last slide is not an end.
- Update contracts before interfaces, update READMEs/traceability and stop if
  source-of-truth files conflict.
