# V0-001: Course and source artifact persistence

**Week:** W2  
**Status:** TODO  
**Owner:** Solo developer  
**Target:** V0

## Objective

Create minimal durable course/version/source/job models.

## Dependencies

- FND-002
- FND-003

## Requirement IDs

- `DEC-DATA-001`
- `DEC-CONTENT-005`

## Required Reading

- `SOURCE_OF_TRUTH.md`
- `governance/DECISION_LEDGER.yaml`
- `governance/TERMINOLOGY_REGISTRY.yaml`
- `AI_IMPLEMENTATION_GUIDE.md`
- `docs/architecture/03_DOMAIN_OWNERSHIP_AND_VERSIONING.md`
- `docs/data/DATA_MODEL_AND_TRANSACTIONS.md`

## In Scope

- Create migrations for course, course version, source artifact, compiler job.
- Add tenant IDs, status, checksums, optimistic versions and indexes.
- Add repository interfaces and transaction tests.

## Out of Scope

- Teacher Studio UI.
- Compilation logic.

## Acceptance Criteria

- Migrations apply from empty database.
- Duplicate course version and artifact constraints are enforced.
- Cross-tenant repository access is rejected.

## Required Tests

- Migration test.
- Repository integration tests.
- Constraint tests.

## Files/Areas Allowed to Change

- `database/`
- `backend/app/courses/`
- `backend/tests/`
- `docs/data/`
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
