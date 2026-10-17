# V0-019: Themed slide rendering (re-lay the content out in the platform theme)

**Week:** W4  
**Status:** DONE (revised)  
**Owner:** Solo developer  
**Target:** V0

## Objective

Make the **default** fallback render a *themed* slide whose **placement is the
platform's and whose content is the author's**: the slide's text, tables and
pictures are **re-laid out as one readable column in reading order**, in the
platform's type scale, typeface, palette and chrome (`MentoraTheme`).

A real deck is art-directed for the author's fonts on the author's grid: source
text frames overlap one another, sit outside the safe area, or hold more text than
they can show. Copying that geometry onto a different typeface (V0-019 v2)
reproduces the problem. The platform therefore imposes its **own** grid — and it
can do so without losing anything, because the *content* is unchanged: every
paragraph, list level, table cell and picture is drawn, exactly once.

Two properties follow from the design rather than from testing:

- **Nothing can overlap.** The flow measures and places in a single pass over a
  cursor, so a block always advances the cursor by its own measured height; the
  platform's page number is placed in a strip the flow may not enter, so the
  chrome cannot cover content either.
- **Nothing can be lost.** There is no re-selection, re-ordering or clipping. An
  object the platform cannot redraw becomes a labelled panel; content that does
  not fit even at the smallest readable scale is still drawn and *flagged* for
  review (`TEXT_OVERFLOW:<scene>`).

The themed renderer owns its typefaces, so the font-substitution problem
disappears by construction. The faithful structural renderer (V0-018) stays
available as an explicit mode, and `DEC-TECH-005` (native PowerPoint rendering)
stays `OPEN` — this task accepts no renderer technology.

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

- `renderers/flow.py`: a **pure flow-layout engine** over content blocks —
  paragraphs (level indent, bullet markers, bold/italic spans), tables (empty
  rows/columns dropped, source column proportions kept), pictures (rows of ≤4,
  aspect from the file header, `srcRect` crop), panels (chart/SmartArt). It
  measures and places in one pass, hoists a heading (kicker/title/subtitle over
  one hairline rule), reserves the footer strip, and fits by a discrete type-scale
  ladder then a continuous shrink to `theme.min_scale`, reporting `overflow`.
- `renderers/textmetrics.py`: a **font-free** advance table (Helvetica/Arial
  metrics, biased slightly wide) used for wrapping and measuring — no bundled font,
  no new dependency.
- `renderers/mentora_theme.py`: the platform theme in px — palette, type stack,
  type scale (`lead`/`body`/`caption` rows), grid (margin, footer strip, gaps),
  panel label. Versioned and folded into the renderer config hash.
- `ThemedSvgRenderer`: turns a scene into flow blocks (consecutive same-emphasis
  text boxes merge into one list; a text-less decorative shape is dropped), draws
  the flow's geometry as SVG in the theme, and applies the gate. The source's own
  sizes only select a type row, so an art-directed statistic still reads as one.
- A **content-completeness gate** replacing visual fidelity: `TEXT_OVERFLOW:<scene>`
  when the content does not fit even at the smallest readable scale (still drawn in
  full; the scene degrades for review and the page number is omitted so nothing is
  covered), and `UNSUPPORTED_OBJECT:<kind>` for a chart/SmartArt panel.
- A new fidelity value `THEMED_RENDERED`; degraded themed output stays
  `DEGRADED_RENDERED`. The themed renderer owns its fonts, so `missing_fonts` is
  empty by construction and source typefaces never degrade a themed scene.
- A renderer factory with two modes (`themed` = default, `faithful`) and a `mode`
  query parameter on the render endpoints; `/renderer` reports the active
  capability. The theme and renderer version are in the identity, so a themed
  package can never be mistaken for a faithful one.
- Update contracts, architecture/ADR notes, corpus manifest, traceability.

## Out of Scope

- Accepting a native/compatible renderer (`DEC-TECH-005` stays OPEN).
- Vision analysis or diagram understanding: a chart/SmartArt is not redrawn; it
  becomes a labelled panel, degrades, and asks for review.
- LLM rewriting of slide text (a meaning change, not a render change).
- Font file embedding/licensing (the theme declares system-available stacks and
  estimates metrics).
- Per-tenant theme authoring (the theme is a single versioned default here).
- Pagination of an over-full slide (it is flagged for review, not split).
- Copying the author's geometry, type sizes, colours, fills or decoration: that is
  v2, superseded (see "Revision history").

## Acceptance Criteria

- The default render mode is `themed`: a compiled deck reports `THEMED_RENDERED`
  and **no** missing fonts, even for a deck that uses an unavailable typeface.
- The slide is re-laid out: a heading is hoisted, the body flows as one column in
  reading order, and **no two drawn texts overlap**, even when the source frames
  do (asserted over the produced SVG, not argued).
- Content completeness: every source paragraph and table cell is drawn, and every
  picture is drawn or becomes a labelled panel — nothing is silently dropped.
- A chart/SmartArt degrades the scene (`DEGRADED_RENDERED` +
  `UNSUPPORTED_OBJECT:<kind>`).
- Content that cannot fit even at the smallest readable scale is reported
  (`TEXT_OVERFLOW:<scene>`), still drawn in full, and degrades the scene; the page
  number is omitted so nothing is covered.
- The heading and the body stay inside the page margins, and nothing but the page
  number enters the reserved footer strip.
- `mode=faithful` still produces the V0-018 structural render, and the two modes
  produce different assets and different package cache keys.
- Determinism: the same document, theme, and config produce byte-identical SVG.
- The fidelity gate is unchanged in force: `FAILED` blocks publication, degraded
  requires review.
- No new production dependency; `DEC-TECH-005` still OPEN; no native/compatible
  claim anywhere.

## Required Tests

- `backend/tests/test_flow_layout.py` (pure layout): no two placed boxes overlap
  (pairwise), reading order is preserved, the heading is hoisted, the footer strip
  is reserved, every line stays inside its column, the ladder/shrink/overflow
  behaviour, table column proportions/alignment/bands, picture aspect/rows/height
  budget, wrapping (including a word longer than the column), determinism.
- Theme identity is stable and config-sensitive; the theme version is part of the
  renderer's config hash.
- Layout is the platform's: overlapping source frames are re-laid out without
  overlap; every drawn text stays inside the page margins and out of the footer
  strip; the theme's type scale replaces the author's (a 40 pt title is not
  reproduced at 53 px).
- The look is the platform's: the theme palette/font stack/page number are drawn;
  no source colour, fill or highlight is reproduced; a text-less shape is dropped.
- Source emphasis and hierarchy survive: bold runs, list markers and indent, a
  lead/caption type row from the source's sizes.
- Table without grid, header band + row bands, numeric columns right-aligned.
- Picture re-framed from its own bytes (aspect), picture-only slide uses the body,
  a mixed slide gives pictures a share.
- Chart/SmartArt degrades with `UNSUPPORTED_OBJECT:`.
- Text overflow is drawn (not truncated), degrades with `TEXT_OVERFLOW:<scene>`,
  and omits the page number.
- Unresolved/absent media warns without degrading.
- Byte-identical repeat render.
- Factory/mode: `themed` is the default; `faithful` is structural; unknown mode is
  rejected. API: default compile is themed; `mode=faithful` returns the structural
  render; `/renderer` reports the themed ceiling.
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
  slide into an archetype and re-flowed the IR. On a real, art-directed deck that
  produced colliding, unreadable slides.
- **v2 (`d969f88`):** themed mode *kept the author's layout* and re-styled it
  (`ThemedSvgRenderer` subclassed `StructuralSvgRenderer`). This removed the
  collisions *introduced* by v1, but inherited the source deck's own: on the real
  deck, 2 slides required review and the source's 16 overlapping text-box pairs
  were reproduced, because the author's geometry is the thing that overlaps.
- **v3 (this revision):** themed mode **re-lays the content out** as one readable
  column in the platform theme (`flow.py` + `textmetrics.py` + a px `mentora_theme.py`
  + a standalone `ThemedSvgRenderer`). Position and measurement are the same
  computation, so overlap is impossible by construction and the source's
  overlapping frames are fixed rather than inherited. Source *hierarchy* survives
  through three theme type rows (`lead`/`body`/`caption`) chosen from the slide's
  own sizes. Renderer identity `mentora-themed-svg@3.0.0`, theme
  `mentora-default` v3.0.0.

## Completion Evidence

**Backend:** `env -u PYTHONPATH .venv/bin/python -m pytest -q` → **334 passed**
(new `test_flow_layout.py` = 22 pure-layout tests; `test_themed_renderer.py`
rewritten for the re-layout contract = 22 tests).

**Frontend:** `npx tsc --noEmit` clean; `npm test` → **38 passed**.

**Real deck** (artifact `1e4c06bc-…`, tenant `university-001`, 28 slides),
recompiled in the default mode:

| | v1 (re-flow, archetype) | v2 (layout kept) | v3 (re-laid out) |
| --- | --- | --- | --- |
| fidelity | 28 × `THEMED_RENDERED` | 26 + 2 degraded | **28 × `THEMED_RENDERED`** |
| warnings | 0 | 3 × `TEXT_OVERFLOW:<object>` | **none** |
| review state | `READY` | `REVIEW_REQUIRED` | **`publishable`, not requiring review** |
| overlaps | introduced by the re-flow | the source's own 16 pairs | **none** |

Structural verification of the 28 produced SVGs: every source paragraph and table
cell is present in the drawn text (481 `<text>` elements), **no two drawn texts
overlap**, every text lies inside the left/right margins, and the reserved footer
strip contains only the page number. The type scale ranges from 1.00 (6 slides)
to 0.49 (the densest slide), i.e. only 3 slides needed the continuous shrink below
the ladder floor. No SVG rasterizer exists in this environment, so the SVGs are
reported for human inspection (`/tmp/opencode/themed_v3/s01..s28.svg`) rather than
graded visually. `GET /renderer` reports `default_mode=themed`,
`fidelity_ceiling=THEMED_RENDERED`, identity `mentora-themed-svg@3.0.0`, theme
`mentora-default` v3.0.0.

**Known characteristics (deliberate):**

- Dense, art-directed slides shrink to the readable floor (the densest on this
  deck lands at 0.49 × the base scale — an ≈9 px body line at a 1280 px page).
  Fitting is preferred to overflow: the alternative is flagging the slide for
  review.
- The art-directed grid of this deck (one text box per fragment, `buNone`) means
  reading order is the only structure recoverable; a fragmented table drawn as
  separate text boxes reads as a list of its values, not as a table. The content is
  complete; the reading order is the source's own.
- Text metrics are *estimated* (no bundled font), so a line may break a word early.
- Slide 18 stays ~19.9 MB: the source photograph is preserved as content at its
  original resolution (down-sampling needs an image codec — a new dependency).
- Themed mode is proven to *not* be a native render: `DEC-TECH-005` is still
  `OPEN`, the notice is disclosure-first, and no classification claims otherwise.
