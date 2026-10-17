# V0-019: Themed slide rendering (re-author in the platform theme)

**Week:** W4  
**Status:** TODO  
**Owner:** Solo developer  
**Target:** V0

## Objective

Make the **default** fallback render a *re-authored* slide: the extracted content
(text, images, tables, notes) is re-laid out in a platform-controlled theme
(typography, palette, grid, spacing) instead of reproducing the source deck's own
geometry. This removes the font-substitution problem entirely — the theme owns
its typefaces, so a deck with `Be Vietnam Pro` is no longer degraded — and gives
one consistent, accessible look across every uploaded deck.

The source deck's *own* layout is not reproduced by this mode. That is the
product decision: content in, our theme out. The existing faithful structural
renderer stays available as an explicit mode, and `DEC-TECH-005` (native
PowerPoint rendering) stays `OPEN` — this task accepts no renderer technology.

## Dependencies

- V0-005 (renderer interface, fidelity gate)
- V0-006 (scene/CTF builder)
- V0-018 (the effective-look IR this renderer consumes)

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
- `docs/architecture/18_ACCESSIBILITY_AND_INCLUSION.md`
- `docs/providers/DOCUMENT_RENDERER.md`
- `docs/adr/proposed/ADR-P005_RENDERER.md`
- `contracts/ctf/scene.schema.json`

## In Scope

- A platform theme (`MentoraTheme`): palette, type scale, font stacks, grid,
  spacing, footer — versioned, deterministic, part of the render config identity.
- A new `ThemedSvgRenderer` that maps the Content IR into that theme: title block,
  body flow (bulleted/paragraph text), media band with correct aspect ratio, and
  styled tables. Content is **re-flowed, never re-selected**: every text
  paragraph, picture, and table cell in the IR is placed.
- A **content-completeness gate** replacing visual fidelity: emit
  `CONTENT_DROPPED:<ref>` for any IR content not placed and `TEXT_OVERFLOW:<ref>`
  when content cannot fit; both degrade the scene and require review.
- A new fidelity value `THEMED_RENDERED`; degraded themed output stays
  `DEGRADED_RENDERED`.
- The themed renderer owns its fonts, so `missing_fonts` is empty by construction
  and source typefaces never degrade a themed scene.
- A renderer factory with two modes (`themed` = default, `faithful`) and a
  `mode` query parameter on the render endpoints; `/renderer` reports the active
  capability. The package cache key binds the renderer identity, so a themed
  package can never be mistaken for a faithful one.
- Update contracts, architecture/ADR notes, corpus manifest, traceability.

## Out of Scope

- Accepting a native/compatible renderer (`DEC-TECH-005` stays OPEN).
- Vision analysis or diagram understanding: a chart/SmartArt is **not**
  re-authored; it degrades and asks for review rather than being silently
  flattened.
- LLM rewriting of slide text (a meaning change, not a render change).
- Font file embedding/licensing (the theme declares system-available stacks).
- Per-tenant theme authoring (theme is a single versioned default here).

## Acceptance Criteria

- The default render mode of the application is `themed`: a compiled deck reports
  `THEMED_RENDERED` and **no** missing fonts, even for a deck that uses an
  unavailable typeface.
- A themed render contains every IR text paragraph, picture, and table cell — a
  deck that fits never reports `CONTENT_DROPPED`.
- A chart/SmartArt object degrades the scene (`DEGRADED_RENDERED` +
  `UNSUPPORTED_OBJECT:<kind>`) instead of being silently dropped.
- `mode=faithful` still produces the V0-018 structural render, and the two modes
  produce different assets and different package cache keys.
- Determinism: the same document, theme, and config produce byte-identical SVG.
- The fidelity gate is unchanged in force: `FAILED` blocks publication, degraded
  requires review.
- No new production dependency; `DEC-TECH-005` still OPEN; no native/compatible
  claim anywhere.

## Required Tests

- Theme identity is stable and config-sensitive.
- Archetype classification is deterministic for title / bullets / table / media.
- Themed render carries the theme palette, type scale, and footer.
- Completeness: every paragraph and table cell appears; an IR with all content
  produces no `CONTENT_DROPPED`.
- Unavailable source font does **not** degrade a themed scene; the theme font is
  used.
- Chart/SmartArt degrades with `UNSUPPORTED_OBJECT:`.
- Text overflow degrades with `TEXT_OVERFLOW:` instead of dropping content.
- Picture aspect ratio is preserved (dimensions read from the image bytes).
- Byte-identical repeat render.
- Factory/mode: `themed` is the default; `faithful` is structural; unknown mode
  is rejected.
- API: default compile is themed; `mode=faithful` returns the structural render;
  `/renderer` reports the themed ceiling.
- Corpus: the manifest declares the themed engine and its outcomes.

## Files/Areas Allowed to Change

- `compiler/models/`
- `compiler/renderers/`
- `compiler/render_service.py`
- `compiler/validators/`
- `api/`
- `publication/`
- `settings`/config (render mode only)
- `backend/tests/`
- `contracts/ctf/`
- `contracts/openapi/`
- `evaluation/`
- `frontend/src/` (fidelity label / notice display only)
- `docs/`
- `tasks/`

## Quality Gate

- `env -u PYTHONPATH .venv/bin/python -m pytest -q`
- `cd frontend && npx tsc --noEmit && npm test`
- No new production dependency; `DEC-TECH-005` still OPEN.

## Completion Evidence

**Backend:** `env -u PYTHONPATH .venv/bin/python -m pytest -q` → **305 passed** (was 280;
25 new tests across `test_themed_renderer.py` and `test_renderer_factory.py`).

**Frontend:** `npx tsc --noEmit` clean; `npm test` → **38 passed**.

**Real deck (artifact `1e4c06bc-…`, tenant `university-001`, 28 slides), recompiled in the default mode:**

| | Before (V0-018 faithful) | After (V0-019 themed default) |
| --- | --- | --- |
| fidelity | 28 × `DEGRADED_RENDERED` | 28 × `THEMED_RENDERED` |
| missing fonts | 28 × `MISSING_FONT:Be Vietnam Pro` | none |
| warnings | 84 | 0 |
| review state | `REVIEW_REQUIRED` | `READY` |
| publishable | true | true |

The package rebuilt as `pkg-6bdb4cd5181aaa1a` (57 files, 28 scenes) with the themed
renderer identity; `GET /renderer` reports `default_mode=themed`,
`fidelity_ceiling=THEMED_RENDERED`, theme `mentora-default` v1.0.0. Compile 0.77 s,
review build 4.38 s.

**Known characteristics (deliberate):**

- Slide 18 stays ~19.9 MB: the source photograph is preserved as content at its
  original resolution. Down-sampling would need an image codec (a new dependency)
  and is out of scope.
- A deck containing a chart/SmartArt would report `UNSUPPORTED_OBJECT:<kind>` and
  require review; this deck has none, so all 28 scenes are clean.
- Themed mode is proven to *not* be a native render: `DEC-TECH-005` is still
  `OPEN`, the notice is disclosure-first, and no classification claims otherwise.

