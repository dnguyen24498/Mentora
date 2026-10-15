# V0-004: PPTX structural extraction

**Week:** W3  
**Status:** TODO  
**Owner:** Solo developer  
**Target:** V0

## Objective

Extract slide structure into internal Content IR.

## Dependencies

- V0-003

## Requirement IDs

- `DEC-CONTENT-001`
- `DEC-CONTENT-002`
- `DEC-CONTENT-006`
- `DEC-CONTENT-008`

## Required Reading

- `SOURCE_OF_TRUTH.md`
- `governance/DECISION_LEDGER.yaml`
- `governance/TERMINOLOGY_REGISTRY.yaml`
- `AI_IMPLEMENTATION_GUIDE.md`
- `docs/architecture/04_CONTENT_COMPILER.md`
- `docs/architecture/05_CONTENT_MODELS_AND_FIDELITY.md`

## In Scope

- Slide order/dimensions.
- Text runs and notes.
- Images, shapes, groups, tables, chart/media refs.
- Normalized bounds, reading order, stable source IDs.
- Warnings/provenance.

## Out of Scope

- Vision analysis.
- Perfect SmartArt reconstruction.
- Native animation recreation.

## Acceptance Criteria

- No slide is silently omitted.
- Content IR is internal and schema/version tagged.
- Known extraction corpus matches expected results.

## Required Tests

- Simple, notes, groups, table, chart, custom fonts, corrupted relationship fixtures.

## Files/Areas Allowed to Change

- `compiler/extractors/`
- `compiler/models/`
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
