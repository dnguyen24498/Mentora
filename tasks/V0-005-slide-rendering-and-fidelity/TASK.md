# V0-005: Slide rendering and fidelity

**Week:** W3  
**Status:** TODO  
**Owner:** Solo developer  
**Target:** V0

## Objective

Create fallback visual for every slide and explicit fidelity/warnings.

## Dependencies

- V0-003
- FND-002

## Requirement IDs

- `DEC-CONTENT-006`

## Required Reading

- `SOURCE_OF_TRUTH.md`
- `governance/DECISION_LEDGER.yaml`
- `governance/TERMINOLOGY_REGISTRY.yaml`
- `AI_IMPLEMENTATION_GUIDE.md`
- `docs/providers/DOCUMENT_RENDERER.md`
- `docs/testing/CONTENT_AND_AI_EVALUATION.md`

## In Scope

- Renderer adapter.
- Render images, renderer identity/version, missing fonts, warnings.
- Fidelity classification.
- Timeout/cancel/health behavior.

## Out of Scope

- Browser-native PowerPoint animation.
- Vision semantics.

## Acceptance Criteria

- Each slide has render or explicit FAILED.
- FAILED blocks publication.
- Same engine/config gives stable logical output.

## Required Tests

- Timeout, missing font, unsupported object, corrupted document, cancellation.

## Files/Areas Allowed to Change

- `compiler/renderers/`
- `compiler/validators/`
- `compiler/tests/`
- `evaluation/`

## Quality Gate

All tests pass; no architecture contradiction; telemetry and traceability are updated; no new production dependency without an accepted ADR.

## Completion Evidence

- Link to commit/PR:
- Test command and result:
- Demo recording/screenshot:
- Metrics observed:
- Traceability rows added:
- Known limitations:
