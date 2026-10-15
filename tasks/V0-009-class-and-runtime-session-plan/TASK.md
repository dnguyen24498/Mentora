# V0-009: Class and runtime session plan

**Week:** W5  
**Status:** TODO  
**Owner:** Solo developer  
**Target:** V0

## Objective

Create class scheduling/start with exact pinned version tuple.

## Dependencies

- V0-008

## Requirement IDs

- `DEC-CONTENT-005`
- `DEC-DATA-005`

## Required Reading

- `SOURCE_OF_TRUTH.md`
- `governance/DECISION_LEDGER.yaml`
- `governance/TERMINOLOGY_REGISTRY.yaml`
- `AI_IMPLEMENTATION_GUIDE.md`
- `docs/architecture/03_DOMAIN_OWNERSHIP_AND_VERSIONING.md`
- `docs/sequences/CLASS_START.md`

## In Scope

- Class/session persistence.
- Resolve exact CTF/content/lesson/index/policy versions.
- Reject draft/incompatible package.
- Initial session state and snapshot.

## Out of Scope

- Group participants.
- SFU room.
- Distributed actor.

## Acceptance Criteria

- No runtime `latest` lookup.
- Pinned tuple survives restart.
- Only authorized enrollment can join.

## Required Tests

- Draft version rejected, incompatible index, duplicate start, cross-tenant join.

## Files/Areas Allowed to Change

- `backend/app/classroom/`
- `database/`
- `contracts/openapi/`
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
