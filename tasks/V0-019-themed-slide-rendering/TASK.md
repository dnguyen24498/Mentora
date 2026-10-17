# V0-019: Themed slide rendering (re-style the author's layout in the platform theme)

**Week:** W4  
**Status:** DONE (revised)  
**Owner:** Solo developer  
**Target:** V0

## Objective

Make the **default** fallback render a *themed* slide: the slide keeps the
**author's layout** — every object is drawn where and at the size the source put
it — while the **appearance is the platform's** (typeface, palette, chrome,
`MentoraTheme`). This removes the font-substitution problem entirely — the theme
owns its typefaces, so a deck with `Be Vietnam Pro` is no longer degraded — and
gives one consistent, accessible look across every uploaded deck.

Keeping the author's geometry is what makes the output readable: a render that
re-flows content has to *estimate* text metrics, and those estimates collide on
real, art-directed decks (banded headings, kickers, rules, small logos, picture
grids). With the source geometry authoritative, two objects can only overlap if
the author drew them overlapping, and the platform's own chrome is drawn only
where the source left the strip empty.

The existing faithful structural renderer stays available as an explicit mode, and
`DEC-TECH-005` (native PowerPoint rendering) stays `OPEN` — this task accepts no
renderer technology.

## Dependencies

- V0-005 (renderer interface, fidelity gate)
- V0-006 (scene/CTF builder)
- V0-018 (the effective-look IR this renderer consumes, and its geometry engine)

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

- A platform theme (`MentoraTheme`): palette, typeface stack, chrome (accent band,
  footer) — versioned, deterministic, part of the render config identity.
- A `ThemedSvgRenderer` that keeps the IR's geometry and swaps the styling in:
  typeface, run colour, fills, strokes, background palette, plus the theme's own
  accent band and footer. Placement, pictures, tables, text wrapping and
  auto-shrink are the V0-018 code, reached by subclassing the structural renderer
  and overriding only the styling seams.
- Colour mapping **by role** (`map_text`/`map_fill`/`map_line`): a light-on-dark
  pair in the source stays light-on-dark in the theme, so re-colouring can never
  hide text; source highlights are re-tinted.
- Platform chrome drawn only where the author left the strip empty, so the theme
  can never paint over content.
- A **content-completeness gate** replacing visual fidelity: nothing is
  re-selected, re-ordered, or clipped, so no code path can lose content. A frame
  that cannot hold its text (an `a:noAutofit` box) spills exactly as PowerPoint
  spills it and is reported per object as `TEXT_OVERFLOW:<object>`, degrading the
  scene for review.
- A new fidelity value `THEMED_RENDERED`; degraded themed output stays
  `DEGRADED_RENDERED`.
- The themed renderer owns its fonts, so `missing_fonts` is empty by construction
  and source typefaces never degrade a themed scene.
- A renderer factory with two modes (`themed` = default, `faithful`) and a
  `mode` query parameter on the render endpoints; `/renderer` reports the active
  capability. The theme is folded into the renderer's config hash and the package
  cache key binds the renderer identity, so a themed package can never be
  mistaken for a faithful one.
- Update contracts, architecture/ADR notes, corpus manifest, traceability.

## Out of Scope

- Accepting a native/compatible renderer (`DEC-TECH-005` stays OPEN).
- Vision analysis or diagram understanding: a chart/SmartArt is **not**
  re-styled; it degrades and asks for review rather than being silently flattened.
- LLM rewriting of slide text (a meaning change, not a render change).
- Font file embedding/licensing (the theme declares system-available stacks).
- Per-tenant theme authoring (theme is a single versioned default here).
- Re-flowing content into a platform-owned layout, or applying the theme's type
  scale to body text: the author's sizes are kept with the author's layout (see
  "Revision history").

## Acceptance Criteria

- The default render mode of the application is `themed`: a compiled deck reports
  `THEMED_RENDERED` and **no** missing fonts, even for a deck that uses an
  unavailable typeface.
