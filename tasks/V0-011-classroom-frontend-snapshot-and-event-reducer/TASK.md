# V0-011: Classroom frontend snapshot and event reducer

**Week:** W5  
**Status:** TODO  
**Owner:** Solo developer  
**Target:** V0

## Objective

Render the authoritative classroom state and recover from refresh.

## Dependencies

- V0-010

## Requirement IDs

- `DEC-RUNTIME-004`

## Required Reading

- `SOURCE_OF_TRUTH.md`
- `governance/DECISION_LEDGER.yaml`
- `governance/TERMINOLOGY_REGISTRY.yaml`
- `AI_IMPLEMENTATION_GUIDE.md`
- `docs/architecture/15_FRONTEND_CLASSROOM_AND_STUDIO.md`
- `contracts/websocket/PROTOCOL.md`

## In Scope

- Classroom shell.
- Separate snapshot/event/media/UI stores.
- Scene display and controls.
- Duplicate/stale/gap behavior.
- Reconnect/resync UI.

## Out of Scope

- Microphone.
- Raise Hand.
- WebRTC.

## Acceptance Criteria

- Refresh restores scene and state.
- Duplicate/stale event ignored.
- Sequence gap requests resync and disables unsafe control.

## Required Tests

- Reducer unit tests, refresh E2E, sequence gap E2E, accessibility smoke.

## Files/Areas Allowed to Change

- `frontend/apps/classroom/`
- `frontend/packages/`
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
