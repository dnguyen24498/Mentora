# V0-016: V0 end-to-end golden path

**Week:** W8  
**Status:** TODO  
**Owner:** Solo developer  
**Target:** V0

## Objective

Prove upload-to-teaching flow in one automated E2E scenario.

## Dependencies

- V0-015

## Requirement IDs

- `DEC-CONTENT-001`
- `DEC-CONTENT-005`
- `DEC-DATA-005`
- `DEC-RUNTIME-004`

## Required Reading

- `SOURCE_OF_TRUTH.md`
- `governance/DECISION_LEDGER.yaml`
- `governance/TERMINOLOGY_REGISTRY.yaml`
- `AI_IMPLEMENTATION_GUIDE.md`
- `docs/product/V0_SCOPE.md`
- `docs/testing/TEST_STRATEGY.md`

## In Scope

- Automate upload, compile, review, publish, start, narrate, text question, answer, resume, restart, complete.
- Seed a small licensed/synthetic PPTX fixture.
- Capture latency/error metrics.

## Out of Scope

- Raise Hand.
- Group class.

## Acceptance Criteria

- Golden path passes repeatedly from clean database.
- Runtime process restart preserves class.
- No test bypasses normal API/domain boundaries.

## Required Tests

- Full E2E, restart E2E, failure smoke.

## Files/Areas Allowed to Change

- `tests/e2e/`
- `evaluation/`
- `scripts/`
- `docs/operations/`

## Quality Gate

All tests pass; no architecture contradiction; telemetry and traceability are updated; no new production dependency without an accepted ADR.

## Completion Evidence

- Link to commit/PR:
- Test command and result:
- Demo recording/screenshot:
- Metrics observed:
- Traceability rows added:
- Known limitations:
