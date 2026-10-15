# V1-004: Mock floor orchestration and invariants

**Week:** W10  
**Status:** TODO  
**Owner:** Solo developer  
**Target:** V1 Pilot

## Objective

Complete Raise Hand state machine using deterministic fake capabilities.

## Dependencies

- V1-003

## Requirement IDs

- `DEC-TURN-004`
- `DEC-TURN-006`
- `DEC-TURN-007`
- `DEC-TURN-008`

## Required Reading

- `SOURCE_OF_TRUTH.md`
- `governance/DECISION_LEDGER.yaml`
- `governance/TERMINOLOGY_REGISTRY.yaml`
- `AI_IMPLEMENTATION_GUIDE.md`
- `docs/sequences/RAISE_HAND_SUCCESS.md`
- `docs/sequences/STT_CAPACITY_UNAVAILABLE.md`
- `docs/sequences/AUDIO_CANCEL_TIMEOUT.md`
- `docs/testing/INVARIANT_AND_CHAOS_TESTS.md`

## In Scope

- Fake STT reservation.
- Safe marker/checkpoint.
- Fake audio cancel ACK.
- Fenced floor model.
- Fake audio publication and transcript.
- Finish/finalize/answer/resume.
- Property-based invariant tests.

## Out of Scope

- Real SFU.
- Real microphone.
- Real STT.

## Acceptance Criteria

- Thousands of generated command sequences preserve all floor/audio/STT invariants.
- Every failure releases reservation/floor.

## Required Tests

- Property tests, timeout races, disconnect, duplicate finish, actor failover.

## Files/Areas Allowed to Change

- `backend/app/classroom/turn/`
- `backend/app/classroom/timeline/`
- `dev/mocks/`
- `tests/property/`
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
