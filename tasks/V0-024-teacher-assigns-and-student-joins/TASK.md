# V0-024: Teacher assigns students and a started class is joinable

**Week:** W8  
**Status:** DONE  
**Owner:** Solo developer  
**Target:** V0

## Objective

Make the teaching flow reachable and honest on both sides of the class:

- **A teacher assigns students to a class** from its roster (an account that
  already exists), and **starts** the class. Those stay the teacher's verbs:
  an institution administrator holds no `class:write`/`enrollment:write`, and a
  student holds neither.
- **A student may join only a class the teacher has started.** A scheduled class
  says it is waiting; the join button is disabled until the class is `ACTIVE`, and
  the server still refuses a direct call with `409 CLASS_NOT_READY`/`NOT_STARTED`.
- **A student has somewhere to go**: `/student` lists the classes they are
  enrolled in, and each becomes a join link once it is running. `GET /classes` is
  scoped to the caller's roster for a student, so the list is not a window onto
  the institution's schedule.
- **The open join page notices the start**: while the class is scheduled, the join
  page (and the class list) re-read on a short client-local timer, so a student who
  opened the link early does not have to guess that a refresh is needed.

This does **not** add live presentation sync. Students still navigate their own
copy of the pinned deck; the ordered per-class event stream is `DEC-DATA-003`
(`OPEN`, live path V1-002), and the UI says so.

## Dependencies

- V0-009 (class start, roster, join credential), V0-021/V0-022 (accounts, roles,
  student pages), V0-023 (required sign-in)

## Requirement IDs

- `DEC-RUNTIME-003` (idempotent enrolment; a repeated join/start is not an error)
- `DEC-RUNTIME-007` (the join credential binds the caller's own account/epoch)
- `DEC-TURN-001` (the join credential stays subscribe-only)
- `DEC-CONTENT-005` (a join reads the pinned publication)
- `DEC-DATA-003` (the ordered per-class event stream remains `OPEN`; the polling
  is labelled client-local, not live)

## Required Reading

- `SOURCE_OF_TRUTH.md`
- `governance/DECISION_LEDGER.yaml`
- `docs/security/IDENTITY_AUTHORIZATION_AND_TOKENS.md`
- `contracts/openapi/openapi.yaml`
- `backend/app/classroom/{router,service,repository}.py`
- `backend/app/identity/models.py` (`ROLE_SCOPES`)
- `frontend/src/student/`, `frontend/src/admin/ClassesAdmin.tsx`,
  `frontend/src/classroom/ClassroomPage.tsx`, `frontend/src/router.tsx`

## In Scope

- **Backend**: `GET /classes` returns only the caller's enrolled classes to a
  student; a teacher and an institution administrator keep the tenant view. The
  roster query is the same authorization the join applies.
- **Student list** (`/student`, `StudentHomePage.tsx`): the classes the server
  returned, their state/time, a **Join class** link only when `ACTIVE`, a waiting
  message when scheduled, and an empty state that names the real route in.
- **Join page** (`/join/{classId}`): Join is disabled until the class is `ACTIVE`
  and says only the teacher can start it; it re-reads while scheduled.
- **Teacher**: class management selects a class as soon as one exists (falling
  back from a stale remembered id), so Start / assign / student join link are on
  screen; the classroom page links a teacher to that panel. Assigning and starting
  remain the existing teacher verbs.
- **Phone layout**: the student list and join page work at 390px and 320px; the
  classroom scene/step keys may break rather than widen the page.
- Contracts, docs, tests and traceability.

## Out of Scope

- Live slide/event sync, a server scheduler, or an outbound notification to
  students (`DEC-DATA-003`, `DEC-TECH-003` are `OPEN`).
- Creating accounts from the roster (enrolment resolves an existing account,
  V0-022), or giving an administrator teacher verbs.
- Any change to the runtime tuple, snapshot shape, join-token claims or the
  pinned-publication rule.
- A new service, broker, database or framework.

## Acceptance Criteria

| Criterion | How it is verified |
| --- | --- |
| A teacher assigns an existing student | `POST /classes/{id}/enrollments` by `student_id` as a teacher; the roster lists the account; the student cannot call it (`403`) |
| Only the teacher starts | A student's `POST /classes/{id}/start` is `403 SCOPE_REQUIRED`; the teacher's is `200 ACTIVE` |
| A scheduled class cannot be joined | `POST /classes/{id}/bootstrap-token` before start is `409 NOT_STARTED`; after start it is `200` subscribe-only, bound to the student's own account |
| A student sees only their roster | `GET /classes` as the student returns the enrolled class only; as the teacher it returns both classes |
| The UI says waiting, then allows join | A scheduled row/page has no enabled Join; once the teacher starts, the open page's poll enables it; a browser at 390px and 320px joins and has no horizontal overflow |
| No live claim is made | The pages label the polling client-local; the student still navigates the pinned deck |

## Blocker

None. The live ordered transport and the durable scheduler remain open decisions
(`DEC-DATA-003`, `DEC-TECH-003`); this task adds no claim about either.
