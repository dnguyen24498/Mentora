# V0-006: Baseline scene and CTF builder

**Week:** W4  
**Status:** DONE  
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

- Link to commit/PR: `2e85a4f` (V0-004 + V0-005 landed as `d91b07f`)
- Test command and result: `cd backend && env -u PYTHONPATH .venv/bin/python -m pytest -q` -> **186 passed** (41 added by this task, all in `tests/test_package_builder.py`). Required tests covered: **golden package** (`test_golden_package_layout`, `test_golden_manifest_matches_the_contract`, `test_golden_documents_match_their_contracts`, `test_build_is_byte_stable_for_the_same_inputs`), **missing asset** (`test_missing_asset_is_rejected_by_the_builder`, `test_asset_bytes_missing_from_the_package_are_rejected`, `test_manifest_without_the_scene_asset_is_an_invalid_reference`), **invalid ref** (`test_compiler_asset_key_in_a_scene_is_an_invalid_ref`, `test_unknown_lesson_section_scene_is_an_invalid_ref`, `test_safe_marker_that_is_not_a_step_is_an_invalid_ref`, `test_step_referencing_an_unknown_object_is_an_invalid_ref`), **checksum mismatch** (`test_checksum_mismatch_detects_mutation`), **no Teaching Graph** (`test_no_teaching_graph_and_unindexed_by_default`).
- Demo recording/screenshot: `PackageBuildService.build("university-001", "1e4c06bc-…")` on the real 16.7 MB / 28-slide class deck -> stage `BUILDING_BASELINE`, prefix `packages/e54bc3f3-…`, **28 scenes + 1 lesson plan + 28 copied assets = 57 files / 576.8 KiB**, `validation.ok: true`, `requires_review: true` (degraded fidelity on the slides using the unavailable `Be Vietnam Pro`), `content_package_version cpv-892f814d4531dec7`, `lesson_plan_versions ["lp-4f186bb0ec531e0a"]`, `knowledge_index_version "unindexed"`, `teaching_graph_version null`, `course_version "3"`, ~3.6 s. Every stored checksum re-verified (0 mismatches); the package was then reloaded from object storage alone and re-validated against the contracts (`ok: true`), and a rebuild with the same `package_id`/`created_at` was byte-identical.
- Metrics observed: `compiler.package.built` (stage, package id, content version, scenes, files, bytes, renderer identity, `requires_review`, `knowledge_index_version`, `teaching_graph_version`) — counts and identities only, never slide text (`test_service_emits_structured_telemetry` asserts the deck text is absent from the record).
- Traceability rows added: `DEC-CONTENT-002` (builder/service/models + tests), `DEC-CONTENT-004` (`contracts/ctf/PACKAGE_LAYOUT.md`, layout/models/validator), `DEC-CONTENT-005` (`contracts/ctf/PACKAGE_LAYOUT.md`, layout/service), `DEC-CONTENT-007` (`contracts/ctf/PACKAGE_LAYOUT.md`, builder/models), `DEC-CONTENT-001` (package validator).
- Acceptance criteria: **package validates against contracts** (`validate_package` checks the manifest, every scene and the lesson plan against `contracts/ctf/*.schema.json` required fields/enums/`const`/`additionalProperties: false`, plus the cross-document references the schemas cannot express; the test module evaluates the *real* schema files with a dependency-free keyword evaluator because `jsonschema` is not installed and no production dependency may be added); **runtime package contains no source-parser dependency** (no source document may be listed — `SOURCE_DOCUMENT_PRESENT`; no file starts with the ZIP magic or contains source markup; no module under `app/compiler/package_builder/` imports `zipfile`, `xml.etree` or the extractor); **checksums detect mutation** (`CHECKSUM_MISMATCH` + `assert_package_ok` -> `PUBLICATION_BLOCKED`/409).
- Known limitations:
  - **No renderer/technology choice is made.** `DEC-TECH-005` stays `OPEN` (FND-002 is `TODO`); the package carries whatever the placeholder renderer produced (`STRUCTURAL_RENDERED`).
  - **One reveal step per scene.** V0-004 extracts no animation timing, so `steps` is a single `ALL_VISIBLE` step in reading order. Multi-step reveal is a later task.
  - **No persisted package table and no publication state.** The package is written under `packages/<package_id>/` in the object store with the manifest last as the commit point; `READY`/`REVIEW_REQUIRED` and the atomic publication transition are V0-008 (V0-003 owns stage persistence).
  - **`knowledge_index_version` is the sentinel `"unindexed"`** until V0-014.
  - **No HTTP endpoint.** The in-scope files are compiler-only, so the stage is reachable through `PackageBuildService`; the teacher-facing preview is V0-007.
  - Assets are copied into every package (self-contained), so a course with many versions duplicates its SVG fallbacks.
  - The `contracts/ctf/*.schema.json` field lists are mirrored as constants in `validators/package.py` (hand-rolled, like `validators/fidelity.py`); FND-003 will replace that with a real schema-validating job.

## Files/Areas Allowed to Change (as delivered)

- `compiler/package_builder/` -> `backend/app/compiler/package_builder/` (`__init__.py`, `layout.py`, `models.py`, `builder.py`, `service.py`)
- `compiler/validators/` -> `backend/app/compiler/validators/package.py` (+ `__init__.py` re-export)
- `contracts/ctf/` -> `contracts/ctf/PACKAGE_LAYOUT.md` (the layout/reference contract the three schemas leave open)
- `compiler/tests/` -> `backend/tests/test_package_builder.py` (same mapping precedent as V0-004/V0-005)

Also touched (required to keep the tree consistent):

`backend/app/compiler/__init__.py` (export the new stage), `backend/README.md`
(package builder section), `governance/TRACEABILITY_MATRIX.csv`,
`tasks/STATUS_BOARD.csv`, this task folder.

