# V1-007: Streaming STT lifecycle

**Week:** W11  
**Status:** TODO  
**Owner:** Solo developer  
**Target:** V1 Pilot

## Objective

Replace fake transcript with accepted STT while preserving floor invariants.

## Dependencies

- V1-006

## Requirement IDs

- `DEC-TURN-005`
- `DEC-TURN-006`
- `DEC-RELIABILITY-001`

## Required Reading

- `SOURCE_OF_TRUTH.md`
- `governance/DECISION_LEDGER.yaml`
- `governance/TERMINOLOGY_REGISTRY.yaml`
- `AI_IMPLEMENTATION_GUIDE.md`
- `docs/providers/STT_PROVIDER.md`
- `contracts/events/transcript-finalized.schema.json`
- `docs/sequences/STT_FINAL_TIMEOUT.md`

## In Scope

- Reserve before floor.
- Start after track ACK.
- Partial UI-only transcript.
- Finish/VAD/timeout/revoke.
- Final transcript, release, quality flag.
- Typed fallback.

## Out of Scope

- Advanced diarization.
- Multiple simultaneous speakers.

## Acceptance Criteria

- No STT session without floor.
- Every path releases reservation.
- Partial never triggers answer.

## Required Tests

- Capacity unavailable, final timeout, duplicate finish, disconnect, provider failure.

## Files/Areas Allowed to Change

- `backend/app/speech/`
- `backend/app/classroom/turn/`
- `frontend/apps/classroom/`
- `tests/contract/`
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
