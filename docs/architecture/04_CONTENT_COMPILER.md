# Content Compiler Architecture

**Status:** Reconciled implementation specification  
**Baseline:** Mentora Architecture Baseline 1.0  
**Purpose:** Specify secure deterministic compilation and selective enrichment.

## Dependencies

- `SOURCE_OF_TRUTH.md`
- `governance/DECISION_LEDGER.yaml`
- `governance/TERMINOLOGY_REGISTRY.yaml`

## Normative Language

**MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** are requirements. Technology choices explicitly marked `PROPOSED` are not binding until accepted.

---

## Pipeline

Validate/scan/store -> structural extraction -> rendering router -> media processing -> reveal semantics -> Content IR -> baseline builder -> selective AI enrichment -> validation.

## Rendering

Record engine/version/fonts/warnings/provenance and classify native-compatible-structural-degraded-failed. Failed blocks publication; degraded meaning requires review. A component the renderer draws in the platform look, and a source font it had to substitute, are **warnings** on a structural scene: they are disclosed and countable, not escalated to a human, because nothing is missing from the output.

Two local render modes sit behind the renderer interface while the production renderer technology is `OPEN`:

- **`faithful` (default)** reproduces the **source slide's own layout and styling** and reports `STRUCTURAL_RENDERED`: the effective theme colours and font scheme, slide/layout/master backgrounds and placeholder inheritance, shape fills/lines/gradients/geometry/rotation, exact run and paragraph formatting, embedded pictures with crop, tables, and connectors. A component it cannot reproduce is **drawn in the platform look, in place**, rather than dropped or degraded: an **unavailable source font** is substituted with the platform's type stack (deterministically — the client's own fonts can never change the asset) and recorded as `FONT_SUBSTITUTED:<family>`, and a frame whose typeface was substituted is shrunk to stay inside the author's frame instead of spilling over its neighbour; a **chart / SmartArt / WordArt / equation / graphic frame** becomes a flat platform panel labelled with the object (`UNSUPPORTED_OBJECT:<kind>`); a **picture that cannot be inlined** (EMF/WMF/TIFF, over budget, bytes withheld) becomes a flat platform panel labelled with the part. Each is a *warning* on a `STRUCTURAL_RENDERED` scene, not a review blocker — the deck's content is complete and its layout is the author's, so meaning is not at risk. Slide-level `DEGRADED_RENDERED` remains reserved for a scene that genuinely cannot be drawn.
- **`themed`** (opt-in) **re-lays the content out**: *the grouping is the author's, the content is the author's, the look is the platform's*. The extracted objects are queued with their source boxes and a binary widest-gap XY-cut (`flow.structure`) recovers the slide's **rows and columns** — a cell keeps the objects the author grouped together, so an icon stays beside its label and a card keeps its parts. Each recovered cell is then folded into flow blocks (a list of paragraphs, a table, a row of pictures) and re-laid out by a single measuring pass over a cursor — position and measurement are the same computation, so two blocks cannot overlap by construction — behind a hoisted heading (kicker/title/subtitle over one hairline rule), with the page number in a reserved bottom strip the flow may not enter. A cell that draws more than one block becomes a **card**: the content is inset and a flat platform surface panel is painted behind it (no border). The look is the platform's throughout: its type stack, its type scale, its palette; no source typeface, colour, fill or geometry is reproduced. Its fidelity is `THEMED_RENDERED` — a re-layout, **not** a rank on the fidelity-to-source ladder — and the gate is *content completeness*, not visual fidelity: nothing is re-selected, re-ordered or dropped. The source's own sizes select one of three theme rows (`lead`/`body`/`caption`), so a 40 pt statistic still reads as a statement beside a 12 pt note, and its bold/italic runs survive. Content that cannot be fitted even at the smallest readable type scale (`flow.LADDER`, then a continuous shrink to `theme.min_scale`) is still drawn, flagged `TEXT_OVERFLOW:<scene>`, degraded for review, and the page number is omitted so nothing is covered. Text metrics are estimated from a font-free advance table (`textmetrics.py`), so a line may break a word early — it can never collide with its neighbour.

A component the default renderer cannot reproduce is never silently flattened: it is drawn in the platform look and named in a warning. The renderer never reads the source package: it receives the Content IR and the picture bytes the compiler injects (`DEC-CONTENT-001`). Both modes estimate text metrics rather than measuring them, so a substituted typeface can wrap a line a word earlier than PowerPoint would.

## Vision

Invoked only for scans, diagrams, complex charts, SmartArt fallback, or meaning carried by position/color/arrows. Every invocation records reason, model/prompt versions, source refs, confidence, and review state.

## Security/reproducibility

Sandbox untrusted files, never execute macros/scripts/OLE, bound resources and archive expansion. Deterministic cache key uses source checksum, compiler version, renderer identity, and config hash.

## Locked Decisions Implemented

- `DEC-CONTENT-001`
- `DEC-CONTENT-002`
- `DEC-CONTENT-006`
- `DEC-CONTENT-009`
