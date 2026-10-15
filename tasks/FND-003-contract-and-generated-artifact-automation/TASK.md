# FND-003: Contract and generated artifact automation

**Week:** W1  
**Status:** TODO  
**Owner:** Solo developer  
**Target:** V0

## Objective

Make contracts and generated architecture executable in CI.

## Dependencies

- FND-001

## Requirement IDs

- `DEC-RUNTIME-003`

## Required Reading

- `SOURCE_OF_TRUTH.md`
- `governance/DECISION_LEDGER.yaml`
- `governance/TERMINOLOGY_REGISTRY.yaml`
- `AI_IMPLEMENTATION_GUIDE.md`
- `docs/architecture/16_API_WEBSOCKET_COMMAND_AND_EVENT_CONTRACTS.md`

## In Scope

- Implement schema validation script.
- Validate OpenAPI.
- Generate ARCHITECTURE_FULL from numbered files.
- Validate all DEC references exist.
- Validate traceability CSV shape.

## Out of Scope

- Application endpoints.
- Client generation beyond a minimal proof.

## Acceptance Criteria

- make check-specs succeeds.
- Intentional invalid schema and unknown decision reference fail CI.

## Required Tests

- Positive and negative script tests.

## Files/Areas Allowed to Change

- `scripts/`
- `contracts/`
- `governance/`
- `.github/ or CI config`
- `Makefile`

## Quality Gate

Specification drift is automatically detected.

## Completion Evidence

- Link to commit/PR:
- Test command and result:
- Demo recording/screenshot:
- Metrics observed:
- Traceability rows added:
- Known limitations:
