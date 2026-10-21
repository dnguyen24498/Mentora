# V0-026: Classroom hub and automatic play

**Week:** W8
**Status:** DONE
**Owner:** Solo developer
**Target:** V0

## Objective

Give the product one classroom page. `/classroom` lists every class the signed-in
person may see — the tenant's schedule for a teacher, their roster for a student —
and is the only place a class is started. A teacher presses **Start**, the class
opens, and its **pinned** slides advance by themselves; a student opens the same
class and watches, with no slide controls and with the slide's own text as the
narration.

This removes the separate "learning page" destination from the navigation: the
classroom is the lesson. `/learn/{artifactId}` stays reachable for links already
shared, but it is no longer the way a lesson is delivered.

## Dependencies

- V0-011 (classroom client snapshot projection)
- V0-024 (teacher-assigned roster and a started class is joinable)
- V0-025 (teacher-driven pinned-slide navigation)

## Requirement IDs

- `DEC-CONTENT-004`
- `DEC-CONTENT-005`
- `DEC-DATA-003` (boundary only: the ordered stream remains `OPEN`)
- `DEC-DATA-004`
- `DEC-RUNTIME-003`
- `DEC-RUNTIME-007`
- `DEC-TECH-003` (boundary only: no durable scheduler is introduced)
- `DEC-TECH-007` (boundary only: the narration is text, never a voice provider)

## Required Reading

- `SOURCE_OF_TRUTH.md`
- `governance/DECISION_LEDGER.yaml`
- `governance/TERMINOLOGY_REGISTRY.yaml`
- `AI_IMPLEMENTATION_GUIDE.md`
- `docs/state-machines/CLASSROOM_SESSION_STATE_MACHINE.md`
- `docs/architecture/12_TIMELINE_PRESENTATION_AND_RESUME.md`
- `contracts/openapi/openapi.yaml`
- `frontend/README.md`

## In Scope

- `src/classroom/ClassroomHomePage.tsx` (`/classroom`): the class list scoped by
  the server, a teacher's real `POST /classes/{id}/start`, a running class's join
  link, and a scheduled class that waits and re-reads on a client-local timer.
- `src/classroom/playbackTiming.ts`: the dwell rule — the slide's text and notes
  counted as words at the Settings `teachingWpm`, with a floor and a ceiling.
- Auto-play in `src/classroom/TeacherStage.tsx`, seeded from `?autoplay=1`, with a
  Pause/Play control, one timer per slide, a stop at the last slide, and no
  retry loop after a refused or failed command.
- Routing: `/classroom` is the hub for every role; `/classroom/{id}` serves the
  teacher's stage or the student's viewer by role; `/student` and `/student/{id}`
  stay as aliases.
- Navigation: the Learn entry is removed; Classroom is the hub entry and needs no
  id, for a teacher and a student alike.
- Tests, READMEs and task traceability.

## Out of Scope

- The ordered per-class event stream, outbox, replay or push transport
  (`DEC-DATA-003` is `OPEN`; V1-002).
- A durable scheduler, worker or automatic start (`DEC-TECH-003` is `OPEN`). The
  teacher's tab is the clock and closing it stops the presentation.
- Voice, TTS, STT, LLM narration, the SFU, microphone or Raise Hand
  (`DEC-TECH-007` is `OPEN`; V1).
- Any new backend endpoint, table, service or dependency. The hub composes
  existing verbs only.
- Changing the aggregate, the snapshot schema or the published package.

## Acceptance Criteria

- A signed-in person reaches every class the server returns for them from
  `/classroom`; a student gets only their roster because the server scopes
  `GET /classes` by role, not because the page filters.
- A teacher's **Start class** calls the real idempotent
  `POST /classes/{id}/start` and opens `/classroom/{id}?autoplay=1`. A refusal is
  reported on the row (`CLASS_NOT_READY`/`VERSION_NOT_PUBLISHED`, …) and the page
  does not navigate, so nothing appears to have started.
- With `?autoplay=1` the teacher's stage advances one pinned slide per dwell and
  applies each returned snapshot immediately. Pause stops it, Play resumes it,
  and the last slide stops it rather than looping.
- A refused or failed navigate pauses auto-play and resynchronises once; it does
  not retry a stale `expected_state_version` in a loop.
- The student's page still has no previous/next, picker or arrow keys and moves
  only when the authoritative snapshot's current lesson scene changes; the
  narration remains the slide's own text and notes, labelled **text only**.
- Every scene is read from the package the session pinned
  (`DEC-CONTENT-005`); the hub and the stage never parse the source deck and
  never ask for the course's current publication.
- The pages remain usable at 320px and do not regress the large-screen layout.
- `pytest`, `vitest`, `tsc --noEmit` and `npm run build` pass.

## Verification

- `frontend/src/classroom/ClassroomHomePage.test.tsx`
- `frontend/src/classroom/TeacherStage.test.tsx`
- `frontend/src/classroom/playbackTiming.test.ts`
- `frontend/src/App.test.tsx`
- `frontend/src/router.test.tsx`
- `frontend/src/student/JoinClassPage.test.tsx`
- Browser check with a teacher starting a class and a student opening it.
