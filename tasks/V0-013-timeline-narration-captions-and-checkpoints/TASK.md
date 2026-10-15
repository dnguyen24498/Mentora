# V0-013: Timeline narration captions and checkpoints

**Week:** W6  
**Status:** TODO  
**Owner:** Solo developer  
**Target:** V0

## Objective

Synchronize scene narration, captions, and resumable segments.

## Dependencies

- V0-011
- V0-012

## Requirement IDs

- `DEC-RUNTIME-005`
- `DEC-RUNTIME-006`

## Required Reading

- `SOURCE_OF_TRUTH.md`
- `governance/DECISION_LEDGER.yaml`
- `governance/TERMINOLOGY_REGISTRY.yaml`
- `AI_IMPLEMENTATION_GUIDE.md`
- `docs/architecture/12_TIMELINE_PRESENTATION_AND_RESUME.md`
- `docs/state-machines/TIMELINE_STATE_MACHINE.md`

## In Scope

- Segment model and audio generation.
- Marker/caption events.
- Pause/cancel/complete.
- Checkpoint before interruption.
- Resume with new segment.

## Out of Scope

- Word-perfect highlighting requirement.
- Student voice.

## Acceptance Criteria

- No old generation event mutates current presentation.
- Text fallback preserves lesson progression.
- Checkpoint resumes semantic segment, not raw bytes.

## Required Tests

- Late marker, duplicate marker, TTS without marker, cancel, restart/resume.

## Files/Areas Allowed to Change

- `backend/app/classroom/timeline/`
- `frontend/apps/classroom/`
- `tests/integration/`
- `tests/e2e/`

## Quality Gate

All tests pass; no architecture contradiction; telemetry and traceability are updated; no new production dependency without an accepted ADR.

## Completion Evidence

- Link to commit/PR:
- Test command and result:
- Demo recording/screenshot:
- Metrics observed:
- Traceability rows added:
- Known limitations:
