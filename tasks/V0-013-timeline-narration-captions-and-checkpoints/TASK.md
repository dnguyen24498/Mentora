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
- Shared teacher audio to remote students: that is the SFU path (`V1-005`;
  `DEC-TECH-004` is `OPEN`). V0 narration plays on the presenting teacher's tab.
- Any decided OmniVoice/TTS provider (`DEC-TECH-007` is `OPEN`). V0 uses the
  provider-neutral port and its deterministic local adapter.

## Acceptance Criteria

- No old generation event mutates current presentation.
- Text fallback preserves lesson progression.
- Checkpoint resumes semantic segment, not raw bytes.

## Required Tests

- Late marker, duplicate marker, TTS without marker, cancel, restart/resume.

## Files/Areas Allowed to Change

The original allowlist named `frontend/apps/classroom/`, `tests/integration/` and
`tests/e2e/`, which do not exist in this repository (the shipped frontend is
`frontend/src/`, and backend tests live under `backend/tests/`). Corrected to the
actual layout:

- `backend/app/classroom/timeline/`
- `backend/app/classroom/{service,router}.py` (pin the narration read; mount the route)
- `backend/app/api/app.py` (construct the timeline service and include its router)
- `backend/app/speech/` (only if a contract field is required; no provider decision)
- `backend/app/providers/` (only the existing deterministic adapter; no vendor adapter)
- `contracts/openapi/openapi.yaml`, `contracts/events/narration-stream.schema.json`
- `backend/tests/classroom/timeline/`, `backend/tests/integration/`
- `frontend/src/audio/`, `frontend/src/classroom/`, `frontend/src/student/`,
  `frontend/src/api/client.ts`, `frontend/src/settings/`
- `docs/state-machines/TIMELINE_STATE_MACHINE.md`,
  `docs/architecture/12_TIMELINE_PRESENTATION_AND_RESUME.md`,
  `docs/providers/TTS_VOICE_PROVIDER.md`, `AGENTS.md`,
  `backend/README.md`, `frontend/README.md`

## Quality Gate

All tests pass; no architecture contradiction; telemetry and traceability are updated; no new production dependency without an accepted ADR.

## Completion Evidence

- Link to commit/PR:
- Test command and result:
- Demo recording/screenshot:
- Metrics observed:
- Traceability rows added:
- Known limitations:
