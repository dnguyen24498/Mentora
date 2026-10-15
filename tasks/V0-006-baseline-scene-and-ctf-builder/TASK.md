# V0-006: Baseline scene and CTF builder

**Week:** W4  
**Status:** TODO  
**Owner:** Solo developer  
**Target:** V0

## Objective

Build validated runtime package without AI semantic dependency.

## Dependencies

- V0-004
- V0-005

## Requirement IDs

- `DEC-CONTENT-002`
- `DEC-CONTENT-004`
- `DEC-CONTENT-005`
- `DEC-CONTENT-007`

## Required Reading

- `SOURCE_OF_TRUTH.md`
- `governance/DECISION_LEDGER.yaml`
- `governance/TERMINOLOGY_REGISTRY.yaml`
- `AI_IMPLEMENTATION_GUIDE.md`
- `docs/architecture/05_CONTENT_MODELS_AND_FIDELITY.md`
- `docs/architecture/06_CTF_TEACHING_GRAPH_AND_LESSON.md`
- `contracts/ctf/manifest.schema.json`
- `contracts/ctf/scene.schema.json`
- `contracts/ctf/lesson-plan.schema.json`

## In Scope

- Map IR and renders into scenes/assets/provenance.
- Build fallback lesson order and safe segment markers.
- Create manifest and checksums.
- Validate internal references and schemas.

## Out of Scope

- Teaching Graph.
- Vision enrichment.
- Advanced quizzes.

## Acceptance Criteria

- Package validates against contracts.
- Runtime package contains no source-parser dependency.
- Checksums detect mutation.

## Required Tests

- Golden package, missing asset, invalid ref, checksum mismatch, no Teaching Graph.

## Files/Areas Allowed to Change

- `compiler/package_builder/`
- `compiler/validators/`
- `contracts/ctf/`
- `compiler/tests/`

## Quality Gate

All tests pass; no architecture contradiction; telemetry and traceability are updated; no new production dependency without an accepted ADR.

## Completion Evidence

- Link to commit/PR:
- Test command and result:
- Demo recording/screenshot:
- Metrics observed:
- Traceability rows added:
- Known limitations:
