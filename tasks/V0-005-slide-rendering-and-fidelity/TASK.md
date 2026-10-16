# V0-005: Slide rendering and fidelity

**Week:** W3  
**Status:** DONE  
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

- Link to commit/PR: _(uncommitted working tree)_
- Test command and result: `cd backend && env -u PYTHONPATH .venv/bin/python -m pytest -q` -> **145 passed** (67 added by this task: `test_renderers.py` 19, `test_fidelity_validator.py` 17, `test_render_service.py` 19, `test_render_corpus.py` 12). Required tests covered: timeout (`RENDER_TIMEOUT`, retryable, bounded), missing font (`MISSING_FONT:`, `DEGRADED_RENDERED`, `requires_review`), unsupported object (`UNSUPPORTED_OBJECT:`), corrupted document (corrupt relationships/packages degrade or fail with a stable code), cancellation (`CANCELLED` distinct from `FAILED`).
- Demo recording/screenshot: `POST /artifacts/1e4c06bc-.../compile` on the real 16.7 MB / 28-slide class deck -> 28/28 slides `RENDERED`, one content-addressed SVG each (`asset_bytes` 138 704, ~1.8 s), fidelity `DEGRADED_RENDERED` because `Be Vietnam Pro` is not in the renderer's declared font set, `publishable: true`, `requires_review: true`, `job_status: EXTRACTED`. `GET /artifacts/{id}/renders/0` -> `200 image/svg+xml` (2 444 B).
- Metrics observed: `evaluation/manifests/render-fidelity.json` v0.1 -> 8 executable items matching exactly (fidelity, missing fonts, publishability, review flag); `render_similarity`, `font_issue_count`, `review_seconds_per_slide` declared for the evaluation stage. Structured telemetry (`compiler.render.started|completed|unavailable`, `compiler.renderer.health`) emits counts/durations/fidelity/font names only — never slide text.
- Traceability rows added: `DEC-CONTENT-006` (renderer interface, structural renderer, validator, render service, corpus), `DEC-RELIABILITY-001` (renderer base, telemetry, test double).
- Acceptance criteria: **each slide has a render or explicit FAILED** (`MISSING_RENDER` is a hard error; cancelled/failed scenes are recorded per slide); **FAILED blocks publication** (`publishable: false`; `assert_publishable()` raises `PUBLICATION_BLOCKED`/409; the job drops to `FAILED`); **same engine/config gives stable logical output** (byte-identical SVG, identical asset key and fidelity across runs, asserted in `test_renderers.py` and `test_render_corpus.py`).
- Known limitations:
  - **No renderer technology is chosen.** `DEC-TECH-005` stays `OPEN` (FND-002 is `TODO`); the local structural renderer is a placeholder behind `DocumentRenderer`, and output is `STRUCTURAL_RENDERED` (approximate layout), never native/compatible.
  - Assets are served live by re-deriving them; there is no persisted render table (`GET .../renders/{order}` recompiles). Stage/lease/checkpoint persistence is V0-003.
  - Fidelity is per-slide; per-object fidelity and pixel-diff scoring (`render_similarity`) need the real renderer and the evaluation corpora.
  - `evaluation/manifests/render-fidelity.json` does not yet cover `smartart`, `equation`, `semantic_reveal`, `scan`, `video` (declared under `not_yet_covered`).
  - The frontend does not display renders yet — that is V0-007 (teacher review preview).

## Files/Areas Allowed to Change (as delivered)

- `compiler/renderers/` -> `backend/app/compiler/renderers/`
- `compiler/validators/` -> `backend/app/compiler/validators/`
- `compiler/tests/` -> `backend/tests/`
- `evaluation/` -> `evaluation/manifests/render-fidelity.json`

Also touched (required to keep the tree consistent / to change the interface):
`contracts/openapi/openapi.yaml` (contract updated first), `backend/app/api/app.py`,
`backend/app/compiler/__init__.py`, `backend/app/common/errors.py` (three stable
codes the API must return: `RENDER_FAILED`, `RENDERER_UNAVAILABLE`,
`PUBLICATION_BLOCKED`), `backend/tests/conftest.py`, `backend/tests/fixtures.py`
(text is now XML-escaped like a real part), `backend/README.md`,
`governance/TRACEABILITY_MATRIX.csv`, this task folder, and
`frontend/vite.config.ts` (proxy `/renderer`, `/docs`, `/openapi.json` to the
backend; without it the dev server answered the new endpoint with the SPA
fallback, i.e. `index.html`).