- Every object is drawn inside its own source bounds (placement is the author's),
  so a designed deck is not stacked or re-flowed.
- A chart/SmartArt object degrades the scene (`DEGRADED_RENDERED` +
  `UNSUPPORTED_OBJECT:<kind>`) instead of being silently dropped.
- A frame that cannot hold its text is reported (`TEXT_OVERFLOW:<object>`) and
  degrades the scene; its text is still drawn, never truncated in silence.
- `mode=faithful` still produces the V0-018 structural render, and the two modes
  produce different assets and different package cache keys.
- Determinism: the same document, theme, and config produce byte-identical SVG.
- The fidelity gate is unchanged in force: `FAILED` blocks publication, degraded
  requires review.
- No new production dependency; `DEC-TECH-005` still OPEN; no native/compatible
  claim anywhere.

## Required Tests

- Theme identity is stable and config-sensitive; the theme version is part of the
  renderer's config hash.
- Layout is the author's: every labelled text is emitted inside its own source box
  (separated bands stay separated); a picture keeps its source frame.
- Typeface substitution: no `MISSING_FONT`, no source family in the output; the
  author's font *sizes* and emphasis are kept.
- Themed render carries the theme palette, font stack, and footer; a source
  background colour is mapped into the palette (contrast preserved); a source
  highlight is re-tinted.
- Chrome never overlaps: the accent band / footer are skipped when an object
  occupies that strip.
- Chart/SmartArt degrades with `UNSUPPORTED_OBJECT:`.
- Text overflow is drawn (not truncated) and degrades with `TEXT_OVERFLOW:`.
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

## Revision history

- **v1 (`7b5e8a0`):** themed mode *re-authored* the content — it classified each
  slide into an archetype and re-flowed the IR into a platform layout. On a real,
  art-directed deck that produced colliding, unreadable slides, because a re-flow
  must estimate text metrics and the estimates overlapped.
- **v2 (this revision):** themed mode *keeps the author's layout* and re-styles it
  (`ThemedSvgRenderer` subclasses `StructuralSvgRenderer`; only the styling seams
  are overridden). The re-flow, `classify_scene`, `content_refs`, and
  `CONTENT_DROPPED:` are removed — with the author's geometry authoritative and no
  clipping, no code path can lose content. Renderer identity
  `mentora-themed-svg@2.0.0`, theme `mentora-default` v1.1.0.

## Completion Evidence

**Commit:** `7b5e8a0` (v1), revised in this commit (v2).

**Backend:** `env -u PYTHONPATH .venv/bin/python -m pytest -q` → **310 passed**
(20 in `test_themed_renderer.py`, rewritten for the layout-preserving contract).

**Frontend:** `npx tsc --noEmit` clean; `npm test` → **38 passed**.

**Real deck (artifact `1e4c06bc-…`, tenant `university-001`, 28 slides), recompiled in the default mode:**

| | v1 (re-flow) | v2 (layout kept) |
| --- | --- | --- |
| fidelity | 28 × `THEMED_RENDERED` | 26 × `THEMED_RENDERED`, 2 × `DEGRADED_RENDERED` |
| missing fonts | none | none |
| layout | re-flowed (stacked/collided) | the author's, object for object |
| warnings | 0 | 3 × `TEXT_OVERFLOW:<object>` (the source's own `a:noAutofit` boxes) |
| review state | `READY` | `REVIEW_REQUIRED` (2 slides: source text does not fit its frame) |

Verification on the real deck is **structural**: of the 584 drawn `<text>` lines,
546 are emitted inside their own source object's box (text objects and table
frames both checked), 31 are the theme's footer chrome, and 7 are continuations of
the source's own overflow — i.e. every line the platform places is the author's
placement. The render's remaining overlaps are exactly the 16 text-box pairs the
*source* deck itself draws overlapping, inherited from the author, not introduced
by the render. No SVG rasterizer exists in this environment, so the SVGs are
reported for human inspection rather than graded visually. `GET /renderer` reports
`default_mode=themed`, `fidelity_ceiling=THEMED_RENDERED`, identity
`mentora-themed-svg@2.0.0`, theme `mentora-default` v1.1.0. Compile ≈ 0.9 s.

**Known characteristics (deliberate):**

- Slide 18 stays ~19.9 MB: the source photograph is preserved as content at its
  original resolution. Down-sampling would need an image codec (a new dependency)
  and is out of scope.
- The two `REVIEW_REQUIRED` slides are the source's own overflow: the deck uses
  `<a:noAutofit/>` on subtitle boxes that hold more text than their frame.
  PowerPoint spills that text; so do we (clipping would lose content), and the
  gate asks the teacher to confirm. The alarm is deliberately calibrated to a
  *whole line* landing past the frame: three further frames on this deck are
  tight enough that the last line's descenders dip ~20 px past the frame edge,
  which is normal typography and is not degraded.
- Text *sizes* are the author's, so the theme's palette/typeface/chrome are
  applied without re-scaling the author's hierarchy (and therefore without
  changing what fits where).
- A deck containing a chart/SmartArt would report `UNSUPPORTED_OBJECT:<kind>` and
  require review; this deck has none.
- Themed mode is proven to *not* be a native render: `DEC-TECH-005` is still
  `OPEN`, the notice is disclosure-first, and no classification claims otherwise.
