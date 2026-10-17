# V0-019: Slide rendering — source-layout default with platform fallbacks (plus the themed re-layout)

**Week:** W4  
**Status:** DONE (revised v5)  
**Owner:** Solo developer  
**Target:** V0

## Objective

> **v5 (current default).** The product owner rejected the re-layout as unlike
> their deck: *"generate layout as same as original presentation, but if some
> components are not compatible please use default format of our app."* The
> **default** mode is therefore the **source layout** (the V0-018
> `StructuralSvgRenderer`): it reproduces the author's own layout and styling and
> paints anything it cannot reproduce — an unavailable source font, a
> chart/SmartArt, an un-inlinable picture — in the **platform's look, in place**,
> as a *warning* rather than a degradation. The themed re-layout below is retained
> as the opt-in `themed` mode (`?mode=themed`).

The `themed` mode (below) makes the fallback render a *themed* slide where **the
grouping is the author's, the content is the author's and the look is the
platform's**: the slide's
rows and columns are recovered from the source geometry, and each cell's text,
tables and pictures are **re-laid out inside that cell**, in the platform's type
scale, typeface, palette and chrome (`MentoraTheme`).

A real deck is art-directed for the author's fonts on the author's grid: source
text frames overlap one another, sit outside the safe area, or hold more text than
they can show. Copying that geometry onto a different typeface (V0-019 v2)
reproduces the problem; flattening it into one column (v3) destroys the *grouping*
— a three-card summary read as one column becomes a meaningless list of fragments
with every icon on its own line. So the platform imposes its **own** grid *inside
the author's grouping*: the rows and columns are recovered from the source boxes
and kept, while type, size, colour, fill, spacing and exact geometry are
re-authored. It can do so without losing anything, because the *content* is
unchanged: every paragraph, list level, table cell and picture is drawn, exactly
once.

Three properties follow from the design rather than from testing:

- **The grouping survives.** The author's rows and columns are recovered from the
  source boxes by a binary widest-gap XY-cut, so an icon stays beside its label and
  a card keeps its parts. A column is only cut when both sides are a substantial
  share of the region, so a narrow icon column never splits from its label, and a
  full-width object forbids a column cut through it.
- **Nothing can overlap.** Within a cell the flow measures and places in a single
  pass over a cursor, so a block always advances the cursor by its own measured
  height; across a row the cells take disjoint x-intervals; and the platform's page
  number is placed in a strip the flow may not enter — so the chrome cannot cover
  content either.
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

- `renderers/flow.py`: a **pure layout engine** with two layers.
  - **Structure recovery**: from the content items' source boxes a binary
    widest-gap XY-cut (`structure`) builds `Run | Row | Stack` — a vertical gap is
    a `Row` (cells side by side, with source-proportional weights), a horizontal
    gap is a `Stack`. A column split is only taken when both sides are at least
    `theme.min_column_share` of the region width (`_columns_are_substantial`), so a
    narrow icon column stays in its label's row. Same-key neighbours coalesce back
    into one `Run` (one bullet per source text box), same-axis nesting flattens,
    and the recursion is depth-capped (`MAX_STRUCTURE_DEPTH`).
  - **Placement**: over the resolved node, blocks — paragraphs (level indent,
    bullet markers, bold/italic spans), tables (empty rows/columns dropped, source
    column proportions kept), pictures (rows of ≤4, aspect from the file header,
    `srcRect` crop), panels (chart/SmartArt). It measures and places in one pass,
    hoists a heading (kicker/title/subtitle over one hairline rule), reserves the
    footer strip, and fits by a discrete type-scale ladder then a continuous shrink
    to `theme.min_scale`, reporting `overflow`. A row cell that draws more than one
    block becomes a **card**: the content is inset by `theme.card_pad_px` and a flat
    `theme.surface` rounded panel is emitted (before the content, and excluded from
    the no-overlap geometry).
- `renderers/textmetrics.py`: a **font-free** advance table (Helvetica/Arial
  metrics, biased slightly wide) used for wrapping and measuring — no bundled font,
  no new dependency.
- `renderers/mentora_theme.py`: the platform theme in px — palette, type stack,
  type scale (`lead`/`body`/`caption` rows), grid (margin, footer strip, gaps),
  panel label. Versioned and folded into the renderer config hash.
- `ThemedSvgRenderer`: turns a scene into flow items (carrying each object's source
  box) and blocks (consecutive same-emphasis text boxes merge into one list; a
  text-less decorative shape is dropped), recovers the structure, draws its
  geometry as SVG in the theme, and applies the gate. The source's own sizes only
  select a type row, so an art-directed statistic still reads as one.
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
- The slide is re-laid out *inside the author's grouping*: the rows and columns
  are recovered, a heading is hoisted, each cell flows in reading order, and **no
  two drawn texts overlap**, even when the source frames do (asserted over the
  produced SVG, not argued).
- The author's grouping is kept where it carries meaning: an icon stays on the row
  of its own label, a multi-object cell is drawn as one card with a flat surface
  panel behind it, and a full-width object forbids a column cut through it.
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

- `backend/tests/test_flow_layout.py` (pure layout): structure recovery — a
  no-gap region is one run, two side-by-side cells are a row, a narrow side is
  read as rows not columns (icon beside label), a row of cards is one flat row, a
  full-width line is not glued into the row below it, adjacent same-key lines are
  re-joined, different keys are not; row cells take disjoint columns with
  source-proportional widths; a multi-block cell draws a card surface behind its
  content (and a single-block cell does not); plus no two placed boxes overlap
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
- Grouping is the author's: a card grid keeps every icon beside its own label; a
  card cell is drawn as a flat surface panel with no border; a plain list slide
  stays one column and gets no panels; regrouping never drops a fragment.
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
- **v3 (`ae68632`):** themed mode **re-laid the content out** as one readable
  column in the platform theme (`flow.py` + `textmetrics.py` + a px `mentora_theme.py`
  + a standalone `ThemedSvgRenderer`). Position and measurement are the same
  computation, so overlap is impossible by construction and the source's
  overlapping frames are fixed rather than inherited. Source *hierarchy* survives
  through three theme type rows (`lead`/`body`/`caption`) chosen from the slide's
  own sizes. Renderer identity `mentora-themed-svg@3.0.0`, theme
  `mentora-default` v3.0.0. **Superseded by v4.**
- **v4 (`f528425`):** v3's single column destroyed the author's
  *grouping* — on the real deck an icon row and its label row were emitted as two
  separate rows, which reads as nonsense. v4 recovers the source geometry's rows
  and columns (`flow.structure`, a binary widest-gap XY-cut) and re-authors only
  the look inside each cell, adding flat card surfaces for multi-object cells. New
  principle: **the grouping is the author's, the content is the author's, the look
  is the platform's.** Renderer identity `mentora-themed-svg@4.0.0`, theme
  `mentora-default` v4.0.0.
- **v5 (this revision):** the product owner still did not want the re-layout. The
  **default flips back to the source layout** and gains a per-component platform
  fallback: the default mode is `faithful` (`StructuralSvgRenderer`,
  `local-structural-svg@3.0.0`), which reproduces the author's layout, styling,
  pictures and tables and draws (a) an unavailable source font as the platform's
  type stack — deterministically, `FONT_SUBSTITUTED:<family>`, with the frame
  shrunk to stay inside the author's box — and (b) a chart/SmartArt/graphic frame
  or an un-inlinable picture as a flat platform panel labelled in place
  (`UNSUPPORTED_OBJECT:<kind>`, `MEDIA_*`). None of these lowers the fidelity or
  sets `requires_review`. `themed@4.0.0` is kept as the opt-in mode; the fidelity
  validator now escalates only `DEGRADED_RENDERED` and reports a font substitution
  as a warning; `review.render_notice` and the corpus baseline were re-based.

## Completion Evidence

**Commit:** `02ca28f` (v5). Earlier revisions: `7b5e8a0` (v1), `d969f88` (v2),
`ae68632` (v3), `f528425` (v4).

### v5 — the default (source layout + platform fallback)

**Backend:** `env -u PYTHONPATH .venv/bin/python -m pytest -q` → **351 passed**
(the corpus manifest was re-baselined in place; the renderer/fidelity, corpus,
package-builder, publication and review tests were updated to the new default).

**Frontend:** `npx tsc --noEmit` clean; `npm test` → **38 passed**.

**Real deck** (artifact `1e4c06bc-…`, tenant `university-001`, 28 slides) compiled
in the default mode (`POST /artifacts/{id}/compile` with no `mode`):

| | v4 default (themed) | v5 default (source layout) |
| --- | --- | --- |
| renderer | `mentora-themed-svg@4.0.0` | **`local-structural-svg@3.0.0`** |
| fidelity | 28 × `THEMED_RENDERED` | **28 × `STRUCTURAL_RENDERED`** |
| warnings | none | **28 × `FONT_SUBSTITUTED:Be Vietnam Pro`** |
| review state | `publishable`, not requiring review | **`publishable`, not requiring review** |
| validation issues | none | 28 × `FONT_SUBSTITUTED` at **warning** severity |

Structural verification of the 28 produced SVGs (`/tmp/opencode/verify_source_v5.py`,
extractor text vs drawn text: 573 `<text>` elements): **every source text token is
present on all 28 slides (0 missing)**, no drawn text box leaves the canvas, and
the only drawn-text overlaps are the **source deck's own overlapping frames**
(4 slides — a heading's second line inside the body frame's band, the big number
beside its unit label), which a source-layout render is *supposed* to reproduce.
One frame on slide 10 spilled out of its card because our substituted font wrapped
to three lines where the author's font needed two; the v5 fit rule (shrink a
substituted frame to its own box) removed it. Platform fallback panels were
verified directly on the `chart` and `media` corpus items (flat `theme.surface`
panel, hairline `theme.border`, platform type stack, labelled in place).

**Deliberate, documented limits of v5:** the renderer reproduces the author's
geometry, so the author's own overlaps are reproduced; text metrics are still
estimated (a substituted typeface can wrap a line a word earlier than PowerPoint
would); charts/SmartArt are platform panels, not charts.

### v4 evidence (the opt-in `themed` mode)

**Backend:** `env -u PYTHONPATH .venv/bin/python -m pytest -q` → **350 passed**
(`test_flow_layout.py` = 34 pure-layout tests, +12 structure/card tests;
`test_themed_renderer.py` = 26, +4 grouping tests).

**Frontend:** `npx tsc --noEmit` clean; `npm test` → **38 passed**.

**Real deck** (artifact `1e4c06bc-…`, tenant `university-001`, 28 slides),
recompiled with `?mode=themed`:

| | v1 (re-flow, archetype) | v2 (layout kept) | v3 (one column) | v4 (grouping kept) |
| --- | --- | --- | --- | --- |
| fidelity | 28 × `THEMED_RENDERED` | 26 + 2 degraded | 28 × `THEMED_RENDERED` | **28 × `THEMED_RENDERED`** |
| warnings | 0 | 3 × `TEXT_OVERFLOW:<object>` | none | **none** |
| review state | `READY` | `REVIEW_REQUIRED` | `publishable` | **`publishable`, not requiring review** |
| overlaps | introduced by the re-flow | the source's own 16 pairs | none | **none** |
| smallest type scale | — | — | 0.49 | **0.76** |

Structural verification of the 28 produced SVGs: every source paragraph and table
cell is present in the drawn text (573 `<text>` elements), **no two drawn boxes
overlap** (pairwise over the emitted geometry), every box lies inside the
left/right margins and out of the reserved footer strip, and 59 card surfaces are
emitted. The recovered structure is sane on the real slides — e.g. slide 21 is a
`ROW(3)` of cards, each card a `STACK` of `ROW([icon],[label])` lines, and all 11
of its icons sit on the row of their own label. Because cards now stay side by
side, far less vertical space is spent on gaps: the smallest type scale rose from
0.49 (v3) to 0.76. No SVG rasterizer exists in this environment, so the SVGs are
reported for human inspection (`/tmp/opencode/themed_v4/s01..s28.svg`) rather than
graded visually. `GET /renderer?mode=themed` reports
`fidelity_ceiling=THEMED_RENDERED`, identity `mentora-themed-svg@4.0.0`, theme
`mentora-default` v4.0.0 (the *default* mode reported by `GET /renderer` is now
`faithful`, `local-structural-svg@3.0.0`, v5).

**Known characteristics (deliberate):**

- Dense, art-directed slides shrink toward the readable floor (the densest on this
  deck lands at 0.76 × the base scale). Fitting is preferred to overflow: the
  alternative is flagging the slide for review.
- Structure recovery is heuristic: when a region has both a qualifying column gap
  and a qualifying row gap, columns win only if both sides are a substantial share
  of the width, otherwise rows win. That keeps an icon with its label, but an
  unusual composition (a wide icon beside a narrow label, say) can still be read as
  a stack. Nothing is lost either way — only the visual grouping differs.
- A table fragmented into separate source text boxes still reads as a list of its
  values, not as a table: the boxes are grouped, but they are not table objects.
  The content is complete; the reading order is the source's own.
- Text metrics are *estimated* (no bundled font), so a line may break a word early.
- Slide 18 stays ~19.9 MB: the source photograph is preserved as content at its
  original resolution (down-sampling needs an image codec — a new dependency).
- Themed mode is proven to *not* be a native render: `DEC-TECH-005` is still
  `OPEN`, the notice is disclosure-first, and no classification claims otherwise.
