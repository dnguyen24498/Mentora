# V0-027: Class lifecycle — end, lock and reopen

**Week:** W8
**Status:** DONE
**Owner:** Solo developer
**Target:** V0

## Objective

Give an ended class an explicit, durable lifecycle. A teacher can **end** the
lesson; the class then reads **Ended**, its students are locked out of the lesson
content until it is reopened, and the teacher can **reopen the same class** to
teach it again from the first slide.

This closes the gap left by V0-026: automatic play stops at the last slide, but
the session stayed `ACTIVE` forever, so there was no ended status, no lock, and no
way to run the class again. The state machine already had `COMPLETED`; the missing
piece was the teacher's `END`/`REOPEN` control and the participant read guard.

## Dependencies

- V0-009 (class and pinned runtime session plan)
- V0-010 (in-process Classroom Aggregate)
- V0-024 (roster-scoped student reads and join)
- V0-025 (teacher-driven pinned-slide navigation)
- V0-026 (classroom hub and automatic play)

## Requirement IDs

- `DEC-CONTENT-005` (a reopen keeps the pinned package and roster)
- `DEC-DATA-004` (the ended/reopened state is durable and snapshot-validated)
- `DEC-RUNTIME-001` (the aggregate stays the only writer)
- `DEC-RUNTIME-003` (end/reopen are idempotent commands)
- `DEC-RUNTIME-007` (a reopen starts a new actor epoch; old credentials are stale)

## Required Reading

- `SOURCE_OF_TRUTH.md`
- `governance/DECISION_LEDGER.yaml`
- `governance/TERMINOLOGY_REGISTRY.yaml`
- `AI_IMPLEMENTATION_GUIDE.md`
- `docs/state-machines/CLASSROOM_SESSION_STATE_MACHINE.md`
- `docs/architecture/09_CLASSROOM_ACTOR_AND_RECOVERY.md`
- `docs/sequences/CLASS_END.md`
- `contracts/openapi/openapi.yaml`
- `frontend/README.md`

## In Scope

- Aggregate: a `REOPEN` command (`COMPLETED → ACTIVE`) that keeps the pinned
  tuple and roster, resets the lesson to its first position, bumps `actor_epoch`,
  clears any turn/floor/checkpoint, and emits `classroom.session.reopened`.
- Persistence: `commit_transition` accepts the **pre-command** epoch as the guard
  while writing the new epoch into the session and the appended snapshot.
- Service: `reopen_class` resolves the first lesson position from the pinned
  package, and `require_student_content_access` locks a completed session's
  snapshot and scenes for students. `verify_bootstrap_token` also refuses a token
  whose session is no longer running.
- HTTP: `POST /classes/{id}/end` and `POST /classes/{id}/reopen` (both
  `class:write`, idempotent by `command_id`, fenced by `expected_state_version`).
- Hub: an **Ended** label, a teacher **Reopen class** action, no lesson link for a
  student on an ended class, and a lock message.
- Student viewer: an ended class shows a locked screen with no slide or text; it
  keeps polling the class metadata and joins the new epoch after a reopen.
- Join page and class management: ended wording and the shared state labels.
- Contract, state-machine, architecture, README and task traceability updates.

## Out of Scope

- The ordered per-class event stream, outbox or push transport (`DEC-DATA-003` is
  `OPEN`; V1-002). Reopen/end are HTTP commands over the aggregate.
- A durable scheduler or automatic end (`DEC-TECH-003` is `OPEN`). Ending is an
  explicit teacher action; auto-play stopping at the last slide is not an end.
- A second class occurrence, copying rosters, or a new `RuntimeSessionPlan`
  (reopen is the same occurrence; a genuinely new lesson is a new class).
- Media, SFU, voice, STT or LLM behaviour.

## Acceptance Criteria

- `POST /classes/{id}/end` moves a running class to `COMPLETED` in one snapshot
  and revokes its join tokens; a second end is `409 INVALID_TRANSITION`.
- After the end, a student still sees the class metadata and its **Ended** row,
  but `GET /classes/{id}/snapshot`, `/scenes` and `/scenes/{order}` answer
  `409 CLASS_NOT_READY`/`CLASS_ENDED`; a teacher's reads still work.
- `START` on a completed class is refused with `WRONG_STATE` rather than silently
  returning the completed session.
- `POST /classes/{id}/reopen` moves `COMPLETED → ACTIVE` for the same class, keeps
  the roster and pinned tuple, sets the lesson to its first position, and writes a
  **new `actor_epoch`**. A student can join again only with a credential from the
  new epoch; the pre-end credential is revoked/stale.
- The hub shows **Ended**, offers a teacher **Reopen class** (which opens the
  class at `?autoplay=1`), and offers a student no lesson link and a lock note.
- The student viewer shows no slide or text while ended and joins automatically
  when the class is reopened.
- `pytest`, `vitest`, `tsc --noEmit` and `npm run build` pass.

## Verification

- `backend/tests/test_teacher_assigns_and_student_joins.py`
  (`test_ending_locks_the_student_and_reopening_runs_the_same_class_again`)
- `backend/tests/classroom/`
- `frontend/src/classroom/ClassroomHomePage.test.tsx`
- `frontend/src/classroom/TeacherStage.test.tsx`
- `frontend/src/student/StudentClassPage.test.tsx`
- `frontend/src/student/JoinClassPage.test.tsx`
- Browser check: start → end → student locked → reopen → student joins again.
