# V0-008: Atomic publication and index version

**Week:** W4  
**Status:** TODO  
**Owner:** Solo developer  
**Target:** V0

## Objective

Publish immutable package and compatible knowledge-index identity.

## Dependencies

- V0-006
- V0-007

## Requirement IDs

- `DEC-CONTENT-005`
- `DEC-DATA-005`
- `DEC-RUNTIME-003`

## Required Reading

- `SOURCE_OF_TRUTH.md`
- `governance/DECISION_LEDGER.yaml`
- `governance/TERMINOLOGY_REGISTRY.yaml`
- `AI_IMPLEMENTATION_GUIDE.md`
- `docs/state-machines/PUBLICATION_STATE_MACHINE.md`
- `docs/architecture/07_PUBLICATION_AND_REVIEW.md`
- `docs/data/OUTBOX_SNAPSHOT_AND_RETENTION.md`

## In Scope

- Approve/seal/index/commit state flow.
- Immutable package storage.
- Knowledge-index version record.
- Transactional publication metadata/outbox.
- Published version retrieval.

## Out of Scope

- Full semantic index content.
- LMS notification.

## Acceptance Criteria

- Partial failure never exposes published version.
- Published bytes cannot be overwritten.
- Correction creates new version.

## Required Tests

- Crash between stages, duplicate publish, index failure, checksum failure, read old version.

## Files/Areas Allowed to Change

- `backend/app/publication/`
- `workers/`
- `database/`
- `tests/integration/`

## Quality Gate

All tests pass; no architecture contradiction; telemetry and traceability are updated; no new production dependency without an accepted ADR.

## Completion Evidence

- Link to commit/PR:
- Test command and result:
- Demo recording/screenshot:
- Metrics observed:
- Traceability rows added:
- Known limitations:
