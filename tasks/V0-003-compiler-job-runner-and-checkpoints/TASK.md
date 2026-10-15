# V0-003: Compiler job runner and checkpoints

**Week:** W3  
**Status:** TODO  
**Owner:** Solo developer  
**Target:** V0

## Objective

Implement retryable staged compiler execution with deterministic job state.

## Dependencies

- V0-002

## Requirement IDs

- `DEC-CONTENT-001`
- `DEC-RUNTIME-003`
- `DEC-RELIABILITY-001`

## Required Reading

- `SOURCE_OF_TRUTH.md`
- `governance/DECISION_LEDGER.yaml`
- `governance/TERMINOLOGY_REGISTRY.yaml`
- `AI_IMPLEMENTATION_GUIDE.md`
- `docs/state-machines/COMPILER_JOB_STATE_MACHINE.md`

## In Scope

- Claim queued work safely.
- Persist stage/status/progress/error/retryability.
- Bound retry and cancellation.
- Deterministic stage checkpoint.
- Worker health and metrics.

## Out of Scope

- PPTX semantic extraction.
- AI enrichment.

## Acceptance Criteria

- Worker restart resumes safe stage.
- Two workers cannot process same lease unsafely.
- Permanent error does not loop.

## Required Tests

- Worker crash, retry, timeout, cancellation, duplicate delivery.

## Files/Areas Allowed to Change

- `workers/`
- `compiler/application/`
- `database/`
- `tests/integration/`
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
