# V1-003: Raise Hand queue and cancellation

**Week:** W10  
**Status:** TODO  
**Owner:** Solo developer  
**Target:** V1 Pilot

## Objective

Implement queue state only, without media or STT.

## Dependencies

- V1-002

## Requirement IDs

- `DEC-TURN-001`
- `DEC-TURN-002`
- `DEC-TURN-003`
- `DEC-TURN-004`
- `DEC-RUNTIME-003`

## Required Reading

- `SOURCE_OF_TRUTH.md`
- `governance/DECISION_LEDGER.yaml`
- `governance/TERMINOLOGY_REGISTRY.yaml`
- `AI_IMPLEMENTATION_GUIDE.md`
- `docs/architecture/11_RAISE_HAND_AND_TURN_CONTROL.md`
- `docs/state-machines/TURN_MANAGER_STATE_MACHINE.md`
- `contracts/commands/raise-hand.schema.json`
- `contracts/commands/cancel-hand.schema.json`
- `contracts/events/hand-queued.schema.json`

## In Scope

- Raise/cancel commands.
- Enrollment/class/policy checks.
- One active request per student.
- FIFO projection, cooldown/rate/queue limit.
- Dedup/replay.

## Out of Scope

- STT reservation.
- Floor token.
- Microphone.

## Acceptance Criteria

- Raise Hand never requests mic.
- Duplicate commands/request do not duplicate queue item.
- Replay reconstructs queue.

## Required Tests

- First/duplicate/new-ID duplicate/cancel twice/inactive/unenrolled/rate-limit/replay.

## Files/Areas Allowed to Change

- `backend/app/classroom/turn/`
- `frontend/apps/classroom/`
- `contracts/`
- `tests/property/`
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
