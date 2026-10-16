# V0-004: PPTX structural extraction

**Week:** W3  
**Status:** DONE  
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

- Link to commit/PR: _(uncommitted working tree)_
- Test command and result: `cd backend && env -u PYTHONPATH .venv/bin/python -m pytest -q` -> **78 passed** (24 of them added by this task).
- Demo recording/screenshot: `POST /artifacts/{id}/extract` on the real 16.7 MB class deck returns `schema_version=content-ir/1.1.0`, 28/28 slides, 386 paragraphs, 512 text runs, 78 pictures, 3 tables (65 cells), notes on slides 4/7/28, fonts `["Arial", "Be Vietnam Pro"]`, contiguous `reading_order`, **0 warnings**.
- Metrics observed: corpus `evaluation/manifests/pptx-corpus.json` v0.2 -> 11 executable items, all matching (`tests/test_extraction_corpus.py`). Movies/`smartart`, `equation`, `semantic_reveal`, `scan` are declared `not_yet_covered`.
- Traceability rows added: `DEC-CONTENT-001` (extractor), `DEC-CONTENT-002` (IR model, corpus), `DEC-CONTENT-006` (IR fidelity fields), `DEC-CONTENT-008` (notes, extractor tests).
- Known limitations:
  - Chart/SmartArt series data is not extracted (only the chart part reference); SmartArt reconstruction and native animation are out of scope by `TASK.md`.
  - Theme font references (`+mj-lt`) resolve to "unknown", not to a family; theme parts are not read.
  - Images are referenced by `media_ref`; no endpoint serves the bytes (the fallback render + serving arrives with V0-005).
  - `fidelity` is provisional at extraction time (`STRUCTURAL_RENDERED`) and is finalised by the render stage (V0-005).
  - Job-stage persistence/retry (`EXTRACTING` checkpoints) is V0-003 and is not implemented here.

## Files/Areas Allowed to Change (as delivered)

- `compiler/models/` -> `backend/app/compiler/models/`
- `compiler/extractors/` -> `backend/app/compiler/extractors/`
- `compiler/tests/` -> `backend/tests/`
- `evaluation/` -> `evaluation/manifests/pptx-corpus.json`

Also touched (required to keep the tree consistent): `backend/app/compiler/__init__.py`,
`backend/app/compiler/service.py`, `backend/app/api/app.py`, `backend/tests/conftest.py`,
`backend/README.md`, `governance/TRACEABILITY_MATRIX.csv`, this task folder.

