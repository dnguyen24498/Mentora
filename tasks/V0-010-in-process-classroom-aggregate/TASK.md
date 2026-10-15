# V0-010: In-process Classroom Aggregate

**Week:** W5  
**Status:** TODO  
**Owner:** Solo developer  
**Target:** V0

## Objective

Implement deterministic single-session state with commands, events, invariants, and snapshots.

## Dependencies

- V0-009

## Requirement IDs

- `DEC-RUNTIME-001`
- `DEC-RUNTIME-003`
- `DEC-RUNTIME-004`

## Required Reading

- `SOURCE_OF_TRUTH.md`
- `governance/DECISION_LEDGER.yaml`
- `governance/TERMINOLOGY_REGISTRY.yaml`
- `AI_IMPLEMENTATION_GUIDE.md`
- `docs/architecture/08_RUNTIME_CONTROL_PLANE.md`
- `docs/architecture/09_CLASSROOM_ACTOR_AND_RECOVERY.md`
- `docs/state-machines/CLASSROOM_SESSION_STATE_MACHINE.md`
- `contracts/snapshots/classroom-snapshot.schema.json`

## In Scope

- Aggregate handle/apply/validate/snapshot.
- Start/end, scene navigation, checkpoint commands/events.
- State version and command dedup.
- Snapshot persistence/restore.

## Out of Scope

- Distributed ownership.
- Message broker.
- Raise Hand.

## Acceptance Criteria

- All classroom mutations pass through aggregate.
- Duplicate command has one logical effect.
- Restart restores pinned tuple and scene position.

## Required Tests

- Reducer tests, invalid transition, duplicate command, snapshot round trip, corrupted snapshot.

## Files/Areas Allowed to Change

- `backend/app/classroom/`
- `backend/tests/classroom/`
- `database/`
- `governance/TRACEABILITY_MATRIX.csv`

## Quality Gate

All tests pass; no architecture contradiction; telemetry and traceability are updated; no new production dependency without an accepted ADR.

## Completion Evidence

- Link to commit/PR:
- Test command and result:
- Demo recording/screenshot:
- Metrics observed:
- Traceability rows added:
- Known limitations:
