# V1-005: SFU teacher audio and reconnect

**Week:** W11  
**Status:** TODO  
**Owner:** Solo developer  
**Target:** V1 Pilot

## Objective

Integrate accepted SFU for shared teacher track before student publishing.

## Dependencies

- V1-001
- V0-013

## Requirement IDs

- `DEC-DEPLOY-002`
- `DEC-RELIABILITY-001`

## Required Reading

- `SOURCE_OF_TRUTH.md`
- `governance/DECISION_LEDGER.yaml`
- `governance/TERMINOLOGY_REGISTRY.yaml`
- `AI_IMPLEMENTATION_GUIDE.md`
- `docs/providers/SFU_PROVIDER.md`
- `docs/state-machines/MEDIA_CONNECTION_STATE_MACHINE.md`
- `docs/sequences/SFU_FAILURE.md`

## In Scope

- One room per class.
- Subscribe-only student token.
- One shared teacher track.
- TURN configuration.
- Track and connection telemetry.
- Reconnect/MEDIA_RECOVERING behavior.

## Out of Scope

- Student microphone publication.
- Multi-region migration.

## Acceptance Criteria

- Reconnect does not corrupt class state.
- SFU failure revokes unsafe floor and resumes at segment boundary.

## Required Tests

- TURN-only, reconnect, teacher republish, SFU callback duplicate/late.

## Files/Areas Allowed to Change

- `backend/app/media/`
- `frontend/apps/classroom/`
- `infra/`
- `tests/e2e/`
- `tests/chaos/`

## Quality Gate

All tests pass; no architecture contradiction; telemetry and traceability are updated; no new production dependency without an accepted ADR.

## Completion Evidence

- Link to commit/PR:
- Test command and result:
- Demo recording/screenshot:
- Metrics observed:
- Traceability rows added:
- Known limitations:
