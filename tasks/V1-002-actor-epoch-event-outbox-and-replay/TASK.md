# V1-002: Actor epoch event outbox and replay

**Week:** W9  
**Status:** TODO  
**Owner:** Solo developer  
**Target:** V1 Pilot

## Objective

Upgrade aggregate to recoverable single-owner runtime.

## Dependencies

- V1-001
- V0-010

## Requirement IDs

- `DEC-RUNTIME-001`
- `DEC-RUNTIME-007`
- `DEC-DATA-003`
- `DEC-DATA-004`

## Required Reading

- `SOURCE_OF_TRUTH.md`
- `governance/DECISION_LEDGER.yaml`
- `governance/TERMINOLOGY_REGISTRY.yaml`
- `AI_IMPLEMENTATION_GUIDE.md`
- `docs/architecture/09_CLASSROOM_ACTOR_AND_RECOVERY.md`
- `docs/sequences/ACTOR_FAILOVER.md`
- `docs/data/OUTBOX_SNAPSHOT_AND_RETENTION.md`

## In Scope

- Ownership and epoch acquisition.
- Ordered command ingress selected by ADR.
- Event/outbox atomic persistence.
- Snapshot/replay and pending-effect reconciliation.
- Graceful drain.

## Out of Scope

- Cross-region failover.
- Raise Hand business flow.

## Acceptance Criteria

- Old epoch cannot mutate state or authorize effect.
- Crash before/after effect recovers without duplicate logical side effect.

## Required Tests

- Stale owner, rebalance, crash before/after commit/effect, snapshot replay, duplicate delivery.

## Files/Areas Allowed to Change

- `backend/app/classroom/actor/`
- `backend/app/events/`
- `database/`
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
