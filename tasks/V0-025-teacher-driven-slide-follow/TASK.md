# V0-025: Teacher-driven slide follow

**Week:** W8
**Status:** DONE
**Owner:** Solo developer
**Target:** V0

## Objective

Make the classroom teacher-led: a teacher advances the slide of the package the
session pinned, and a student's view follows that slide. The student is a viewer,
not a self-paced copy of the deck: no previous/next buttons, no slide picker and
no arrow-key navigation. A student still cannot join before the teacher starts.

## Dependencies

- V0-010 (in-process Classroom Aggregate)
- V0-011 (classroom client snapshot projection)
- V0-024 (teacher-assigned roster and a started class is joinable)

## Requirement IDs

- `DEC-CONTENT-004`
- `DEC-CONTENT-005`
- `DEC-RUNTIME-003`
- `DEC-RUNTIME-007`
- `DEC-DATA-004`
- `DEC-DATA-003` (boundary only: the ordered stream remains `OPEN`)

## Required Reading

- `SOURCE_OF_TRUTH.md`
- `governance/DECISION_LEDGER.yaml`
- `governance/TERMINOLOGY_REGISTRY.yaml`
- `AI_IMPLEMENTATION_GUIDE.md`
- `docs/state-machines/CLASSROOM_SESSION_STATE_MACHINE.md`
- `docs/architecture/12_TIMELINE_PRESENTATION_AND_RESUME.md`
- `contracts/openapi/openapi.yaml`
- `contracts/ctf/PACKAGE_LAYOUT.md`

## In Scope

- A teacher-only `POST /classes/{classId}/navigate` that resolves a **pinned**
  scene order against the session plan's scene list and lesson plan and commits a
  resolved `NAVIGATE_SCENE` through the existing aggregate.
- Student roster checks on a student's class, snapshot and pinned-scene reads.
- A teacher presentation stage on `/classroom/{classId}`: the pinned slide,
  previous/next and a slide picker; the returned snapshot is applied immediately.
- A student viewer on `/student/{classId}` that waits for the start, follows the
  session snapshot's current lesson scene, and offers no slide navigation.
- Tests, OpenAPI, READMEs and task traceability.

## Out of Scope

- The ordered per-class event stream, outbox, replay or push transport
  (`DEC-DATA-003` is `OPEN`; V1-002).
- SFU, audio, microphone, Raise Hand, STT and timeline narration (V0-013/V1).
- A durable scheduler or automatic start (`DEC-TECH-003` is `OPEN`).
- Any new service, broker, database or framework.

## Acceptance Criteria

- Only a principal with `class:write` can move a class; a student receives
  `403 INSUFFICIENT_SCOPE` and the snapshot is unchanged.
- The target is resolved from the package the session **pinned**, not the course's
  current publication; no source deck is parsed.
- A stale `expected_state_version` or a command after the class ended is refused
  and writes nothing. A duplicate `command_id` has one effect.
- A student cannot read a class, its snapshot or its pinned scenes unless the
  student is on that class's roster (`403 NOT_ENROLLED`).
- The teacher page shows the current pinned slide and can advance it. The returned
  snapshot updates the teacher's own view without a second read.
- The student page has no previous/next, picker or arrow-key navigation; it moves
  only when the authoritative snapshot's current scene changes.
- The student page waits for the teacher to start and joins by itself; a finished
  class is read as the last slide without live controls.
- The page says the update is a short poll, not a live stream, and that the
  narration is text only.
- The layout remains usable at 320px and does not regress the large-screen layout.
- `pytest`, `vitest`, `tsc --noEmit` and `npm run build` pass.

## Verification

- `backend/tests/test_teacher_drives_student_slide.py`
- `frontend/src/classroom/TeacherStage.test.tsx`
- `frontend/src/classroom/ClassroomPage.teacher.test.tsx`
- `frontend/src/classroom/scenePosition.test.ts`
- `frontend/src/student/StudentClassPage.test.tsx`
- Browser check with a teacher and a student on the same running class.
