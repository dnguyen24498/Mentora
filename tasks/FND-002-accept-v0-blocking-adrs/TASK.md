# FND-002: Accept V0 blocking ADRs

**Week:** W1  
**Status:** TODO  
**Owner:** Solo developer  
**Target:** V0

## Objective

Decide only the technologies required for the V0 golden path.

## Dependencies

- FND-001

## Requirement IDs

- `DEC-RELIABILITY-001`

## Required Reading

- `SOURCE_OF_TRUTH.md`
- `governance/DECISION_LEDGER.yaml`
- `governance/TERMINOLOGY_REGISTRY.yaml`
- `AI_IMPLEMENTATION_GUIDE.md`
- `docs/adr/proposed/ADR-P003_DURABLE_WORKFLOW.md`
- `docs/adr/proposed/ADR-P005_RENDERER.md`
- `docs/adr/proposed/ADR-P008_SEARCH.md`
- `docs/adr/proposed/ADR-P009_CLOUD_REGION.md`

## In Scope

- Benchmark or document backend/database/object storage/job execution/renderer/search/neutral TTS choices.
- Record consequences, rollback, validation, and owner.
- Move accepted decisions to docs/adr/accepted and update ledger.

## Out of Scope

- SFU choice.
- STT choice.
- Multi-region design.
- Cloned voice.

## Acceptance Criteria

- Every V0 dependency has an accepted ADR or explicitly approved temporary mock.
- Decision ledger and traceability are updated.

## Required Tests

- ADR consistency validation.

## Files/Areas Allowed to Change

- `docs/adr/`
- `governance/`
- `CONSISTENCY_REPORT.md`

## Quality Gate

No V0 implementation is blocked by an unresolved infrastructure decision.

## Completion Evidence

- Link to commit/PR:
- Test command and result:
- Demo recording/screenshot:
- Metrics observed:
- Traceability rows added:
- Known limitations:
