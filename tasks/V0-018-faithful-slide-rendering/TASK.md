# V0-018: Faithful slide rendering fidelity

**Week:** W4  
**Status:** DONE  
**Owner:** Solo developer  
**Target:** V0

## Objective

Make the fallback render of a slide look like the original slide: use the deck's
real theme (colours/fonts), slide/layout/master backgrounds and placeholder
inheritance, shape fill/line, run and paragraph formatting, embedded images, and
table cell styling — all dependency-free, from the package the compiler already
reads. The renderer technology stays an OPEN decision (`DEC-TECH-005`): this
raises the *fidelity of the local structural renderer*, it does not accept a
renderer.

## Dependencies

- V0-005 (renderer interface, fidelity gate)
- V0-006 (scene/CTF builder)

## Requirement IDs

- `DEC-CONTENT-001`
- `DEC-CONTENT-006`
- `DEC-CONTENT-007`
- `DEC-CONTENT-008`
- `DEC-DATA-005`
- `DEC-RELIABILITY-001`

## Required Reading

- `SOURCE_OF_TRUTH.md`
- `governance/DECISION_LEDGER.yaml`
- `governance/TERMINOLOGY_REGISTRY.yaml`
- `AI_IMPLEMENTATION_GUIDE.md`
- `docs/architecture/04_CONTENT_COMPILER.md`
- `docs/architecture/05_CONTENT_MODELS_AND_FIDELITY.md`
- `docs/providers/DOCUMENT_RENDERER.md`
- `docs/adr/proposed/ADR-P005_RENDERER.md`
- `contracts/ctf/scene.schema.json`

## In Scope

- Extend the Content IR (schema version bump) with presentation styling:
  theme-resolved colours, slide background, shape fill/line/geometry/rotation,
  body properties (anchor/insets), paragraph alignment/indent/bullets, run
  formatting (size/bold/italic/underline/colour/typeface), table column/row
  metrics and cell fills, picture crop.
- Resolve the slide -> layout -> master -> theme inheritance chain (placeholder
  geometry and text defaults, master `p:txStyles`).
- Extract absolute bounds for shapes inside groups (group child transform).
- Feed referenced media bytes to the render stage (the compiler holds them; the
  renderer never opens the source package) and inline them into the slide SVG.
- Rewrite the local structural renderer to draw that styling (backgrounds,
  preset geometries, fills/gradients/lines, real font sizes and alignment,
  word-wrapped text, images, table grids, z-order).
- Keep the fidelity classification honest: still `STRUCTURAL_RENDERED` ceiling,
  `DEGRADED_RENDERED` when fonts are missing or an object cannot be drawn.

## Out of Scope

- Accepting a native/compatible renderer (`DEC-TECH-005` stays OPEN).
- Charts, SmartArt, WordArt, equations, 3D, transitions/animations (still
  structural placeholders; never silently claimed as faithful).
- Font file embedding/licensing; text metrics are estimated, not measured.
- Vision analysis.

## Acceptance Criteria

- A slide that uses theme colours, fonts, fills, images, and placeholder
  inheritance renders those in its SVG (covered by tests).
- A picture no longer renders as a grey box when its part resolves.
- The renderer input stays the IR plus injected media: it never reads the source
  package (`DEC-CONTENT-001`).
- Determinism: the same document and config still produce byte-identical SVG.
- The fidelity gate is unchanged: `FAILED` still blocks publication, degraded
  still requires review.
- No new production dependency.

## Required Tests

- Theme colour/font resolution (scheme colour -> sRGB, clrMap).
- Placeholder inheritance (title/body size from master, geometry from layout).
- Shape fill/line/geometry/rotation extraction.
- Run/paragraph formatting extraction (size, bold, italic, align, bullet).
- Slide background extraction.
- Group child absolute bounds.
- Picture media inlining and crop.
- Table metrics/cell fill extraction.
- Renderer: rendered SVG contains the resolved colour/font-size/image data.
- Renderer: determinism (byte-identical repeat render).
- Renderer: oversized media degrades that scene instead of failing the deck.

## Files/Areas Allowed to Change

- `compiler/models/`
- `compiler/extractors/`
- `compiler/renderers/`
- `compiler/render_service.py`
- `compiler/package_builder/`
- `compiler/validators/`
- `backend/tests/`
- `contracts/ctf/`
- `evaluation/`
- `frontend/src/` (IR types / render display only)
- `docs/`

## Quality Gate

- `env -u PYTHONPATH .venv/bin/python -m pytest -q`
- `cd frontend && npx tsc --noEmit && npm test`
- No new production dependency; `DEC-TECH-005` still OPEN.

## Completion Evidence

**What changed**

- **IR v1.2.0** (`compiler/models/ir.py`, `EXTRACTOR_VERSION` 1.2.0): scenes carry
  an effective `background`; objects carry `fill` (solid/gradient/none),
  `line` (colour/width/dash), `geometry` + `custom_path` (custGeom as a unit-square
  SVG path), `rotation`/`flip_h`/`flip_v`, `anchor`/`insets`/`autofit`/`font_scale`,
  `media_ref`/`media_type`/`crop`, `table_columns`/`table_rows`/`table_cells`;
  paragraphs carry `align`/`bullet`/`margin_left_emu`/`indent_emu`/spacing and
  `line_spacing`/`line_spacing_pt`; runs carry `font`/`size_pt`/`bold`/`italic`/
  `underline`/`color`/`highlight`.
- **New extractor modules**: `extractors/ooxml.py` (namespaces, rel/part helpers),
  `extractors/theme.py` (theme colours/fonts, `p:clrMap`, colour modifiers,
  fills/lines, preset + custom geometry), `extractors/style.py` (run/paragraph/body
  formats, level merging, transforms, placeholder defs, `p:txStyles`),
  `compiler/media.py` (image part reader + `media_ref` collection).
- **`extractors/pptx.py`**: resolves slide → layout → master → theme (cached per
  layout), merges master `p:txStyles` ← master placeholder ← layout placeholder ←
  shape, applies group transforms so child bounds are absolute slide coordinates.
- **`renderers/base.py` + `render_service.py`**: `RenderRequest.media` (image bytes
  keyed by IR `media_ref`, injected by the compiler), `RenderConfig`
  `max_asset_bytes` (28 MiB) and `max_inline_media_bytes` (16 MiB).
- **`renderers/structural.py`** (renderer 2.0.0): backgrounds, gradients, preset +
  custom geometry, fills/strokes/dashes, rotation/flip, real font sizes with
  word-wrap/alignment/bullets/auto-shrink, inline `data:` images with `srcRect`
  crop, table grids with cell fills, connectors, placeholders.
- **Contracts/docs**: `contracts/ctf/scene.schema.json` documents every new field;
  `RENDER_PLACEHOLDER_NOTICE` reworded to "structural SVG render reproduced from the
  slide's own styling — not a native PowerPoint render"; `AGENTS.md`,
  `backend/README.md`, `governance/TRACEABILITY_MATRIX.csv` updated; frontend IR
  types extended (no component behaviour change).

**Verification**

- `env -u PYTHONPATH .venv/bin/python -m pytest -q` → **275 passed** (241 before;
  +25 `tests/test_extractor_styling.py`, +9 `tests/test_renderer_fidelity.py`).
- `cd frontend && npx tsc --noEmit && npm test` → clean; **38 passed**.
  `npm run build` → OK.
- New `tests/test_renderer_fidelity.py` (9 tests): theme fill + inherited master
  font/size appear in the SVG, text is placed at its box origin, rotation is a
  transform, a line-less shape is not stroked, pictures are inlined with a crop
  clip, table cells keep their fill and column ratio, an inherited unavailable font
  degrades the scene, an over-budget picture becomes a labelled placeholder
  (`MEDIA_BUDGET_EXCEEDED:`) without failing the scene, and a repeat render is
  byte-identical.
- **Real deck** (`1e4c06bc-…`, 16.7 MB, 28 slides) via the running API:
  `POST /artifacts/{id}/compile` → 28/28 `RENDERED`, 0 failed, renderer 2.0.0,
  total 21.6 MB, byte-identical asset refs across two runs; `GET …/renders/{order}`
  matches a locally rendered SVG byte for byte. `POST …/review-package` rebuilds the
  package (57 files) at `REVIEW_REQUIRED` / `publishable: true`, and the notice now
  says what the render actually is.
- Fixes found while inspecting real output: theme colour slots were never read
  (every theme colour resolved to `None`); line colours nested in `a:ln/a:solidFill`
  were dropped (352 strokes in the real deck); `srcRect` crop read `left/top/right/
  bottom` instead of `l/t/r/b`; `spcPts` was treated as a font-size multiple instead
  of absolute leading (over-shrinking titles); text x was relative to the box
  instead of absolute; `MISSING_FONT` ignored fonts inherited from `p:txStyles`.
- Pinned expectations updated: `evaluation/manifests/render-fidelity.json`
  (engine 2.0.0), `tests/test_package_builder.py` fallback-asset hash.

**Known limits (unchanged and still honest)**

- Still a **structural** renderer (`STRUCTURAL_RENDERED` ceiling); `DEC-TECH-005`
  remains `OPEN`. No native/compatible claim is made anywhere.
- Fonts: typeface names are resolved but no font file is embedded/licensed, and text
  metrics are estimated — the deck therefore reports
  `DEGRADED_RENDERED` + `MISSING_FONT:Be Vietnam Pro` and requires review.
- Charts/SmartArt/animation/3D/exotic effects remain placeholders.
- Non-inlinable media (EMF/WMF/TIFF) and over-budget pictures become labelled
  placeholders with warnings; this is reported without changing fidelity.

